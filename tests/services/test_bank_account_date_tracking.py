from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.config import settings
from app.models.finance.banking.bank_reconciliation import ReconciliationStatus
from app.services.finance.banking.reconciliation_parts.workflow import (
    ReconciliationWorkflowService,
)
from app.services.finance.payments.paystack_sync import PaystackSyncService
from app.services.finance.reminder_service import FinanceReminderService


def test_paystack_statement_balance_update_writes_statement_date_as_date() -> None:
    db = MagicMock()
    statement_date = date(2026, 4, 14)
    db.scalar.return_value = SimpleNamespace(
        statement_date=statement_date,
        closing_balance=Decimal("1000.00"),
    )
    account = SimpleNamespace(
        bank_account_id=uuid4(),
        last_statement_balance=None,
        last_statement_date=None,
        updated_at=None,
    )

    PaystackSyncService(db, uuid4())._update_account_balance(account)

    assert account.last_statement_balance == Decimal("1000.00")
    assert account.last_statement_date == statement_date
    assert isinstance(account.last_statement_date, date)
    assert not isinstance(account.last_statement_date, datetime)


def test_paystack_api_balance_updates_write_calendar_date() -> None:
    db = MagicMock()
    svc = PaystackSyncService(db, uuid4())
    account = SimpleNamespace(
        account_name="Collections",
        last_statement_balance=None,
        last_statement_date=None,
        updated_at=None,
    )
    client = MagicMock()
    client.list_settlements.return_value = [SimpleNamespace(net_amount=12345)]

    svc._update_collections_balance_from_api(client, account)

    assert account.last_statement_balance == Decimal("123.45")
    assert account.last_statement_date == date.today()
    assert not isinstance(account.last_statement_date, datetime)

    account.account_name = "OPEX"
    client.get_balance.return_value = [
        {"currency": settings.default_functional_currency_code, "balance": 67890}
    ]

    svc._update_opex_balance_from_api(client, account)

    assert account.last_statement_balance == Decimal("678.90")
    assert account.last_statement_date == date.today()
    assert not isinstance(account.last_statement_date, datetime)


def test_reconciliation_approval_writes_reconciled_date_as_date() -> None:
    db = MagicMock()
    svc = ReconciliationWorkflowService()
    bank_account = SimpleNamespace(
        last_reconciled_date=None,
        last_reconciled_balance=None,
    )
    reconciliation_date = date(2026, 4, 13)
    reconciliation = SimpleNamespace(
        status=ReconciliationStatus.pending_review,
        reconciliation_difference=Decimal("0"),
        approved_by=None,
        approved_at=None,
        review_notes=None,
        bank_account=bank_account,
        reconciliation_date=reconciliation_date,
        statement_closing_balance=Decimal("500.00"),
    )
    svc._get_for_org = MagicMock(return_value=reconciliation)  # type: ignore[attr-defined]

    result = svc.approve(db, uuid4(), uuid4(), uuid4())

    assert result is reconciliation
    assert bank_account.last_reconciled_date == reconciliation_date
    assert not isinstance(bank_account.last_reconciled_date, datetime)
    assert bank_account.last_reconciled_balance == Decimal("500.00")
    db.flush.assert_called()


def test_reconciliation_reminder_date_arithmetic_accepts_date() -> None:
    service = FinanceReminderService(MagicMock())
    account = SimpleNamespace(
        last_reconciled_date=date.today() - timedelta(days=45),
    )

    urgency = service.get_reconciliation_urgency(account)

    assert urgency in {"warning", "overdue", "critical"}
