"""
Automation Background Tasks — Celery tasks for workflow rule execution.

Handles:
- Async workflow action execution (dispatched from WorkflowService)
- Scheduled workflow rule evaluation
- Recurring template processing (invoices, bills, journals, expenses)
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from celery import shared_task
from sqlalchemy import distinct, select

from app.db.session_context import cross_org_session, session_for_org

logger = logging.getLogger(__name__)


def _resolve_workflow_rule_org(rule_id: str) -> UUID | None:
    """Resolve a workflow rule's organization before tenant-scoped execution."""
    from app.models.finance.automation import WorkflowRule

    with cross_org_session() as db:
        return db.scalar(
            select(WorkflowRule.organization_id).where(
                WorkflowRule.rule_id == UUID(rule_id)
            )
        )


def _list_orgs_with_due_recurring_templates() -> list[UUID]:
    """List organizations that have due recurring templates."""
    from datetime import date

    from app.models.finance.automation import RecurringStatus, RecurringTemplate

    stmt = (
        select(distinct(RecurringTemplate.organization_id))
        .where(
            RecurringTemplate.status == RecurringStatus.ACTIVE,
            RecurringTemplate.next_run_date <= date.today(),
        )
        .order_by(RecurringTemplate.organization_id)
    )
    with cross_org_session() as db:
        return list(db.scalars(stmt).all())


def _list_orgs_with_scheduled_workflow_rules() -> list[UUID]:
    """List organizations that have active scheduled workflow rules."""
    from app.models.finance.automation import TriggerEvent, WorkflowRule

    stmt = (
        select(distinct(WorkflowRule.organization_id))
        .where(
            WorkflowRule.is_active.is_(True),
            WorkflowRule.trigger_event == TriggerEvent.ON_SCHEDULE,
        )
        .order_by(WorkflowRule.organization_id)
    )
    with cross_org_session() as db:
        return list(db.scalars(stmt).all())


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def execute_workflow_action(
    self: Any,
    rule_id: str,
    context_dict: dict[str, Any],
) -> dict[str, Any]:
    """Execute a single workflow action asynchronously.

    Called by WorkflowService.trigger_event() when a rule has
    execute_async=True.

    Args:
        rule_id: UUID string of the workflow rule to execute.
        context_dict: Serialized TriggerContext (from TriggerContext.to_dict()).

    Returns:
        Dict with execution result.
    """
    logger.info("Executing async workflow action: rule=%s", rule_id)

    result: dict[str, Any] = {
        "rule_id": rule_id,
        "status": "unknown",
        "error": None,
    }

    org_id = _resolve_workflow_rule_org(rule_id)
    if org_id is None:
        result["status"] = "rule_not_found"
        result["error"] = f"Rule {rule_id} not found"
        logger.warning("Workflow rule %s not found", rule_id)
        return result

    try:
        with session_for_org(org_id) as db:
            from app.services.finance.automation.workflow import (
                TriggerContext,
                workflow_service,
            )

            rule = workflow_service.get(db, UUID(rule_id))
            if not rule:
                result["status"] = "rule_not_found"
                result["error"] = f"Rule {rule_id} not found"
                logger.warning("Workflow rule %s not found", rule_id)
                return result

            context = TriggerContext.from_dict(context_dict)

            # Check throttle before executing
            if workflow_service._is_throttled(db, rule, context.entity_id):
                result["status"] = "throttled"
                logger.info(
                    "Rule %s throttled for entity %s",
                    rule_id,
                    context.entity_id,
                )
                return result

            execution = workflow_service.execute_action(db, rule, context)
            db.commit()

            result["status"] = execution.status.value
            result["execution_id"] = str(execution.execution_id)

    except Exception as exc:
        logger.exception("Async workflow action failed: rule=%s", rule_id)
        result["status"] = "error"
        result["error"] = str(exc)

        # Retry on transient failures
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for rule %s", rule_id)

    return result


@shared_task
def process_recurring_templates() -> dict[str, Any]:
    """Process all due recurring templates (invoices, bills, journals, expenses).

    Returns:
        Dict with processing statistics.
    """
    logger.info("Processing recurring templates")

    from app.services.finance.automation.recurring import recurring_service

    total = 0
    succeeded = 0
    failed = 0
    for org_id in _list_orgs_with_due_recurring_templates():
        try:
            with session_for_org(org_id) as db:
                logs: list[Any] = recurring_service.run_due_templates(db)
                db.commit()
        except Exception:
            logger.exception("Recurring template processing failed for org %s", org_id)
            failed += 1
            continue

        # Extract counts inside session before ORM objects become detached
        total += len(logs)
        succeeded += sum(1 for log in logs if log.status.value == "SUCCESS")
        failed += sum(1 for log in logs if log.status.value == "FAILED")

    logger.info(
        "Recurring templates: processed=%d, succeeded=%d, failed=%d",
        total,
        succeeded,
        failed,
    )
    return {"processed": total, "succeeded": succeeded, "failed": failed}


@shared_task
def process_scheduled_workflow_rules() -> dict[str, Any]:
    """Evaluate and execute all due ON_SCHEDULE workflow rules.

    This task should be run on a periodic schedule (e.g. every 5 minutes)
    via Celery beat.

    Returns:
        Dict with processing statistics.
    """
    logger.info("Processing scheduled workflow rules")

    from app.services.finance.automation.scheduled_evaluator import (
        scheduled_evaluator,
    )

    results: dict[str, Any] = {
        "rules_checked": 0,
        "rules_due": 0,
        "actions_fired": 0,
        "errors": [],
    }
    for org_id in _list_orgs_with_scheduled_workflow_rules():
        try:
            with session_for_org(org_id) as db:
                org_results = scheduled_evaluator.evaluate_due_rules(db)
                db.commit()
            results["rules_checked"] += org_results["rules_checked"]
            results["rules_due"] += org_results["rules_due"]
            results["actions_fired"] += org_results["actions_fired"]
            results["errors"].extend(org_results["errors"])
        except Exception as exc:
            logger.exception("Scheduled workflow evaluation failed for org %s", org_id)
            results["errors"].append(str(exc))

    logger.info(
        "Scheduled rules: checked=%d, due=%d, fired=%d, errors=%d",
        results["rules_checked"],
        results["rules_due"],
        results["actions_fired"],
        len(results["errors"]),
    )
    return results
