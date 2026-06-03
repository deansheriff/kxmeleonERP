from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.models.finance.ap.supplier_invoice import SupplierInvoiceStatus
from app.services.common import ValidationError
from app.services.finance.ap.auto_inventory_receipt import (
    APInvoiceAutoReceiptService,
)
from app.services.finance.ap.supplier_invoice import SupplierInvoiceService


class _ScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return list(self.values)

    def first(self):
        return self.values[0] if self.values else None


def _invoice(org_id, *, status=SupplierInvoiceStatus.SUBMITTED, auto=True):
    return SimpleNamespace(
        invoice_id=uuid4(),
        organization_id=org_id,
        invoice_number="SINV202605-0003",
        supplier_invoice_number="SUP-INV-001",
        currency_code="NGN",
        status=status,
        auto_create_inventory_receipt=auto,
    )


def _line(invoice_id, item_id, warehouse_id=None, *, quantity="2"):
    return SimpleNamespace(
        line_id=uuid4(),
        invoice_id=invoice_id,
        line_number=1,
        item_id=item_id,
        quantity=Decimal(quantity),
        unit_price=Decimal("10.00"),
        receipt_warehouse_id=warehouse_id,
        receipt_reference="DEL-001",
        receipt_serial_numbers=None,
        receipt_auto_generate_serials=False,
        auto_receipt_transaction_id=None,
    )


def _item(org_id, item_id, *, stock=True, serial=False):
    return SimpleNamespace(
        item_id=item_id,
        organization_id=org_id,
        track_inventory=stock,
        track_serial_numbers=serial,
        base_uom="EA",
    )


def _warehouse(org_id, warehouse_id):
    return SimpleNamespace(warehouse_id=warehouse_id, organization_id=org_id)


def _period():
    return SimpleNamespace(fiscal_period_id=uuid4())


def test_build_invoice_input_preserves_auto_receipt_fields():
    db = MagicMock()
    org_id = uuid4()
    warehouse_id = uuid4()
    item_id = uuid4()

    payload = {
        "supplier_id": str(uuid4()),
        "invoice_date": "2026-05-25",
        "received_date": "2026-05-25",
        "due_date": "2026-05-30",
        "currency_code": "NGN",
        "auto_create_inventory_receipt": True,
        "lines": [
            {
                "description": "Router",
                "quantity": "2",
                "unit_price": "10",
                "expense_account_id": str(uuid4()),
                "item_id": str(item_id),
                "receipt_warehouse_id": str(warehouse_id),
                "receipt_reference": "DEL-001",
                "receipt_serial_numbers": "SN-1\nSN-2",
                "receipt_auto_generate_serials": False,
            }
        ],
    }

    with patch(
        "app.services.finance.ap.supplier_invoice.resolve_currency_code",
        return_value="NGN",
    ):
        result = SupplierInvoiceService.build_input_from_payload(db, org_id, payload)

    assert result.auto_create_inventory_receipt is True
    assert result.lines[0].receipt_warehouse_id == warehouse_id
    assert result.lines[0].receipt_reference == "DEL-001"
    assert result.lines[0].receipt_serial_numbers == ["SN-1", "SN-2"]
    assert result.lines[0].receipt_auto_generate_serials is False


def test_no_receipt_before_submission():
    db = MagicMock()
    org_id = uuid4()
    invoice = _invoice(org_id, status=SupplierInvoiceStatus.DRAFT)
    db.get.return_value = invoice

    with patch(
        "app.services.finance.ap.auto_inventory_receipt.InventoryTransactionService.create_receipt"
    ) as create_receipt:
        result = APInvoiceAutoReceiptService.create_for_invoice(
            db, org_id, invoice.invoice_id, uuid4()
        )

    assert result.created_count == 0
    create_receipt.assert_not_called()


