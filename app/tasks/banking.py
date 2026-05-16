"""
Banking Background Tasks - Celery tasks for banking reconciliation workflows.

Handles:
- Periodic auto-matching of unreconciled bank statement lines
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def auto_match_unreconciled_statements() -> dict[str, Any]:
    """Periodically auto-match unreconciled statement lines.

    Scans all statements with unmatched lines and runs deterministic
    matching via two strategies:

    1. **PaymentIntent** — DotMac-initiated Paystack transfers
    2. **Splynx CustomerPayment** — Splynx-originated payments

    This catches cases where a GL journal was posted *after* the
    statement was imported, as well as backfilling matches on
    historical statements.

    Session shape (two-step, the canonical batch pattern):

    1. List unmatched statements across all tenants via
       :func:`cross_org_session`, then close that session.
    2. Process each statement under its own :func:`session_for_org` —
       per-org session, single commit, isolated failure. This avoids
       (a) the SET LOCAL clearing that would silently de-prime a
       shared session after the first commit, and (b) identity-map
       contamination between tenants on the same session.

    Returns:
        Dict with processing statistics.
    """
    from sqlalchemy import select

    from app.db.session_context import cross_org_session, session_for_org
    from app.models.finance.banking.bank_statement import BankStatement
    from app.services.finance.banking.auto_reconciliation import (
        AutoReconciliationService,
    )

    logger.info("Starting periodic auto-match of unreconciled statements")

    results: dict[str, Any] = {
        "statements_processed": 0,
        "total_matched": 0,
        "errors": [],
    }

    # Step 1 — cross-tenant listing under bypass. Materialise the (id, org)
    # pairs we need, then drop the cross-org session before per-tenant work
    # so we never accidentally hand a bypassed session to the matcher.
    with cross_org_session() as cross_db:
        statement_meta = list(
            cross_db.execute(
                select(BankStatement.statement_id, BankStatement.organization_id).where(
                    BankStatement.unmatched_lines > 0
                )
            ).all()
        )

    auto_svc = AutoReconciliationService()

    # Step 2 — per-tenant matching, fresh session + single commit per org.
    for stmt_id, org_id in statement_meta:
        try:
            with session_for_org(org_id) as db:
                match_result = auto_svc.auto_match_statement(db, org_id, stmt_id)
                db.commit()

                if match_result.matched > 0:
                    results["total_matched"] += match_result.matched
                    logger.info(
                        "Auto-matched %d lines for statement %s (org %s)",
                        match_result.matched,
                        stmt_id,
                        org_id,
                    )

                if match_result.errors:
                    for err in match_result.errors:
                        results["errors"].append(f"Statement {stmt_id}: {err}")

                results["statements_processed"] += 1

        except Exception as e:
            logger.exception("Failed to auto-match statement %s", stmt_id)
            results["errors"].append(f"Statement {stmt_id}: {e}")

    logger.info(
        "Periodic auto-match complete: %d statements, %d lines matched",
        results["statements_processed"],
        results["total_matched"],
    )

    return results
