"""Tests for finance dashboard subledger reconciliation."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql

from app.services.finance.dashboard import DashboardService


def _compiled_params(statement) -> dict:
    return statement.compile(dialect=postgresql.dialect()).params


def test_subledger_reconciliation_uses_posted_outstanding_statuses() -> None:
    """Subledger totals should exclude draft/unposted documents."""
    mock_db = MagicMock()
    mock_db.scalar.side_effect = [Decimal("0"), Decimal("0")]

    DashboardService.get_subledger_reconciliation(
        mock_db,
        uuid.uuid4(),
        gl_balances=(Decimal("0"), Decimal("0")),
    )

    ar_stmt = mock_db.scalar.call_args_list[0].args[0]
    ap_stmt = mock_db.scalar.call_args_list[1].args[0]

    assert _compiled_params(ar_stmt)["status_1"] == [
        "OVERDUE",
        "PARTIALLY_PAID",
        "POSTED",
    ]
    assert _compiled_params(ap_stmt)["status_1"] == [
        "APPROVED",
        "ON_HOLD",
        "PARTIALLY_PAID",
        "POSTED",
    ]
