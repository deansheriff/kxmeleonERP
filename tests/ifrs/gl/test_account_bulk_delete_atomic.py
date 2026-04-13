"""
Tests for AccountBulkService.bulk_delete — atomic batch semantics.

The override must reject the entire batch if *any* account fails its
dependency check. A partial state must never be committed.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.models.finance.gl.account import AccountType
from app.services.finance.gl.bulk import AccountBulkService
from tests.ifrs.gl.conftest import MockAccount


@pytest.fixture
def org_id():
    return uuid.uuid4()


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = MagicMock()
    db.delete = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    return db


def _make_service(db, org_id):
    return AccountBulkService(db, org_id)


def _execute_returns(mock_db, line_rows=None, balance_rows=None):
    """
    The service calls db.execute() twice:
      1. journal-line count group-by
      2. balance-row count group-by
    """
    line_mock = MagicMock()
    line_mock.all.return_value = line_rows or []
    balance_mock = MagicMock()
    balance_mock.all.return_value = balance_rows or []
    mock_db.execute.side_effect = [line_mock, balance_mock]


@pytest.mark.asyncio
async def test_bulk_delete_empty_ids(mock_db, org_id):
    service = _make_service(mock_db, org_id)
    result = await service.bulk_delete([])
    assert result.success_count == 0
    assert "No IDs provided" in result.message


@pytest.mark.asyncio
async def test_bulk_delete_all_clean_commits(mock_db, org_id):
    """All accounts clean → single commit, every account deleted."""
    a1 = MockAccount(account_code="1000", account_name="Cash")
    a2 = MockAccount(account_code="1100", account_name="Bank")
    service = _make_service(mock_db, org_id)
    service._get_entities = MagicMock(return_value=[a1, a2])
    _execute_returns(mock_db)

    result = await service.bulk_delete([a1.account_id, a2.account_id])

    assert result.success_count == 2
    assert mock_db.delete.call_count == 2
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_bulk_delete_rejects_whole_batch_on_single_violation(mock_db, org_id):
    """
    The core atomicity guarantee: if ONE account has journal entries,
    NO accounts get deleted and NO commit fires.
    """
    a1 = MockAccount(account_code="1000", account_name="Cash")
    a2 = MockAccount(account_code="1100", account_name="Bank")
    service = _make_service(mock_db, org_id)
    service._get_entities = MagicMock(return_value=[a1, a2])
    _execute_returns(
        mock_db,
        line_rows=[(a2.account_id, 7)],  # a2 has 7 journal entries
    )

    result = await service.bulk_delete([a1.account_id, a2.account_id])

    assert result.success_count == 0
    assert "Batch rejected" in result.message
    assert "7 journal entries" in result.message
    mock_db.delete.assert_not_called()
    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_bulk_delete_rejects_on_balance_records(mock_db, org_id):
    a1 = MockAccount(account_code="1000", account_name="Cash")
    service = _make_service(mock_db, org_id)
    service._get_entities = MagicMock(return_value=[a1])
    _execute_returns(mock_db, balance_rows=[(a1.account_id, 3)])

    result = await service.bulk_delete([a1.account_id])

    assert result.success_count == 0
    assert "balance records" in result.message
    mock_db.delete.assert_not_called()
    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_bulk_delete_rejects_control_account(mock_db, org_id):
    control = MockAccount(
        account_code="1000",
        account_name="Assets Control",
        account_type=AccountType.CONTROL,
    )
    service = _make_service(mock_db, org_id)
    service._get_entities = MagicMock(return_value=[control])
    _execute_returns(mock_db)

    result = await service.bulk_delete([control.account_id])

    assert result.success_count == 0
    assert "control account" in result.message
    mock_db.delete.assert_not_called()
    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_bulk_delete_rolls_back_on_db_error(mock_db, org_id):
    a1 = MockAccount(account_code="1000", account_name="Cash")
    service = _make_service(mock_db, org_id)
    service._get_entities = MagicMock(return_value=[a1])
    _execute_returns(mock_db)
    mock_db.commit.side_effect = RuntimeError("deadlock detected")

    result = await service.bulk_delete([a1.account_id])

    assert result.success_count == 0
    assert "Delete failed" in result.message
    mock_db.rollback.assert_called_once()
