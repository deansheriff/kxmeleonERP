"""Tests for fixed asset depreciation GL reconciliation."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


class TestFixedAssetDepreciationReconciliationService:
    """Tests for depreciation run auto-matching against GL."""

    def test_reconcile_run_matches_expected_gl_lines(self):
        from app.models.fixed_assets.depreciation_run import DepreciationRunStatus
        from app.services.fixed_assets.reconciliation import (
            FixedAssetDepreciationReconciliationService,
        )

        org_id = uuid.uuid4()
        run_id = uuid.uuid4()
        journal_entry_id = uuid.uuid4()
        expense_account_id = uuid.uuid4()
        accum_account_id = uuid.uuid4()

        run = SimpleNamespace(
            run_id=run_id,
            organization_id=org_id,
            status=DepreciationRunStatus.POSTED,
            journal_entry_id=journal_entry_id,
        )
        schedules = [
            SimpleNamespace(
                depreciation_amount=Decimal("100.00"),
                expense_account_id=expense_account_id,
                accumulated_depreciation_account_id=accum_account_id,
            ),
            SimpleNamespace(
                depreciation_amount=Decimal("25.00"),
                expense_account_id=expense_account_id,
                accumulated_depreciation_account_id=accum_account_id,
            ),
        ]
        gl_rows = [
            SimpleNamespace(
                account_id=expense_account_id,
                debit_amount_functional=Decimal("125.00"),
                credit_amount_functional=Decimal("0"),
            ),
            SimpleNamespace(
                account_id=accum_account_id,
                debit_amount_functional=Decimal("0"),
                credit_amount_functional=Decimal("125.00"),
            ),
        ]

        db = MagicMock()
        db.get.return_value = run
        db.scalars.return_value = SimpleNamespace(all=lambda: schedules)
        db.execute.return_value = SimpleNamespace(all=lambda: gl_rows)

        result = FixedAssetDepreciationReconciliationService.reconcile_run(
            db,
            org_id,
            run_id,
        )

        assert result.is_reconciled is True
        assert result.status == "reconciled"
        assert result.matched_count == 2
        assert result.expected_total == Decimal("250.00")
        assert result.gl_total == Decimal("250.00")
        assert result.net_variance == Decimal("0.00")

    def test_reconcile_run_flags_missing_and_variance_lines(self):
        from app.models.fixed_assets.depreciation_run import DepreciationRunStatus
        from app.services.fixed_assets.reconciliation import (
            FixedAssetDepreciationReconciliationService,
        )

        org_id = uuid.uuid4()
        run_id = uuid.uuid4()
        expense_account_id = uuid.uuid4()
        accum_account_id = uuid.uuid4()
        extra_account_id = uuid.uuid4()

        run = SimpleNamespace(
            run_id=run_id,
            organization_id=org_id,
            status=DepreciationRunStatus.POSTED,
            journal_entry_id=None,
        )
        schedules = [
            SimpleNamespace(
                depreciation_amount=Decimal("100.00"),
                expense_account_id=expense_account_id,
                accumulated_depreciation_account_id=accum_account_id,
            )
        ]
        gl_rows = [
            SimpleNamespace(
                account_id=expense_account_id,
                debit_amount_functional=Decimal("90.00"),
                credit_amount_functional=Decimal("0"),
            ),
            SimpleNamespace(
                account_id=extra_account_id,
                debit_amount_functional=Decimal("5.00"),
                credit_amount_functional=Decimal("0"),
            ),
        ]

        db = MagicMock()
        db.get.return_value = run
        db.scalars.return_value = SimpleNamespace(all=lambda: schedules)
        db.execute.return_value = SimpleNamespace(all=lambda: gl_rows)

        result = FixedAssetDepreciationReconciliationService.reconcile_run(
            db,
            org_id,
            run_id,
        )

        statuses = {line.status for line in result.lines}
        assert result.is_reconciled is False
        assert result.status == "review_required"
        assert statuses == {"VARIANCE", "MISSING_GL", "EXTRA_GL"}
        assert result.variance_count == 1
        assert result.missing_gl_count == 1
        assert result.extra_gl_count == 1

    def test_reconcile_run_requires_posted_run(self):
        from app.models.fixed_assets.depreciation_run import DepreciationRunStatus
        from app.services.fixed_assets.reconciliation import (
            FixedAssetDepreciationReconciliationService,
        )

        org_id = uuid.uuid4()
        run_id = uuid.uuid4()
        db = MagicMock()
        db.get.return_value = SimpleNamespace(
            run_id=run_id,
            organization_id=org_id,
            status=DepreciationRunStatus.CALCULATED,
            journal_entry_id=None,
        )

        with pytest.raises(HTTPException) as exc_info:
            FixedAssetDepreciationReconciliationService.reconcile_run(
                db,
                org_id,
                run_id,
            )

        assert exc_info.value.status_code == 400
