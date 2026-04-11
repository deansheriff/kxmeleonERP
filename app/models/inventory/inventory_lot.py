"""
Inventory Lot Model - Inventory Schema.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, cast

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship
from sqlalchemy import select as sa_select

from app.db import Base

if TYPE_CHECKING:
    from app.models.inventory.item import Item
    from app.models.inventory.inventory_lot_balance import InventoryLotBalance


class InventoryLot(Base):
    """
    Inventory lot/batch for lot-tracked items.
    """

    __tablename__ = "inventory_lot"
    __table_args__ = (
        UniqueConstraint("item_id", "lot_number", name="uq_inventory_lot"),
        Index("idx_lot_item", "item_id"),
        Index("idx_lot_org", "organization_id"),
        {"schema": "inv"},
    )

    lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core_org.organization.organization_id"),
        nullable=False,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inv.item.item_id"),
        nullable=False,
    )

    lot_number: Mapped[str] = mapped_column(String(50), nullable=False)

    # Dates
    manufacture_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Supplier/source
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    supplier_lot_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Cost
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)

    # Batch-level quantity context
    initial_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    allocation_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Certificate/QC
    certificate_of_analysis: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )

    # Relationships
    item: Mapped["Item"] = relationship(
        "Item",
        foreign_keys=[item_id],
        lazy="noload",
    )
    balances: Mapped[list["InventoryLotBalance"]] = relationship(
        "InventoryLotBalance",
        foreign_keys="InventoryLotBalance.lot_id",
        lazy="noload",
        back_populates="lot",
    )

    def _balance_rows(self) -> list["InventoryLotBalance"]:
        if "balances" in self.__dict__:
            return list(self.balances or [])
        session = object_session(self)
        if session is None:
            return []
        from app.models.inventory.inventory_lot_balance import InventoryLotBalance

        return list(
            session.scalars(
                sa_select(InventoryLotBalance).where(
                    InventoryLotBalance.lot_id == self.lot_id,
                    InventoryLotBalance.organization_id == self.organization_id,
                )
            ).all()
        )

    @property
    def warehouse_id(self) -> uuid.UUID | None:
        if "_snapshot_warehouse_id" in self.__dict__:
            return cast(uuid.UUID | None, self.__dict__["_snapshot_warehouse_id"])
        warehouse_ids = {
            balance.warehouse_id
            for balance in self._balance_rows()
            if balance.warehouse_id is not None
            and (
                (balance.quantity_on_hand or Decimal("0")) > 0
                or (balance.quantity_allocated or Decimal("0")) > 0
            )
        }
        if len(warehouse_ids) == 1:
            return next(iter(warehouse_ids))
        return None

    @warehouse_id.setter
    def warehouse_id(self, value: uuid.UUID | None) -> None:
        self.__dict__["_snapshot_warehouse_id"] = value

    @property
    def quantity_on_hand(self) -> Decimal:
        if "_snapshot_quantity_on_hand" in self.__dict__:
            return cast(Decimal, self.__dict__["_snapshot_quantity_on_hand"])
        return sum(
            (
                balance.quantity_on_hand or Decimal("0")
                for balance in self._balance_rows()
            ),
            Decimal("0"),
        )

    @quantity_on_hand.setter
    def quantity_on_hand(self, value: Decimal) -> None:
        self.__dict__["_snapshot_quantity_on_hand"] = value

    @property
    def quantity_allocated(self) -> Decimal:
        if "_snapshot_quantity_allocated" in self.__dict__:
            return cast(Decimal, self.__dict__["_snapshot_quantity_allocated"])
        return sum(
            (
                balance.quantity_allocated or Decimal("0")
                for balance in self._balance_rows()
            ),
            Decimal("0"),
        )

    @quantity_allocated.setter
    def quantity_allocated(self, value: Decimal) -> None:
        self.__dict__["_snapshot_quantity_allocated"] = value

    @property
    def quantity_available(self) -> Decimal:
        if "_snapshot_quantity_available" in self.__dict__:
            return cast(Decimal, self.__dict__["_snapshot_quantity_available"])
        return sum(
            (
                balance.quantity_available or Decimal("0")
                for balance in self._balance_rows()
            ),
            Decimal("0"),
        )

    @quantity_available.setter
    def quantity_available(self, value: Decimal) -> None:
        self.__dict__["_snapshot_quantity_available"] = value

    @property
    def is_quarantined(self) -> bool:
        if "_snapshot_is_quarantined" in self.__dict__:
            return cast(bool, self.__dict__["_snapshot_is_quarantined"])
        return any(bool(balance.is_quarantined) for balance in self._balance_rows())

    @is_quarantined.setter
    def is_quarantined(self, value: bool) -> None:
        self.__dict__["_snapshot_is_quarantined"] = value

    @property
    def quarantine_reason(self) -> str | None:
        if "_snapshot_quarantine_reason" in self.__dict__:
            return cast(str | None, self.__dict__["_snapshot_quarantine_reason"])
        reasons = [
            balance.quarantine_reason
            for balance in self._balance_rows()
            if balance.quarantine_reason
        ]
        return reasons[0] if reasons else None

    @quarantine_reason.setter
    def quarantine_reason(self, value: str | None) -> None:
        self.__dict__["_snapshot_quarantine_reason"] = value

    @property
    def qc_status(self) -> str | None:
        if "_snapshot_qc_status" in self.__dict__:
            return cast(str | None, self.__dict__["_snapshot_qc_status"])
        statuses = [
            balance.qc_status for balance in self._balance_rows() if balance.qc_status
        ]
        return statuses[0] if statuses else None

    @qc_status.setter
    def qc_status(self, value: str | None) -> None:
        self.__dict__["_snapshot_qc_status"] = value
