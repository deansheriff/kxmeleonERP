"""Tests for monthly fixed-asset depreciation automation task."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch


class TestProcessMonthlyDepreciationRuns:
    """Tests for the monthly fixed-assets depreciation automation task."""

    def test_skips_when_automation_disabled(self) -> None:
        """Task should no-op cleanly when automation is turned off."""
        mock_db = MagicMock()

        with (
            patch("app.tasks.finance.SessionLocal") as mock_session,
            patch(
                "app.services.fixed_assets.depreciation.DepreciationService.automation_enabled",
                return_value=False,
            ),
        ):
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            from app.tasks.finance import process_monthly_depreciation_runs

            result = process_monthly_depreciation_runs()

        assert result["automation_enabled"] is False
        assert result["organizations_checked"] == 0
        assert result["runs_calculated"] == 0
        assert result["runs_posted"] == 0

    def test_processes_active_organizations(self) -> None:
        """Task should create or post runs for each active organization."""
        org_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        mock_db = MagicMock()

        with (
            patch("app.tasks.finance.SessionLocal") as mock_session,
            patch(
                "app.services.fixed_assets.depreciation.DepreciationService.automation_enabled",
                return_value=True,
            ),
            patch(
                "app.services.fixed_assets.depreciation.DepreciationService.automation_auto_post_enabled",
                return_value=True,
            ),
            patch(
                "app.services.fixed_assets.depreciation.DepreciationService.list_active_organization_ids",
                return_value=org_ids,
            ),
            patch(
                "app.services.fixed_assets.depreciation.DepreciationService.create_automated_monthly_run",
                side_effect=[
                    {"status": "posted"},
                    {"status": "calculated"},
                    {"status": "skipped"},
                ],
            ) as run_mock,
        ):
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            from app.tasks.finance import process_monthly_depreciation_runs

            result = process_monthly_depreciation_runs()

        assert run_mock.call_count == 3
        assert result["automation_enabled"] is True
        assert result["auto_post"] is True
        assert result["organizations_checked"] == 3
        assert result["runs_posted"] == 1
        assert result["runs_calculated"] == 1
        assert result["skipped"] == 1