def test_receipt_created_after_submission():
    db = MagicMock()
    org_id = uuid4()
    invoice = _invoice(org_id)
    item_id = uuid4()
    warehouse_id = uuid4()
    line = _line(invoice.invoice_id, item_id, warehouse_id)
    item = _item(org_id, item_id)
    warehouse = _warehouse(org_id, warehouse_id)
    transaction = SimpleNamespace(transaction_id=uuid4())

    def _get(model, _id):
        if model.__name__ == "SupplierInvoice":
            return invoice
        if model.__name__ == "Item":
            return item
        if model.__name__ == "Warehouse":
            return warehouse
        return None

    db.get.side_effect = _get
    db.scalars.side_effect = [
        _ScalarResult([line]),
        _ScalarResult([]),
        _ScalarResult([_period()]),
    ]

    with patch(
        "app.services.finance.ap.auto_inventory_receipt.InventoryTransactionService.create_receipt",
        return_value=transaction,
    ) as create_receipt:
        result = APInvoiceAutoReceiptService.create_for_invoice(
            db, org_id, invoice.invoice_id, uuid4()
        )

    assert result.created_count == 1
    assert result.transaction_ids == [transaction.transaction_id]
    assert line.auto_receipt_transaction_id == transaction.transaction_id
    create_receipt.assert_called_once()


def test_non_stock_lines_skipped():
    db = MagicMock()
    org_id = uuid4()
    invoice = _invoice(org_id)
    item_id = uuid4()
    line = _line(invoice.invoice_id, item_id, uuid4())
    item = _item(org_id, item_id, stock=False)

    def _get(model, _id):
        if model.__name__ == "SupplierInvoice":
            return invoice
        if model.__name__ == "Item":
            return item
        return None

    db.get.side_effect = _get
    db.scalars.side_effect = [_ScalarResult([line])]

    with patch(
        "app.services.finance.ap.auto_inventory_receipt.InventoryTransactionService.create_receipt"
    ) as create_receipt:
        result = APInvoiceAutoReceiptService.create_for_invoice(
            db, org_id, invoice.invoice_id, uuid4()
        )

    assert result.created_count == 0
    assert result.skipped_count == 1
    create_receipt.assert_not_called()


def test_duplicate_prevention_skips_existing_line_receipt():
    db = MagicMock()
    org_id = uuid4()
    invoice = _invoice(org_id)
    item_id = uuid4()
    line = _line(invoice.invoice_id, item_id, uuid4())
    line.auto_receipt_transaction_id = uuid4()
    item = _item(org_id, item_id)

    def _get(model, _id):
        if model.__name__ == "SupplierInvoice":
            return invoice
        if model.__name__ == "Item":
            return item
        return None

    db.get.side_effect = _get
    db.scalars.side_effect = [_ScalarResult([line])]

    with patch(
        "app.services.finance.ap.auto_inventory_receipt.InventoryTransactionService.create_receipt"
    ) as create_receipt:
        result = APInvoiceAutoReceiptService.create_for_invoice(
            db, org_id, invoice.invoice_id, uuid4()
        )

    assert result.created_count == 0
    assert result.skipped_count == 1
    create_receipt.assert_not_called()


def test_missing_warehouse_blocks_receipt_creation_clearly():
    db = MagicMock()
    org_id = uuid4()
    invoice = _invoice(org_id)
    item_id = uuid4()
    line = _line(invoice.invoice_id, item_id, warehouse_id=None)
    item = _item(org_id, item_id)

    def _get(model, _id):
        if model.__name__ == "SupplierInvoice":
            return invoice
        if model.__name__ == "Item":
            return item
        return None

    db.get.side_effect = _get
    db.scalars.side_effect = [
        _ScalarResult([line]),
        _ScalarResult([]),
    ]

    with pytest.raises(ValidationError, match="warehouse is required"):
        APInvoiceAutoReceiptService.create_for_invoice(
            db, org_id, invoice.invoice_id, uuid4()
        )
