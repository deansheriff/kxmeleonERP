"""
Inventory Return Model - Inventory Schema.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    ARRAY,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.inventory.inventory_lot import InventoryLot
    from app.models.inventory.inventory_transaction import InventoryTransaction
    from app.models.inventory.item import Item
    from app.models.inventory.material_request import MaterialRequest, MaterialRequestItem
    from app.models.inventory.warehouse import Warehouse


class InventoryReturnMode(str, enum.Enum):
    """How the return was initiated."""

    MANUAL = "MANUAL"
    MATERIAL_REQUEST = "MATERIAL_REQUEST"


class InventoryReturn(Base):
    """Single-item return-to-store record."""

    __tablename__ = "inventory_return"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "return_number",
            name="uq_inventory_return_org_number",
        ),
        Index("idx_inventory_return_org", "organization_id"),
        Index("idx_inventory_return_mode", "return_mode"),
        Index("idx_inventory_return_mr", "material_request_id"),
        Index("idx_inventory_return_item", "item_id"),
        Index("idx_inventory_return_return_date", "return_date"),
        {"schema": "inv"},
    )

    return_id: Mapped[uuid.UUID] = mapped_column(
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
    return_number: Mapped[str] = mapped_column(String(50), nullable=False)
    return_mode: Mapped[InventoryReturnMode] = mapped_column(
        Enum(InventoryReturnMode, name="inventory_return_mode", schema="inv"),
        nullable=False,
        default=InventoryReturnMode.MANUAL,
    )

    material_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inv.material_request.request_id"),
        nullable=True,
    )
    material_request_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inv.material_request_item.item_id"),
        nullable=True,
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inv.item.item_id"),
        nullable=False,
    )
    source_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inv.warehouse.warehouse_id"),
        nullable=False,
    )
    destination_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inv.warehouse.warehouse_id"),
        nullable=False,
    )
    return_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    uom: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    lot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inv.inventory_lot.lot_id"),
        nullable=True,
    )
    lot_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    serial_numbers: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    source_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inv.inventory_transaction.transaction_id"),
        nullable=True,
    )
    posted_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inv.inventory_transaction.transaction_id"),
        nullable=True,
    )

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
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

    item: Mapped["Item"] = relationship("Item", foreign_keys=[item_id], lazy="noload")
    source_warehouse: Mapped["Warehouse"] = relationship(
        "Warehouse", foreign_keys=[source_warehouse_id], lazy="noload"
    )
    destination_warehouse: Mapped["Warehouse"] = relationship(
        "Warehouse", foreign_keys=[destination_warehouse_id], lazy="noload"
    )
    material_request: Mapped["MaterialRequest | None"] = relationship(
        "MaterialRequest", foreign_keys=[material_request_id], lazy="noload"
    )
    material_request_item: Mapped["MaterialRequestItem | None"] = relationship(
        "MaterialRequestItem",
        foreign_keys=[material_request_item_id],
        lazy="noload",
    )
    lot: Mapped["InventoryLot | None"] = relationship(
        "InventoryLot", foreign_keys=[lot_id], lazy="noload"
    )
    source_transaction: Mapped["InventoryTransaction | None"] = relationship(
        "InventoryTransaction",
        foreign_keys=[source_transaction_id],
        lazy="noload",
    )
    posted_transaction: Mapped["InventoryTransaction | None"] = relationship(
        "InventoryTransaction",
        foreign_keys=[posted_transaction_id],
        lazy="noload",
    )
