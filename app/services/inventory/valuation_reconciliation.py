"""
Inventory valuation reconciliation service.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.finance.gl.account import Account
from app.models.finance.gl.fiscal_period import FiscalPeriod
from app.models.finance.gl.posted_ledger_line import PostedLedgerLine
from app.models.inventory.inventory_transaction import InventoryTransaction
from app.models.inventory.item import Item
from app.models.inventory.item_wac_ledger import ItemWACLedger
from app.models.inventory.warehouse import Warehouse
from app.services.common import coerce_uuid


@dataclass(frozen=True)
class ValuationReconciliationResult:
    fiscal_period_id: UUID
    inventory_total: Decimal
    gl_total: Decimal
    difference: Decimal
    is_balanced: bool


@dataclass(frozen=True)
class ValuationReconciliationDetailRow:
    item_id: UUID
    warehouse_id: UUID
    item_code: str
    item_name: str
    warehouse_name: str
    quantity_on_hand: Decimal
    current_wac: Decimal
    inventory_value: Decimal
    gl_value: Decimal
    difference: Decimal
    is_balanced: bool


class ValuationReconciliationService:
    """Compare WAC inventory totals against GL inventory postings."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def reconcile(
        self,
        organization_id: UUID,
        fiscal_period_id: UUID | None = None,
    ) -> ValuationReconciliationResult:
        org_id = coerce_uuid(organization_id)
        period_id = fiscal_period_id or self._latest_period_id(org_id)
        if period_id is None:
            raise ValueError("No fiscal period found for organization.")
        period_end_date = self.db.scalar(
            select(FiscalPeriod.end_date).where(
                FiscalPeriod.fiscal_period_id == period_id
            )
        )
        if period_end_date is None:
            raise ValueError("Fiscal period end date not found.")

        inventory_total = Decimal(
            str(
                self.db.scalar(
                    select(func.coalesce(func.sum(ItemWACLedger.total_value), 0)).where(
                        ItemWACLedger.organization_id == org_id
                    )
                )
                or 0
            )
        )

        gl_total = Decimal(
            str(
                self.db.scalar(
                    select(
                        func.coalesce(
                            func.sum(
                                PostedLedgerLine.debit_amount
                                - PostedLedgerLine.credit_amount
                            ),
                            0,
                        )
                    )
                    .join(Account, Account.account_id == PostedLedgerLine.account_id)
                    .where(
                        PostedLedgerLine.organization_id == org_id,
                        PostedLedgerLine.posting_date <= period_end_date,
                        Account.subledger_type == "INVENTORY",
                    )
                )
                or 0
            )
        )

        difference = inventory_total - gl_total
        return ValuationReconciliationResult(
            fiscal_period_id=period_id,
            inventory_total=inventory_total,
            gl_total=gl_total,
            difference=difference,
            is_balanced=(difference == Decimal("0")),
        )

    def detail_rows(
        self,
        organization_id: UUID,
        fiscal_period_id: UUID | None = None,
        *,
        limit: int = 100,
    ) -> list[ValuationReconciliationDetailRow]:
        """Return item/warehouse WAC vs GL rows for the valuation report."""
        org_id = coerce_uuid(organization_id)
        period_id = fiscal_period_id or self._latest_period_id(org_id)
        if period_id is None:
            return []
        period_end_date = self.db.scalar(
            select(FiscalPeriod.end_date).where(
                FiscalPeriod.fiscal_period_id == period_id
            )
        )
        if period_end_date is None:
            return []

        wac_rows = (
            select(
                ItemWACLedger.item_id.label("item_id"),
                ItemWACLedger.warehouse_id.label("warehouse_id"),
                func.coalesce(ItemWACLedger.quantity_on_hand, 0).label(
                    "quantity_on_hand"
                ),
                func.coalesce(ItemWACLedger.current_wac, 0).label("current_wac"),
                func.coalesce(ItemWACLedger.total_value, 0).label("inventory_value"),
            )
            .where(ItemWACLedger.organization_id == org_id)
            .subquery()
        )
        gl_rows = (
            select(
                InventoryTransaction.item_id.label("item_id"),
                InventoryTransaction.warehouse_id.label("warehouse_id"),
                func.coalesce(
                    func.sum(
                        PostedLedgerLine.debit_amount - PostedLedgerLine.credit_amount
                    ),
                    0,
                ).label("gl_value"),
            )
            .join(Account, Account.account_id == PostedLedgerLine.account_id)
            .join(
                InventoryTransaction,
                InventoryTransaction.transaction_id
                == PostedLedgerLine.source_document_id,
            )
            .where(
                PostedLedgerLine.organization_id == org_id,
                PostedLedgerLine.posting_date <= period_end_date,
                Account.subledger_type == "INVENTORY",
            )
            .group_by(InventoryTransaction.item_id, InventoryTransaction.warehouse_id)
            .subquery()
        )

        item_id = func.coalesce(wac_rows.c.item_id, gl_rows.c.item_id)
        warehouse_id = func.coalesce(wac_rows.c.warehouse_id, gl_rows.c.warehouse_id)
        inventory_value = func.coalesce(wac_rows.c.inventory_value, 0)
        gl_value = func.coalesce(gl_rows.c.gl_value, 0)
        difference = inventory_value - gl_value

        stmt = (
            select(
                item_id.label("item_id"),
                warehouse_id.label("warehouse_id"),
                Item.item_code,
                Item.item_name,
                Warehouse.warehouse_name,
                func.coalesce(wac_rows.c.quantity_on_hand, 0).label("quantity_on_hand"),
                func.coalesce(wac_rows.c.current_wac, 0).label("current_wac"),
                inventory_value.label("inventory_value"),
                gl_value.label("gl_value"),
                difference.label("difference"),
            )
            .select_from(
                wac_rows.join(
                    gl_rows,
                    and_(
                        wac_rows.c.item_id == gl_rows.c.item_id,
                        wac_rows.c.warehouse_id == gl_rows.c.warehouse_id,
                    ),
                    full=True,
                )
            )
            .join(Item, Item.item_id == item_id)
            .join(Warehouse, Warehouse.warehouse_id == warehouse_id)
            .order_by(func.abs(difference).desc(), inventory_value.desc())
            .limit(max(1, min(limit, 500)))
        )

        rows = self.db.execute(stmt).all()
        return [
            ValuationReconciliationDetailRow(
                item_id=row.item_id,
                warehouse_id=row.warehouse_id,
                item_code=row.item_code,
                item_name=row.item_name,
                warehouse_name=row.warehouse_name,
                quantity_on_hand=Decimal(str(row.quantity_on_hand or 0)),
                current_wac=Decimal(str(row.current_wac or 0)),
                inventory_value=Decimal(str(row.inventory_value or 0)),
                gl_value=Decimal(str(row.gl_value or 0)),
                difference=Decimal(str(row.difference or 0)),
                is_balanced=(Decimal(str(row.difference or 0)) == Decimal("0")),
            )
            for row in rows
        ]

    def _latest_period_id(self, organization_id: UUID) -> UUID | None:
        inventory_period_stmt = (
            select(FiscalPeriod.fiscal_period_id)
            .join(
                PostedLedgerLine,
                PostedLedgerLine.fiscal_period_id == FiscalPeriod.fiscal_period_id,
            )
            .join(Account, Account.account_id == PostedLedgerLine.account_id)
            .where(
                FiscalPeriod.organization_id == organization_id,
                PostedLedgerLine.organization_id == organization_id,
                Account.subledger_type == "INVENTORY",
            )
            .group_by(FiscalPeriod.fiscal_period_id, FiscalPeriod.end_date)
            .order_by(FiscalPeriod.end_date.desc())
            .limit(1)
        )
        inventory_period_id = self.db.scalar(inventory_period_stmt)
        if inventory_period_id is not None:
            return inventory_period_id

        fallback_stmt = (
            select(FiscalPeriod.fiscal_period_id)
            .where(FiscalPeriod.organization_id == organization_id)
            .order_by(FiscalPeriod.end_date.desc())
            .limit(1)
        )
        return self.db.scalar(fallback_stmt)
