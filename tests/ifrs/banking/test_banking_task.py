"""
Tests for banking Celery tasks.

The auto-match task is the canonical demo of the dual-layer tenant
session API (``cross_org_session`` + ``session_for_org``). These tests
lock that contract — they assert *which helpers are called and how*,
not row counts, because zero rows is a legitimate outcome.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# ── Helpers ──────────────────────────────────────────────────────────


def _mock_match_result(
    matched: int = 0,
    skipped: int = 0,
    errors: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        matched=matched,
        skipped=skipped,
        errors=errors or [],
    )


def _fake_cross_session(rows):
    """Return a context manager that yields a session whose
    ``execute().all()`` returns ``rows`` (list of (stmt_id, org_id))."""

    @contextmanager
    def _factory():
        db = MagicMock()
        db.execute.return_value.all.return_value = rows
        yield db

    return _factory


def _fake_session_for_org_factory(per_org_dbs, captured_org_ids):
    """Return a ``session_for_org``-shaped context manager that pops one
    session from ``per_org_dbs`` each call and records the org_id."""
    db_iter = iter(per_org_dbs)

    @contextmanager
    def _factory(org_id):
        captured_org_ids.append(org_id)
        yield next(db_iter)

    return _factory


# ── Tests ────────────────────────────────────────────────────────────


class TestAutoMatchUnreconciledStatements:
    """Tests for the auto_match_unreconciled_statements Celery task."""

    def test_no_unmatched_statements(self) -> None:
        """Returns zero counts when no statements have unmatched lines.

        The cross-org listing returns nothing; no per-org session is
        ever opened.
        """
        from app.tasks.banking import auto_match_unreconciled_statements

        with (
            patch(
                "app.db.session_context.cross_org_session",
                _fake_cross_session([]),
            ),
            patch("app.db.session_context.session_for_org") as for_org,
            patch(
                "app.services.finance.banking.auto_reconciliation.AutoReconciliationService"
            ),
        ):
            result = auto_match_unreconciled_statements()

        assert result["statements_processed"] == 0
        assert result["total_matched"] == 0
        assert result["errors"] == []
        # No per-org session was opened because there was nothing to do.
        for_org.assert_not_called()

    def test_processes_multiple_statements(self) -> None:
        """Per-org session per statement; counts accumulate; commit fires
        once per statement (one commit per org-session, no shared commit)."""
        from app.tasks.banking import auto_match_unreconciled_statements

        org_id = uuid.uuid4()
        stmt1, stmt2 = uuid.uuid4(), uuid.uuid4()
        per_org_dbs = [MagicMock(name="db1"), MagicMock(name="db2")]
        captured: list[uuid.UUID] = []

        with (
            patch(
                "app.db.session_context.cross_org_session",
                _fake_cross_session([(stmt1, org_id), (stmt2, org_id)]),
            ),
            patch(
                "app.db.session_context.session_for_org",
                _fake_session_for_org_factory(per_org_dbs, captured),
            ),
            patch(
                "app.services.finance.banking.auto_reconciliation.AutoReconciliationService"
            ) as mock_svc_cls,
        ):
            mock_svc_cls.return_value.auto_match_statement.side_effect = [
                _mock_match_result(matched=3, skipped=2),
                _mock_match_result(matched=1, skipped=4),
            ]
            result = auto_match_unreconciled_statements()

        assert result["statements_processed"] == 2
        assert result["total_matched"] == 4
        assert result["errors"] == []
        # Each per-org session commits once. With the old shared-session
        # design this was one shared commit; the new per-org design
        # gives clean transaction boundaries per tenant.
        assert per_org_dbs[0].commit.call_count == 1
        assert per_org_dbs[1].commit.call_count == 1

    def test_per_statement_failure_isolation(self) -> None:
        """A failure in one statement must not affect others. With the new
        per-org session design, isolation is structural (separate session,
        separate transaction) instead of savepoint-based."""
        from app.tasks.banking import auto_match_unreconciled_statements

        org_id = uuid.uuid4()
        stmt1, stmt2 = uuid.uuid4(), uuid.uuid4()
        per_org_dbs = [MagicMock(name="db1"), MagicMock(name="db2")]
        captured: list[uuid.UUID] = []

        with (
            patch(
                "app.db.session_context.cross_org_session",
                _fake_cross_session([(stmt1, org_id), (stmt2, org_id)]),
            ),
            patch(
                "app.db.session_context.session_for_org",
                _fake_session_for_org_factory(per_org_dbs, captured),
            ),
            patch(
                "app.services.finance.banking.auto_reconciliation.AutoReconciliationService"
            ) as mock_svc_cls,
        ):
            mock_svc_cls.return_value.auto_match_statement.side_effect = [
                _mock_match_result(matched=2),
                RuntimeError("DB exploded"),
            ]
            result = auto_match_unreconciled_statements()

        # First statement committed successfully in its own session.
        assert result["statements_processed"] == 1
        assert result["total_matched"] == 2
        # Second statement's error is recorded but doesn't crash the task.
        assert len(result["errors"]) == 1
        assert "DB exploded" in result["errors"][0]
        # First-statement session committed once; second never reached commit.
        assert per_org_dbs[0].commit.call_count == 1
        assert per_org_dbs[1].commit.call_count == 0

    def test_uses_cross_org_session_for_listing_and_session_for_org_per_item(
        self,
    ) -> None:
        """The dual-layer RLS contract, asserted directly.

        Regression for the 2026-05-16 finding where the matcher ran on
        an un-primed session and every join silently returned zero. The
        canonical task entry-point pattern is:

        1. Use ``cross_org_session()`` to list cross-tenant work.
        2. Use ``session_for_org(org_id)`` for each tenant's work.

        Asserting the helpers themselves (not the underlying primitives)
        is what makes this regression-proof — if a future refactor drops
        either layer, this test fails.
        """
        from app.tasks.banking import auto_match_unreconciled_statements

        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        stmt1, stmt2 = uuid.uuid4(), uuid.uuid4()
        per_org_dbs = [MagicMock(name="db_a"), MagicMock(name="db_b")]
        captured: list[uuid.UUID] = []

        with (
            patch(
                "app.db.session_context.cross_org_session",
                _fake_cross_session([(stmt1, org_a), (stmt2, org_b)]),
            ),
            patch(
                "app.db.session_context.session_for_org",
                _fake_session_for_org_factory(per_org_dbs, captured),
            ),
            patch(
                "app.services.finance.banking.auto_reconciliation.AutoReconciliationService"
            ) as mock_svc_cls,
        ):
            mock_svc_cls.return_value.auto_match_statement.return_value = (
                _mock_match_result(matched=1)
            )
            auto_match_unreconciled_statements()

        # session_for_org was called once per statement, in order, with
        # that statement's org_id — proves both the count and the binding.
        assert captured == [org_a, org_b]

    def test_match_errors_appended_to_results(self) -> None:
        """Per-line errors from auto_match are propagated to task results."""
        from app.tasks.banking import auto_match_unreconciled_statements

        org_id = uuid.uuid4()
        stmt = uuid.uuid4()
        per_org_dbs = [MagicMock(name="db")]
        captured: list[uuid.UUID] = []

        with (
            patch(
                "app.db.session_context.cross_org_session",
                _fake_cross_session([(stmt, org_id)]),
            ),
            patch(
                "app.db.session_context.session_for_org",
                _fake_session_for_org_factory(per_org_dbs, captured),
            ),
            patch(
                "app.services.finance.banking.auto_reconciliation.AutoReconciliationService"
            ) as mock_svc_cls,
        ):
            mock_svc_cls.return_value.auto_match_statement.return_value = (
                _mock_match_result(matched=1, errors=["Line 3: amount mismatch"])
            )
            result = auto_match_unreconciled_statements()

        assert result["total_matched"] == 1
        assert len(result["errors"]) == 1
        assert "Line 3" in result["errors"][0]
