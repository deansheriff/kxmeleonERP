"""
Weighted-average cost valuation service.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import TypedDict
from uuid import UUID

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from app.models.inventory.inventory_transaction import (
    InventoryTransaction,
    TransactionType,
)
from app.models.inventory.item import CostingMethod, Item
from app.models.inventory.item_wac_ledger import ItemWACLedger
from app.models.sync import SyncEntity
from app.services.common import coerce_uuid

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WACSnapshot:
    quantity: Decimal
    wac: Decimal
    total_value: Decimal


@dataclass(frozen=True)
class WACResult:
    previous_wac: Decimal
    new_wac: Decimal
    unit_cost: Decimal
    total_cost: Decimal
    new_balance_qty: Decimal
    new_balance_value: Decimal


@dataclass(frozen=True)
class WACRebuildRow:
    organization_id: UUID
    item_id: UUID
    warehouse_id: UUID
    quantity_on_hand: Decimal
    current_wac: Decimal
    total_value: Decimal
    last_transaction_id: UUID
    transaction_count: int


@dataclass(frozen=True)
class WACBreakdownRow:
    transaction_id: UUID
    transaction_date: object
    transaction_type: str
    reference: str | None
    quantity_in: Decimal
    quantity_out: Decimal
    unit_cost: Decimal
    value_in: Decimal
    value_out: Decimal
    quantity_after: Decimal
    wac_after: Decimal
    total_value_after: Decimal


class _WACSnapshotState(TypedDict):
    quantity_on_hand: Decimal
    current_wac: Decimal
    total_value: Decimal
    last_transaction_id: UUID
    transaction_count: int


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


class WACValuationService:
    """Weighted-average costing calculations and ledger updates."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_snapshot(
        self,
        organization_id: UUID,
        item_id: UUID,
        warehouse_id: UUID,
    ) -> WACSnapshot:
        ledger = self.db.scalar(
            select(ItemWACLedger).where(
                ItemWACLedger.organization_id == coerce_uuid(organization_id),
                ItemWACLedger.item_id == coerce_uuid(item_id),
                ItemWACLedger.warehouse_id == coerce_uuid(warehouse_id),
            )
        )
        if not ledger:
            return self._rebuild_snapshot_from_transactions(
                organization_id, item_id, warehouse_id
            )
        return WACSnapshot(
            quantity=Decimal(str(ledger.quantity_on_hand or 0)),
            wac=Decimal(str(ledger.current_wac or 0)),
            total_value=Decimal(str(ledger.total_value or 0)),
        )

    def _rebuild_snapshot_from_transactions(
        self,
        organization_id: UUID,
        item_id: UUID,
        warehouse_id: UUID,
    ) -> WACSnapshot:
        """Compute WAC snapshot from transaction history when ledger is missing."""
        from app.services.inventory.transaction import InventoryTransactionService

        qty = InventoryTransactionService.get_current_balance(
            self.db, organization_id, item_id, warehouse_id
        )
        if qty <= 0:
            return WACSnapshot(
                quantity=Decimal("0"),
                wac=Decimal("0"),
                total_value=Decimal("0"),
            )
        # Ledger missing but transactions exist — initialize ledger
        from app.models.inventory.item import Item

        item = self.db.get(Item, coerce_uuid(item_id))
        wac = Decimal(str(item.average_cost or 0)) if item else Decimal("0")
        total_value = (qty * wac).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        # Persist so future lookups don't re-compute
        ledger = self._get_or_create_ledger(organization_id, item_id, warehouse_id)
        ledger.current_wac = wac
        ledger.quantity_on_hand = qty
        ledger.total_value = total_value
        self.db.flush()
        logger.info(
            "Auto-initialized WAC ledger for item %s warehouse %s: qty=%s wac=%s",
            item_id,
            warehouse_id,
            qty,
            wac,
        )
        return WACSnapshot(quantity=qty, wac=wac, total_value=total_value)

    def calculate_receipt_cost(
        self,
        organization_id: UUID,
        item_id: UUID,
        warehouse_id: UUID,
        receipt_qty: Decimal,
        receipt_unit_cost: Decimal,
    ) -> WACResult:
        current = self.get_snapshot(organization_id, item_id, warehouse_id)
        if receipt_qty <= 0:
            raise ValueError("Receipt quantity must be positive.")
        if receipt_unit_cost < 0:
            raise ValueError("Receipt unit cost cannot be negative.")

        receipt_total = receipt_qty * receipt_unit_cost
        new_qty = current.quantity + receipt_qty
        if new_qty == 0:
            new_wac = Decimal("0")
        else:
            new_wac = ((current.total_value + receipt_total) / new_qty).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
        new_total = (new_qty * new_wac).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
        return WACResult(
            previous_wac=current.wac,
            new_wac=new_wac,
            unit_cost=receipt_unit_cost,
            total_cost=receipt_total,
            new_balance_qty=new_qty,
            new_balance_value=new_total,
        )

    def calculate_issue_cost(
        self,
        organization_id: UUID,
        item_id: UUID,
        warehouse_id: UUID,
        issue_qty: Decimal,
    ) -> WACResult:
        current = self.get_snapshot(organization_id, item_id, warehouse_id)
        if issue_qty <= 0:
            raise ValueError("Issue quantity must be positive.")
        if current.quantity < issue_qty:
            raise ValueError(
                f"Insufficient stock: {current.quantity} available, {issue_qty} requested"
            )

        unit_cost = current.wac
        issue_total = (issue_qty * unit_cost).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
        new_qty = current.quantity - issue_qty
        new_total = (new_qty * unit_cost).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
        return WACResult(
            previous_wac=current.wac,
            new_wac=current.wac,
            unit_cost=unit_cost,
            total_cost=issue_total,
            new_balance_qty=new_qty,
            new_balance_value=new_total,
        )

    def apply_receipt(
        self,
        organization_id: UUID,
        item_id: UUID,
        warehouse_id: UUID,
        receipt_qty: Decimal,
        receipt_unit_cost: Decimal,
        *,
        transaction_id: UUID | None = None,
    ) -> WACResult:
        result = self.calculate_receipt_cost(
            organization_id,
            item_id,
            warehouse_id,
            receipt_qty,
            receipt_unit_cost,
        )
        ledger = self._get_or_create_ledger(organization_id, item_id, warehouse_id)
        ledger.current_wac = result.new_wac
        ledger.quantity_on_hand = result.new_balance_qty
        ledger.total_value = result.new_balance_value
        ledger.last_transaction_id = transaction_id
        self.db.flush()
        return result

    def apply_issue(
        self,
        organization_id: UUID,
        item_id: UUID,
        warehouse_id: UUID,
        issue_qty: Decimal,
        *,
        transaction_id: UUID | None = None,
    ) -> WACResult:
        result = self.calculate_issue_cost(
            organization_id,
            item_id,
            warehouse_id,
            issue_qty,
        )
        ledger = self._get_or_create_ledger(organization_id, item_id, warehouse_id)
        ledger.current_wac = result.new_wac
        ledger.quantity_on_hand = result.new_balance_qty
        ledger.total_value = result.new_balance_value
        ledger.last_transaction_id = transaction_id
        self.db.flush()
        return result

    def _get_or_create_ledger(
        self,
        organization_id: UUID,
        item_id: UUID,
        warehouse_id: UUID,
    ) -> ItemWACLedger:
        org_id = coerce_uuid(organization_id)
        itm_id = coerce_uuid(item_id)
        wh_id = coerce_uuid(warehouse_id)
        ledger = self.db.scalar(
            select(ItemWACLedger).where(
                ItemWACLedger.organization_id == org_id,
                ItemWACLedger.item_id == itm_id,
                ItemWACLedger.warehouse_id == wh_id,
            )
        )
        if ledger:
            return ledger

        ledger = ItemWACLedger(
            organization_id=org_id,
            item_id=itm_id,
            warehouse_id=wh_id,
            current_wac=Decimal("0"),
            quantity_on_hand=Decimal("0"),
            total_value=Decimal("0"),
        )
        self.db.add(ledger)
        self.db.flush()
        return ledger

    @staticmethod
    def _signed_quantity_delta(txn: InventoryTransaction) -> Decimal:
        """Infer signed quantity movement from the stored running balances."""
        before = Decimal(str(txn.quantity_before or 0))
        after = Decimal(str(txn.quantity_after or 0))
        delta = after - before
        if delta != 0:
            return delta

        quantity = Decimal(str(txn.quantity or 0))
        if txn.transaction_type in {
            "ISSUE",
            "SALE",
            "SCRAP",
            "DISASSEMBLY",
        }:
            return -abs(quantity)
        return quantity

    @staticmethod
    def _rebuild_value_delta(
        txn: InventoryTransaction, quantity_delta: Decimal
    ) -> Decimal:
        """Return the signed value movement stored on an inventory transaction."""
        total_cost = Decimal(str(txn.total_cost or 0))
        if quantity_delta < 0:
            return -abs(total_cost)
        return total_cost

    @staticmethod
    def _rebuild_outbound_value_delta(
        txn: InventoryTransaction,
        outbound_qty: Decimal,
        current_wac: Decimal,
    ) -> Decimal:
        """Return outbound value, falling back to WAC when import cost is missing."""
        total_cost = Decimal(str(txn.total_cost or 0))
        if total_cost != 0:
            return -abs(total_cost)
        return -_quantize_money(outbound_qty * current_wac)

    @classmethod
    def _build_rebuild_rows(
        cls,
        rows: list[tuple[InventoryTransaction, Item]],
    ) -> list[WACRebuildRow]:
        """Replay WAC transactions into per-item, per-warehouse ledger rows."""
        snapshots: dict[tuple[UUID, UUID, UUID], _WACSnapshotState] = {}

        for txn, item in rows:
            if item.costing_method != CostingMethod.WEIGHTED_AVERAGE:
                continue

            key = (txn.organization_id, txn.item_id, txn.warehouse_id)
            snapshot = snapshots.setdefault(
                key,
                {
                    "quantity_on_hand": Decimal("0"),
                    "current_wac": Decimal("0"),
                    "total_value": Decimal("0"),
                    "last_transaction_id": txn.transaction_id,
                    "transaction_count": 0,
                },
            )

            delta = cls._signed_quantity_delta(txn)
            quantity_on_hand = snapshot["quantity_on_hand"]
            total_value = snapshot["total_value"]

            if delta > 0:
                inbound_cost = cls._rebuild_value_delta(txn, delta)
                new_qty = quantity_on_hand + delta
                new_total = total_value + inbound_cost
                new_wac = (
                    _quantize_money(new_total / new_qty)
                    if new_qty > 0
                    else Decimal("0")
                )
                snapshot["quantity_on_hand"] = new_qty
                snapshot["total_value"] = _quantize_money(new_total)
                snapshot["current_wac"] = new_wac
            elif delta < 0:
                outbound_qty = min(abs(delta), quantity_on_hand)
                new_qty = quantity_on_hand - outbound_qty
                new_total = total_value + cls._rebuild_outbound_value_delta(
                    txn,
                    outbound_qty,
                    snapshot["current_wac"],
                )
                if new_qty <= 0:
                    snapshot["quantity_on_hand"] = Decimal("0")
                    snapshot["total_value"] = Decimal("0")
                    snapshot["current_wac"] = Decimal("0")
                else:
                    snapshot["quantity_on_hand"] = _quantize_money(new_qty)
                    snapshot["total_value"] = _quantize_money(new_total)
                    snapshot["current_wac"] = _quantize_money(new_total / new_qty)
            elif (
                txn.transaction_type
                in {TransactionType.ADJUSTMENT, TransactionType.COUNT_ADJUSTMENT}
                and Decimal(str(txn.total_cost or 0)) != 0
            ):
                adjustment_qty = Decimal(str(txn.quantity_after or 0))
                if adjustment_qty > 0:
                    new_total = Decimal(str(txn.total_cost or 0))
                    snapshot["quantity_on_hand"] = _quantize_money(adjustment_qty)
                    snapshot["total_value"] = _quantize_money(new_total)
                    snapshot["current_wac"] = _quantize_money(
                        new_total / adjustment_qty
                    )

            snapshot["last_transaction_id"] = txn.transaction_id
            snapshot["transaction_count"] = int(snapshot["transaction_count"]) + 1

        rebuilt: list[WACRebuildRow] = []
        for (org_id, item_id, warehouse_id), snapshot in snapshots.items():
            rebuilt.append(
                WACRebuildRow(
                    organization_id=org_id,
                    item_id=item_id,
                    warehouse_id=warehouse_id,
                    quantity_on_hand=snapshot["quantity_on_hand"],
                    current_wac=snapshot["current_wac"],
                    total_value=snapshot["total_value"],
                    last_transaction_id=snapshot["last_transaction_id"],
                    transaction_count=snapshot["transaction_count"],
                )
            )
        return rebuilt

    def compute_rebuild_rows(
        self,
        organization_id: UUID | None = None,
        *,
        item_id: UUID | None = None,
        warehouse_id: UUID | None = None,
    ) -> list[WACRebuildRow]:
        """Compute WAC ledger rows by replaying historical inventory transactions."""
        stmt = (
            select(InventoryTransaction, Item)
            .join(Item, Item.item_id == InventoryTransaction.item_id)
            .outerjoin(
                SyncEntity,
                and_(
                    SyncEntity.organization_id == InventoryTransaction.organization_id,
                    SyncEntity.source_system == "erpnext",
                    SyncEntity.source_doctype == "Stock Ledger Entry",
                    SyncEntity.target_id == InventoryTransaction.transaction_id,
                ),
            )
            .where(Item.costing_method == CostingMethod.WEIGHTED_AVERAGE)
            .order_by(
                InventoryTransaction.organization_id.asc(),
                InventoryTransaction.item_id.asc(),
                InventoryTransaction.warehouse_id.asc(),
                SyncEntity.source_name.asc().nulls_last(),
                InventoryTransaction.transaction_date.asc(),
                InventoryTransaction.created_at.asc(),
                InventoryTransaction.transaction_id.asc(),
            )
        )

        if organization_id is not None:
            stmt = stmt.where(
                InventoryTransaction.organization_id == coerce_uuid(organization_id)
            )
        if item_id is not None:
            stmt = stmt.where(InventoryTransaction.item_id == coerce_uuid(item_id))
        if warehouse_id is not None:
            stmt = stmt.where(
                InventoryTransaction.warehouse_id == coerce_uuid(warehouse_id)
            )

        rows = list(self.db.execute(stmt).tuples().all())
        return self._build_rebuild_rows(rows)

    @classmethod
    def _build_breakdown_rows(
        cls,
        rows: list[tuple[InventoryTransaction, Item]],
    ) -> list[WACBreakdownRow]:
        """Replay WAC transactions and return the running calculation trail."""
        quantity_on_hand = Decimal("0")
        current_wac = Decimal("0")
        total_value = Decimal("0")
        breakdown_rows: list[WACBreakdownRow] = []

        for txn, item in rows:
            if item.costing_method != CostingMethod.WEIGHTED_AVERAGE:
                continue

            delta = cls._signed_quantity_delta(txn)
            quantity_in = Decimal("0")
            quantity_out = Decimal("0")
            value_in = Decimal("0")
            value_out = Decimal("0")

            if delta > 0:
                quantity_in = delta
                inbound_cost = cls._rebuild_value_delta(txn, delta)
                value_in = inbound_cost
                new_qty = quantity_on_hand + delta
                new_total = total_value + inbound_cost
                current_wac = (
                    _quantize_money(new_total / new_qty)
                    if new_qty > 0
                    else Decimal("0")
                )
                quantity_on_hand = _quantize_money(new_qty)
                total_value = _quantize_money(new_total)
            elif delta < 0:
                quantity_out = min(abs(delta), quantity_on_hand)
                outbound_value = abs(
                    cls._rebuild_outbound_value_delta(txn, quantity_out, current_wac)
                )
                value_out = outbound_value
                new_qty = quantity_on_hand - quantity_out
                new_total = total_value - outbound_value
                if new_qty <= 0:
                    quantity_on_hand = Decimal("0")
                    total_value = Decimal("0")
                    current_wac = Decimal("0")
                else:
                    quantity_on_hand = _quantize_money(new_qty)
                    total_value = _quantize_money(new_total)
                    current_wac = _quantize_money(total_value / quantity_on_hand)
            elif (
                txn.transaction_type
                in {TransactionType.ADJUSTMENT, TransactionType.COUNT_ADJUSTMENT}
                and Decimal(str(txn.total_cost or 0)) != 0
            ):
                adjustment_qty = Decimal(str(txn.quantity_after or 0))
                if adjustment_qty > 0:
                    new_total = Decimal(str(txn.total_cost or 0))
                    quantity_on_hand = _quantize_money(adjustment_qty)
                    total_value = _quantize_money(new_total)
                    current_wac = _quantize_money(new_total / adjustment_qty)
                    value_in = total_value

            txn_type = getattr(txn.transaction_type, "value", txn.transaction_type)
            breakdown_rows.append(
                WACBreakdownRow(
                    transaction_id=txn.transaction_id,
                    transaction_date=txn.transaction_date,
                    transaction_type=str(txn_type),
                    reference=txn.reference,
                    quantity_in=quantity_in,
                    quantity_out=quantity_out,
                    unit_cost=Decimal(str(txn.unit_cost or 0)),
                    value_in=_quantize_money(value_in),
                    value_out=_quantize_money(value_out),
                    quantity_after=quantity_on_hand,
                    wac_after=current_wac,
                    total_value_after=total_value,
                )
            )

        return breakdown_rows

    def breakdown_rows(
        self,
        organization_id: UUID,
        item_id: UUID,
        warehouse_id: UUID,
        *,
        limit: int = 250,
    ) -> list[WACBreakdownRow]:
        """Return transaction-level WAC calculation rows for one item/warehouse."""
        stmt = (
            select(InventoryTransaction, Item)
            .join(Item, Item.item_id == InventoryTransaction.item_id)
            .outerjoin(
                SyncEntity,
                and_(
                    SyncEntity.organization_id == InventoryTransaction.organization_id,
                    SyncEntity.source_system == "erpnext",
                    SyncEntity.source_doctype == "Stock Ledger Entry",
                    SyncEntity.target_id == InventoryTransaction.transaction_id,
                ),
            )
            .where(
                InventoryTransaction.organization_id == coerce_uuid(organization_id),
                InventoryTransaction.item_id == coerce_uuid(item_id),
                InventoryTransaction.warehouse_id == coerce_uuid(warehouse_id),
                Item.costing_method == CostingMethod.WEIGHTED_AVERAGE,
            )
            .order_by(
                SyncEntity.source_name.asc().nulls_last(),
                InventoryTransaction.transaction_date.asc(),
                InventoryTransaction.created_at.asc(),
                InventoryTransaction.transaction_id.asc(),
            )
            .limit(max(1, min(limit, 1000)))
        )
        rows = list(self.db.execute(stmt).tuples().all())
        return self._build_breakdown_rows(rows)

    def rebuild_ledger_from_transactions(
        self,
        organization_id: UUID | None = None,
        *,
        item_id: UUID | None = None,
        warehouse_id: UUID | None = None,
        persist: bool = False,
        replace_existing: bool = False,
    ) -> dict[str, int]:
        """Replay historical WAC transactions and optionally persist ledger rows."""
        rebuilt_rows = self.compute_rebuild_rows(
            organization_id,
            item_id=item_id,
            warehouse_id=warehouse_id,
        )

        if persist and replace_existing:
            delete_stmt = delete(ItemWACLedger)
            if organization_id is not None:
                delete_stmt = delete_stmt.where(
                    ItemWACLedger.organization_id == coerce_uuid(organization_id)
                )
            if item_id is not None:
                delete_stmt = delete_stmt.where(
                    ItemWACLedger.item_id == coerce_uuid(item_id)
                )
            if warehouse_id is not None:
                delete_stmt = delete_stmt.where(
                    ItemWACLedger.warehouse_id == coerce_uuid(warehouse_id)
                )
            self.db.execute(delete_stmt)

        written = 0
        for rebuilt in rebuilt_rows:
            if persist:
                ledger = self._get_or_create_ledger(
                    rebuilt.organization_id,
                    rebuilt.item_id,
                    rebuilt.warehouse_id,
                )
                ledger.current_wac = rebuilt.current_wac
                ledger.quantity_on_hand = rebuilt.quantity_on_hand
                ledger.total_value = rebuilt.total_value
                ledger.last_transaction_id = rebuilt.last_transaction_id
                written += 1

        if persist:
            self.db.flush()

        return {
            "rows_computed": len(rebuilt_rows),
            "rows_written": written,
            "transactions_replayed": sum(row.transaction_count for row in rebuilt_rows),
        }
