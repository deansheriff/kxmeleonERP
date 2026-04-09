from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.models.inventory.inventory_return import InventoryReturnMode
from app.services.inventory.return_web import InventoryReturnWebService


def test_create_return_from_form_manual_success() -> None:
    db = MagicMock()
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    item_id = uuid.uuid4()
    source_warehouse_id = uuid.uuid4()
    destination_warehouse_id = uuid.uuid4()

    item = MagicMock()
    item.organization_id = org_id
    item.base_uom = "Nos"
    item.average_cost = Decimal("12")
    item.currency_code = "NGN"
    item.track_lots = False
    item.track_serial_numbers = False

    source_warehouse = MagicMock()
    source_warehouse.organization_id = org_id
    destination_warehouse = MagicMock()
    destination_warehouse.organization_id = org_id
    destination_warehouse.is_receiving = True

    fiscal_period_result = MagicMock()
    fiscal_period = MagicMock()
    fiscal_period.fiscal_period_id = uuid.uuid4()
    fiscal_period_result.first.return_value = fiscal_period

    added_objects: list[object] = []

    def add_capture(obj: object) -> None:
        added_objects.append(obj)

    def flush_assign() -> None:
        for obj in added_objects:
            cast_any: Any = obj
            if getattr(cast_any, "return_id", None) is None:
                cast_any.return_id = uuid.uuid4()

    db.add.side_effect = add_capture
    db.flush.side_effect = flush_assign
    db.get.side_effect = [item, source_warehouse, destination_warehouse]
    db.scalars.side_effect = [fiscal_period_result]

    posted_transaction = MagicMock()
    posted_transaction.transaction_id = uuid.uuid4()

    with patch(
        "app.services.inventory.transaction.InventoryTransactionService.create_transaction",
        return_value=posted_transaction,
    ) as mock_create_transaction:
        inventory_return = InventoryReturnWebService.create_from_form(
            db=db,
            organization_id=org_id,
            user_id=user_id,
            material_request_id=None,
            item_id=str(item_id),
            source_warehouse_id=str(source_warehouse_id),
            destination_warehouse_id=str(destination_warehouse_id),
            quantity="4",
            return_date="2026-04-09",
            reason="Unused items returned from site",
            reference="RTN-001",
            remarks="Manual return",
            lot_number=None,
            serial_numbers_text=None,
        )

    assert inventory_return.return_mode == InventoryReturnMode.MANUAL
    assert inventory_return.item_id == item_id
    assert inventory_return.source_warehouse_id == source_warehouse_id
    assert inventory_return.destination_warehouse_id == destination_warehouse_id
    assert inventory_return.quantity == Decimal("4")
    assert inventory_return.reason == "Unused items returned from site"
    assert inventory_return.posted_transaction_id == posted_transaction.transaction_id
    mock_create_transaction.assert_called_once()


def test_create_return_from_form_material_request_blocks_over_return() -> None:
    db = MagicMock()
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    item_id = uuid.uuid4()
    source_warehouse_id = uuid.uuid4()
    destination_warehouse_id = uuid.uuid4()
    material_request_id = uuid.uuid4()
    material_request_item_id = uuid.uuid4()

    item = MagicMock()
    item.organization_id = org_id
    item.base_uom = "Nos"
    item.average_cost = Decimal("12")
    item.currency_code = "NGN"
    item.track_lots = False
    item.track_serial_numbers = False

    source_warehouse = MagicMock()
    source_warehouse.organization_id = org_id
    destination_warehouse = MagicMock()
    destination_warehouse.organization_id = org_id
    destination_warehouse.is_receiving = True

    fiscal_period_result = MagicMock()
    fiscal_period = MagicMock()
    fiscal_period.fiscal_period_id = uuid.uuid4()
    fiscal_period_result.first.return_value = fiscal_period

    material_request_item = MagicMock()
    material_request_item.item_id = material_request_item_id
    material_request_item.inventory_item_id = item_id
    material_request_item.warehouse_id = source_warehouse_id
    material_request_item.requested_qty = Decimal("5")

    material_request = MagicMock()
    material_request.request_id = material_request_id
    material_request.organization_id = org_id
    material_request.default_warehouse_id = None
    material_request.items = [material_request_item]

    material_request_result = MagicMock()
    material_request_result.unique.return_value.first.return_value = material_request

    db.get.side_effect = [item, source_warehouse, destination_warehouse]
    db.scalars.side_effect = [fiscal_period_result, material_request_result]
    db.scalar.return_value = Decimal("4")

    with pytest.raises(ValueError, match="exceeds remaining issued quantity"):
        InventoryReturnWebService.create_from_form(
            db=db,
            organization_id=org_id,
            user_id=user_id,
            material_request_id=str(material_request_id),
            item_id=str(item_id),
            source_warehouse_id=str(source_warehouse_id),
            destination_warehouse_id=str(destination_warehouse_id),
            quantity="2",
            return_date="2026-04-09",
            reason="Return against MR",
            reference=None,
            remarks=None,
            lot_number=None,
            serial_numbers_text=None,
        )
