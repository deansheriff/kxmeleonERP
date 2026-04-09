"""
PMS Governance Web Service.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.services.common import PaginationParams, coerce_uuid
from app.services.people.hr import EmployeeFilters
from app.services.people.hr.employees import EmployeeService
from app.services.people.perf.governance_service import PMSGovernanceService
from app.services.people.perf.performance_policy import get_policy_profile
from app.templates import templates
from app.web.deps import WebAuthContext, base_context

from .base import parse_date, parse_uuid

logger = logging.getLogger(__name__)


class GovernanceWebService:
    """Web service for governance, grievances, and stakeholder feedback pages."""

    _deadline_warning_days = 7

    @staticmethod
    def _text(value: object | None) -> str:
        if isinstance(value, str):
            return value.strip()
        return ""

    def _grievance_resolution_deadline(self, grievance: object) -> date | None:
        due_date = getattr(grievance, "due_date", None)
        if isinstance(due_date, date):
            return due_date

        policy = get_policy_profile("GOVERNMENT_PMS")
        cycle_year: int | None = None
        appraisal = getattr(grievance, "appraisal", None)
        cycle = getattr(appraisal, "cycle", None) if appraisal is not None else None
        end_date = getattr(cycle, "end_date", None) if cycle is not None else None
        if end_date is not None:
            cycle_year = end_date.year

        raised_date = getattr(grievance, "raised_date", None)
        base_year = cycle_year if cycle_year is not None else (
            raised_date.year if isinstance(raised_date, date) else None
        )
        if base_year is None:
            return None
        return date(
            base_year + 1,
            policy.resolution_deadline_month,
            policy.resolution_deadline_day,
        )

    def _deadline_meta(self, deadline: date | None, resolved: bool) -> dict[str, object] | None:
        if deadline is None:
            return None
        today = date.today()
        days_remaining = (deadline - today).days
        if resolved:
            state = "resolved"
        elif days_remaining < 0:
            state = "overdue"
        elif days_remaining <= self._deadline_warning_days:
            state = "approaching"
        else:
            state = "on_track"
        return {
            "date": deadline,
            "days_remaining": days_remaining,
            "state": state,
        }

    def governance_dashboard_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
    ) -> HTMLResponse:
        org_id = coerce_uuid(auth.organization_id)
        svc = PMSGovernanceService(db)
        summary = svc.governance_compliance_summary(org_id)
        from sqlalchemy import select

        from app.models.people.perf.institutional_performance import InstitutionalPerformance
        from app.models.people.perf.pms_governance import PMSStakeholderFeedback

        inst_records = list(
            db.scalars(
                select(InstitutionalPerformance).where(
                    InstitutionalPerformance.organization_id == org_id
                )
            ).all()
        )
        workflow_stages = (
            "DRAFT",
            "INTERNAL_REVIEW",
            "CENTRAL_REVIEW",
            "APPROVED",
            "RETURNED",
            "FINAL_SIGNOFF",
        )
        stage_counts = {
            stage: sum(
                1 for record in inst_records if (record.workflow_stage or "DRAFT") == stage
            )
            for stage in workflow_stages
        }
        stage_links = {stage: "/people/perf/pms/institutional" for stage in workflow_stages}
        stage_hints = {
            "DRAFT": "Records waiting to be prepared and submitted.",
            "INTERNAL_REVIEW": "Department reviewers and HR should act here.",
            "CENTRAL_REVIEW": "Central review records awaiting escalation or approval.",
            "APPROVED": "Approved records waiting for final signoff.",
            "RETURNED": "Returned records needing correction and resubmission.",
            "FINAL_SIGNOFF": "Fully signed-off institutional records.",
        }
        feedback_open = len(
            list(
                db.scalars(
                    select(PMSStakeholderFeedback.feedback_id).where(
                        PMSStakeholderFeedback.organization_id == org_id,
                        PMSStakeholderFeedback.status != "CLOSED",
                    )
                ).all()
            )
        )

        context = base_context(request, auth, "PMS Governance", "pms-governance", db=db)
        context.update(
            {
                "summary": summary,
                "stage_counts": stage_counts,
                "stage_links": stage_links,
                "stage_hints": stage_hints,
                "feedback_open": feedback_open,
            }
        )
        return templates.TemplateResponse(
            request,
            "people/perf/pms/governance_dashboard.html",
            context,
        )

    def grievances_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
        status: str | None,
        page: int,
    ) -> HTMLResponse:
        org_id = coerce_uuid(auth.organization_id)
        svc = PMSGovernanceService(db)
        result = svc.list_grievances(
            org_id,
            status=status,
            pagination=PaginationParams.from_page(page, per_page=20),
        )
        context = base_context(request, auth, "PMS Grievances", "pms-grievances", db=db)
        emp_svc = EmployeeService(db, org_id)
        employees = emp_svc.list_employees(
            EmployeeFilters(is_active=True), PaginationParams(limit=500)
        ).items
        deadline_map = {
            str(record.grievance_id): self._deadline_meta(
                self._grievance_resolution_deadline(record),
                resolved=record.status in ("RESOLVED", "ESCALATED"),
            )
            for record in result.items
        }
        context.update(
            {
                "records": result.items,
                "status": status,
                "employees": employees,
                "page": result.page,
                "total_pages": result.total_pages,
                "total": result.total,
                "saved": request.query_params.get("saved"),
                "error": request.query_params.get("error"),
                "deadline_map": deadline_map,
            }
        )
        return templates.TemplateResponse(
            request,
            "people/perf/pms/grievances.html",
            context,
        )

    def grievance_new_form_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
    ) -> HTMLResponse:
        context = base_context(
            request, auth, "New PMS Grievance", "pms-grievances", db=db
        )
        context.update({"error": None, "form_data": {}})
        return templates.TemplateResponse(
            request,
            "people/perf/pms/grievance_form.html",
            context,
        )

    async def grievance_create_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
    ) -> HTMLResponse | RedirectResponse:
        form_data = await request.form()
        org_id = coerce_uuid(auth.organization_id)
        svc = PMSGovernanceService(db)
        try:
            title = self._text(form_data.get("title"))
            description = self._text(form_data.get("description"))
            if not title or not description:
                raise ValueError("Title and description are required")
            if not auth.employee_id:
                raise ValueError("Current user is not linked to an employee profile")

            svc.create_grievance(
                org_id,
                raised_by_employee_id=auth.employee_id,
                title=title,
                description=description,
                channel=self._text(form_data.get("channel")) or "INTERNAL",
                appraisal_id=parse_uuid(self._text(form_data.get("appraisal_id"))),
                inst_perf_id=parse_uuid(self._text(form_data.get("inst_perf_id"))),
            )
            db.commit()
            return RedirectResponse(
                "/people/perf/pms/grievances?saved=1", status_code=303
            )
        except Exception as exc:
            logger.exception("Failed to create governance grievance")
            db.rollback()
            context = base_context(
                request, auth, "New PMS Grievance", "pms-grievances", db=db
            )
            context.update({"error": str(exc), "form_data": dict(form_data)})
            return templates.TemplateResponse(
                request,
                "people/perf/pms/grievance_form.html",
                context,
            )

    async def assign_grievance_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
        grievance_id: str,
    ) -> RedirectResponse:
        form_data = await request.form()
        org_id = coerce_uuid(auth.organization_id)
        svc = PMSGovernanceService(db)
        try:
            assigned_to_id = parse_uuid(
                self._text(form_data.get("assigned_to_employee_id"))
            )
            if assigned_to_id is None:
                raise ValueError("Assigned employee is required")
            svc.assign_grievance(
                org_id,
                grievance_id=coerce_uuid(grievance_id),
                assigned_to_employee_id=assigned_to_id,
                due_date=parse_date(self._text(form_data.get("due_date"))),
            )
            db.commit()
            return RedirectResponse(
                "/people/perf/pms/grievances?saved=1", status_code=303
            )
        except Exception as exc:
            db.rollback()
            logger.exception("Failed to assign grievance %s", grievance_id)
            return RedirectResponse(
                f"/people/perf/pms/grievances?error={str(exc)}",
                status_code=303,
            )

    async def resolve_grievance_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
        grievance_id: str,
    ) -> RedirectResponse:
        form_data = await request.form()
        org_id = coerce_uuid(auth.organization_id)
        svc = PMSGovernanceService(db)
        try:
            resolution_notes = self._text(form_data.get("resolution_notes"))
            svc.resolve_grievance(
                org_id,
                grievance_id=coerce_uuid(grievance_id),
                resolution_notes=resolution_notes,
            )
            db.commit()
            return RedirectResponse(
                "/people/perf/pms/grievances?saved=1", status_code=303
            )
        except Exception as exc:
            db.rollback()
            logger.exception("Failed to resolve grievance %s", grievance_id)
            return RedirectResponse(
                f"/people/perf/pms/grievances?error={str(exc)}",
                status_code=303,
            )

    async def escalate_grievance_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
        grievance_id: str,
    ) -> RedirectResponse:
        form_data = await request.form()
        org_id = coerce_uuid(auth.organization_id)
        svc = PMSGovernanceService(db)
        try:
            escalation_notes = self._text(form_data.get("escalation_notes"))
            svc.escalate_grievance_to_fcsc(
                org_id,
                grievance_id=coerce_uuid(grievance_id),
                escalation_notes=escalation_notes or None,
            )
            db.commit()
            return RedirectResponse(
                "/people/perf/pms/grievances?saved=1", status_code=303
            )
        except Exception as exc:
            db.rollback()
            logger.exception("Failed to escalate grievance %s", grievance_id)
            return RedirectResponse(
                f"/people/perf/pms/grievances?error={str(exc)}",
                status_code=303,
            )

    def feedback_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
        status: str | None,
        page: int,
    ) -> HTMLResponse:
        org_id = coerce_uuid(auth.organization_id)
        svc = PMSGovernanceService(db)
        result = svc.list_stakeholder_feedback(
            org_id,
            status=status,
            pagination=PaginationParams.from_page(page, per_page=20),
        )
        context = base_context(
            request, auth, "Stakeholder Feedback", "pms-stakeholder-feedback", db=db
        )
        context.update(
            {
                "records": result.items,
                "status": status,
                "page": result.page,
                "total_pages": result.total_pages,
                "total": result.total,
            }
        )
        return templates.TemplateResponse(
            request,
            "people/perf/pms/stakeholder_feedback.html",
            context,
        )

    def feedback_new_form_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
    ) -> HTMLResponse:
        context = base_context(
            request,
            auth,
            "New Stakeholder Feedback",
            "pms-stakeholder-feedback",
            db=db,
        )
        context.update({"error": None, "form_data": {}})
        return templates.TemplateResponse(
            request,
            "people/perf/pms/stakeholder_feedback_form.html",
            context,
        )

    async def feedback_create_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
    ) -> HTMLResponse | RedirectResponse:
        form_data = await request.form()
        org_id = coerce_uuid(auth.organization_id)
        svc = PMSGovernanceService(db)
        try:
            title = self._text(form_data.get("title"))
            feedback_text = self._text(form_data.get("feedback_text"))
            if not title or not feedback_text:
                raise ValueError("Title and feedback text are required")

            svc.create_stakeholder_feedback(
                org_id,
                title=title,
                feedback_text=feedback_text,
                source_type=self._text(form_data.get("source_type")) or "SERVICOM",
                channel=self._text(form_data.get("channel")) or "PORTAL",
                submitted_by_name=self._text(form_data.get("submitted_by_name"))
                or None,
                submitted_by_contact=self._text(form_data.get("submitted_by_contact"))
                or None,
                inst_perf_id=parse_uuid(self._text(form_data.get("inst_perf_id"))),
            )
            db.commit()
            return RedirectResponse(
                "/people/perf/pms/stakeholder-feedback?saved=1",
                status_code=303,
            )
        except Exception as exc:
            logger.exception("Failed to create stakeholder feedback")
            db.rollback()
            context = base_context(
                request,
                auth,
                "New Stakeholder Feedback",
                "pms-stakeholder-feedback",
                db=db,
            )
            context.update({"error": str(exc), "form_data": dict(form_data)})
            return templates.TemplateResponse(
                request,
                "people/perf/pms/stakeholder_feedback_form.html",
                context,
            )


governance_web_service = GovernanceWebService()
