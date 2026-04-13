"""ReconciliationWorkflowService component."""

from __future__ import annotations

from typing import cast

from app.services.finance.banking.reconciliation_parts.base import (
    BankReconciliation,
    Decimal,
    HTTPException,
    ReconciliationStatus,
    Session,
    UTC,
    UUID,
    datetime,
    logger,
)


class ReconciliationWorkflowService:
    """Bank reconciliation methods for workflow."""

    def submit_for_review(
        self,
        db: Session,
        organization_id: UUID,
        reconciliation_id: UUID,
    ) -> BankReconciliation:
        """Submit reconciliation for review."""
        reconciliation = cast(
            BankReconciliation,
            self._get_for_org(db, organization_id, reconciliation_id),  # type: ignore[attr-defined]
        )

        if reconciliation.status != ReconciliationStatus.draft:
            raise HTTPException(
                status_code=400,
                detail="Only draft reconciliations can be submitted for review",
            )

        reconciliation.status = ReconciliationStatus.pending_review
        db.flush()

        try:
            from app.services.finance.automation.event_dispatcher import (
                fire_workflow_event,
            )

            fire_workflow_event(
                db=db,
                organization_id=reconciliation.organization_id,
                entity_type="RECONCILIATION",
                entity_id=reconciliation.reconciliation_id,
                event="ON_STATUS_CHANGE",
                old_values={"status": "draft"},
                new_values={"status": "pending_review"},
            )
        except Exception:
            logger.exception("Ignored exception")

        db.flush()
        return reconciliation

    def approve(
        self,
        db: Session,
        organization_id: UUID,
        reconciliation_id: UUID,
        approved_by: UUID,
        notes: str | None = None,
    ) -> BankReconciliation:
        """Approve a reconciliation."""
        reconciliation = cast(
            BankReconciliation,
            self._get_for_org(db, organization_id, reconciliation_id),  # type: ignore[attr-defined]
        )

        if reconciliation.status != ReconciliationStatus.pending_review:
            raise HTTPException(
                status_code=400, detail="Only pending reconciliations can be approved"
            )

        if reconciliation.reconciliation_difference != Decimal("0"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot approve: reconciliation difference is "
                f"{reconciliation.reconciliation_difference}",
            )

        reconciliation.status = ReconciliationStatus.approved
        reconciliation.approved_by = approved_by
        reconciliation.approved_at = datetime.utcnow()
        if notes:
            reconciliation.review_notes = notes

        # Update bank account
        bank_account = reconciliation.bank_account
        bank_account.last_reconciled_date = datetime.combine(
            reconciliation.reconciliation_date,
            datetime.min.time(),
            tzinfo=UTC,
        )
        bank_account.last_reconciled_balance = reconciliation.statement_closing_balance

        db.flush()

        try:
            from app.services.finance.automation.event_dispatcher import (
                fire_workflow_event,
            )

            fire_workflow_event(
                db=db,
                organization_id=reconciliation.organization_id,
                entity_type="RECONCILIATION",
                entity_id=reconciliation.reconciliation_id,
                event="ON_APPROVAL",
                old_values={"status": "pending_review"},
                new_values={"status": "approved"},
                user_id=approved_by,
            )
        except Exception:
            logger.exception("Ignored exception")

        db.flush()
        return reconciliation

    def reject(
        self,
        db: Session,
        organization_id: UUID,
        reconciliation_id: UUID,
        rejected_by: UUID,
        notes: str = "",
    ) -> BankReconciliation:
        """Reject a reconciliation."""
        reconciliation = cast(
            BankReconciliation,
            self._get_for_org(db, organization_id, reconciliation_id),  # type: ignore[attr-defined]
        )

        if reconciliation.status != ReconciliationStatus.pending_review:
            raise HTTPException(
                status_code=400, detail="Only pending reconciliations can be rejected"
            )

        reconciliation.status = ReconciliationStatus.rejected
        reconciliation.reviewed_by = rejected_by
        reconciliation.reviewed_at = datetime.utcnow()
        reconciliation.review_notes = notes

        db.flush()

        try:
            from app.services.finance.automation.event_dispatcher import (
                fire_workflow_event,
            )

            fire_workflow_event(
                db=db,
                organization_id=reconciliation.organization_id,
                entity_type="RECONCILIATION",
                entity_id=reconciliation.reconciliation_id,
                event="ON_REJECTION",
                old_values={"status": "pending_review"},
                new_values={"status": "rejected"},
                user_id=rejected_by,
            )
        except Exception:
            logger.exception("Ignored exception")

        db.flush()
        return reconciliation

    def get_reconciliation_report(
        self,
        db: Session,
        organization_id: UUID,
        reconciliation_id: UUID,
    ) -> dict:
        """Generate reconciliation report data."""
        reconciliation = self._get_for_org(db, organization_id, reconciliation_id)  # type: ignore[attr-defined]

        # Get all lines
        lines = reconciliation.lines

        matched_items = [l for l in lines if l.is_cleared and not l.is_adjustment]
        adjustments = [l for l in lines if l.is_adjustment]
        outstanding = [l for l in lines if l.is_outstanding]

        return {
            "reconciliation": reconciliation,
            "bank_account": reconciliation.bank_account,
            "summary": {
                "statement_balance": reconciliation.statement_closing_balance,
                "gl_balance": reconciliation.gl_closing_balance,
                "adjusted_book_balance": reconciliation.adjusted_book_balance,
                "difference": reconciliation.reconciliation_difference,
                "is_reconciled": reconciliation.is_reconciled,
            },
            "matched_items": {
                "count": len(matched_items),
                "total": sum(l.statement_amount or Decimal("0") for l in matched_items),
                "items": matched_items,
            },
            "adjustments": {
                "count": len(adjustments),
                "total": sum(l.statement_amount or Decimal("0") for l in adjustments),
                "items": adjustments,
            },
            "outstanding_deposits": {
                "count": len(
                    [o for o in outstanding if o.outstanding_type == "deposit"]
                ),
                "total": reconciliation.outstanding_deposits,
                "items": [o for o in outstanding if o.outstanding_type == "deposit"],
            },
            "outstanding_payments": {
                "count": len(
                    [o for o in outstanding if o.outstanding_type == "payment"]
                ),
                "total": reconciliation.outstanding_payments,
                "items": [o for o in outstanding if o.outstanding_type == "payment"],
            },
        }
