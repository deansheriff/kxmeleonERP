"""Tests for finance subledger reconciliation alerts."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch


def test_subledger_reconciliation_alert_uses_dashboard_balance_keys() -> None:
    """Alert payload should use the keys returned by DashboardService."""
    org_id = uuid.uuid4()
    recipient_id = uuid.uuid4()
    mock_db = MagicMock()
    mock_db.scalars.return_value.all.return_value = [
        SimpleNamespace(organization_id=org_id)
    ]

    mock_reminder_service = MagicMock()
    mock_reminder_service.send_subledger_discrepancy_alert.side_effect = [1, 1]

    recon_data = {
        "ar_ok": False,
        "ap_ok": False,
        "gl_ar_balance": Decimal("100.25"),
        "subledger_ar_balance": Decimal("80.00"),
        "gl_ap_balance": Decimal("45.75"),
        "subledger_ap_balance": Decimal("55.50"),
    }

    with (
        patch("app.tasks.finance.SessionLocal") as mock_session,
        patch("app.tasks.finance._get_finance_recipients", return_value=[recipient_id]),
        patch(
            "app.services.finance.dashboard.DashboardService.get_subledger_reconciliation",
            return_value=recon_data,
        ),
        patch(
            "app.services.finance.reminder_service.FinanceReminderService",
            return_value=mock_reminder_service,
        ),
    ):
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        from app.tasks.finance import process_subledger_reconciliation

        result = process_subledger_reconciliation()

    assert result["ar_discrepancies"] == 1
    assert result["ap_discrepancies"] == 1
    assert result["notifications_sent"] == 2
    mock_reminder_service.send_subledger_discrepancy_alert.assert_has_calls(
        [
            call(
                organization_id=org_id,
                recipient_ids=[recipient_id],
                subledger_type="AR",
                gl_balance=Decimal("100.25"),
                subledger_balance=Decimal("80.00"),
            ),
            call(
                organization_id=org_id,
                recipient_ids=[recipient_id],
                subledger_type="AP",
                gl_balance=Decimal("45.75"),
                subledger_balance=Decimal("55.50"),
            ),
        ]
    )
