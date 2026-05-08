from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.models.inventory.item import CostingMethod
from app.models.inventory.inventory_transaction import TransactionType
from app.services.erpnext.sync.stock_ledger import StockLedgerSyncService


def _entity(org_id, item_id, warehouse_id):
    return SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_type=TransactionType.RECEIPT,
        quantity=Decimal("1"),
    )


def test_post_sync_hook_rebuilds_wac_ledger_for_weighted_average_items():
    db = MagicMock()
    org_id = uuid4()
    user_id = uuid4()
    item_id = uuid4()
    warehouse_id = uuid4()
    service = StockLedgerSyncService(db, org_id, user_id)
    db.get.return_value = SimpleNamespace(
        item_id=item_id,
        organization_id=org_id,
        costing_method=CostingMethod.WEIGHTED_AVERAGE,
    )

    with patch(
        "app.services.erpnext.sync.stock_ledger.WACValuationService"
    ) as mock_wac:
        service.post_sync_hook(_entity(org_id, item_id, warehouse_id))

    mock_wac.return_value.rebuild_ledger_from_transactions.assert_called_once_with(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        persist=True,
        replace_existing=True,
    )


def test_post_sync_hook_skips_non_wac_items():
    db = MagicMock()
    org_id = uuid4()
    user_id = uuid4()
    item_id = uuid4()
    warehouse_id = uuid4()
    service = StockLedgerSyncService(db, org_id, user_id)
    db.get.return_value = SimpleNamespace(
        item_id=item_id,
        organization_id=org_id,
        costing_method=CostingMethod.FIFO,
    )

    with patch(
        "app.services.erpnext.sync.stock_ledger.WACValuationService"
    ) as mock_wac:
        service.post_sync_hook(_entity(org_id, item_id, warehouse_id))

    mock_wac.return_value.rebuild_ledger_from_transactions.assert_not_called()
