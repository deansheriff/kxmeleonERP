from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

from app.models.expense.expense_claim import ExpenseClaimStatus
from app.services.erpnext.sync.payment_entry import PaymentEntrySyncService


def _make_claim(
    *,
    org_id: uuid.UUID,
    status: ExpenseClaimStatus,
) -> SimpleNamespace:
    return SimpleNamespace(
        claim_id=uuid.uuid4(),
        organization_id=org_id,
        status=status,
        paid_on=None,
        payment_reference=None,
        updated_by_id=None,
    )


def _make_service(db: MagicMock, org_id: uuid.UUID) -> PaymentEntrySyncService:
    svc = PaymentEntrySyncService.__new__(PaymentEntrySyncService)
    svc.db = db
    svc.organization_id = org_id
    svc.user_id = uuid.uuid4()
    return svc


def test_sync_employee_payment_uses_expense_mark_paid_for_approved_claims() -> None:
    org_id = uuid.uuid4()
    db = MagicMock()
    claim = _make_claim(org_id=org_id, status=ExpenseClaimStatus.APPROVED)
    svc = _make_service(db, org_id)
    svc._resolve_entity_id = MagicMock(return_value=claim.claim_id)
    db.get.return_value = claim

    payment_date = date(2026, 4, 10)
    data = {
        "_references": [
            {
                "_reference_doctype": "Expense Claim",
                "_reference_source_name": "HR-EXP-0001",
            }
        ],
        "payment_date": payment_date,
        "reference": "ACC-PAY-0001",
    }

    with patch(
        "app.services.expense.expense_service.ExpenseService.mark_paid",
        autospec=True,
        return_value=claim,
    ) as mock_mark_paid:
        result = svc._sync_employee_expense_payment(data, "ACC-PAY-0001")

    assert result == claim.claim_id
    mock_mark_paid.assert_called_once_with(
        ANY,
        org_id,
        claim.claim_id,
        payment_reference="ACC-PAY-0001",
        payment_date=payment_date,
        send_notification=False,
    )
    assert claim.updated_by_id == svc.user_id


def test_sync_employee_payment_backfills_existing_paid_claim_metadata() -> None:
    org_id = uuid.uuid4()
    db = MagicMock()
    claim = _make_claim(org_id=org_id, status=ExpenseClaimStatus.PAID)
    svc = _make_service(db, org_id)
    svc._resolve_entity_id = MagicMock(return_value=claim.claim_id)
    db.get.return_value = claim

    payment_date = date(2026, 4, 10)
    data = {
        "_references": [
            {
                "_reference_doctype": "Expense Claim",
                "_reference_source_name": "HR-EXP-0001",
            }
        ],
        "payment_date": payment_date,
        "reference": "ACC-PAY-0001",
    }

    with patch(
        "app.services.expense.expense_service.ExpenseService.mark_paid",
        autospec=True,
    ) as mock_mark_paid:
        result = svc._sync_employee_expense_payment(data, "ACC-PAY-0001")

    assert result == claim.claim_id
    assert claim.paid_on == payment_date
    assert claim.payment_reference == "ACC-PAY-0001"
    assert claim.updated_by_id == svc.user_id
    mock_mark_paid.assert_not_called()
