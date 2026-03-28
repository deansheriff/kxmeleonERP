"""PMS Reports Web Service."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.services.common import coerce_uuid
from app.templates import templates
from app.web.deps import WebAuthContext, base_context


class PMSReportsWebService:
    """Web service for OHCSF PMS reports."""

    def reports_hub_response(
        self, request: Request, auth: WebAuthContext, db: Session
    ) -> HTMLResponse:
        context = base_context(request, auth, "PMS Reports", "perf", db=db)
        return templates.TemplateResponse(
            request, "people/perf/pms/reports.html", context
        )

    def report_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
        report_type: str,
    ) -> HTMLResponse:
        org_id = coerce_uuid(auth.organization_id)
        context = base_context(request, auth, "PMS Report", "perf", db=db)

        from app.services.people.perf.ohcsf_reporting_service import (
            OHCSFReportingService,
        )

        reporting = OHCSFReportingService(db)

        # Find active cycle
        from sqlalchemy import select

        from app.models.people.perf.appraisal_cycle import (
            AppraisalCycle,
            AppraisalCycleStatus,
        )

        active_cycle = db.scalar(
            select(AppraisalCycle)
            .where(
                AppraisalCycle.organization_id == org_id,
                AppraisalCycle.status == AppraisalCycleStatus.ACTIVE,
                AppraisalCycle.cycle_type == "ANNUAL",
            )
            .order_by(AppraisalCycle.start_date.desc())
        )

        report_data: dict | list = {}
        report_title = "Report"

        if active_cycle:
            cycle_id = active_cycle.cycle_id
            report_map = {
                "rating-summary": (
                    "Rating Summary",
                    lambda: reporting.rating_summary(org_id, cycle_id),
                ),
                "by-department": (
                    "Rating by Department",
                    lambda: reporting.rating_by_department(org_id, cycle_id),
                ),
                "by-grade": (
                    "Rating by Grade Level",
                    lambda: reporting.rating_by_grade_level(org_id, cycle_id),
                ),
                "distribution": (
                    "Performance Distribution",
                    lambda: reporting.distribution_org_wide(org_id, cycle_id),
                ),
                "distribution-dept": (
                    "Distribution by Department",
                    lambda: reporting.distribution_by_department(org_id, cycle_id),
                ),
                "distribution-grade": (
                    "Distribution by Grade",
                    lambda: reporting.distribution_by_grade(org_id, cycle_id),
                ),
                "top-performers": (
                    "Top Performers",
                    lambda: reporting.top_performers(org_id, cycle_id),
                ),
                "bottom-performers": (
                    "Bottom Performers",
                    lambda: reporting.bottom_performers(org_id, cycle_id),
                ),
                "development-needs": (
                    "Development Needs",
                    lambda: reporting.development_needs_overview(org_id, cycle_id),
                ),
                "development-dept": (
                    "Development Needs by Department",
                    lambda: reporting.development_needs_by_department(org_id, cycle_id),
                ),
                "compliance": (
                    "Compliance Dashboard",
                    lambda: reporting.cycle_compliance_dashboard(org_id, cycle_id),
                ),
            }

            if report_type in report_map:
                report_title, report_fn = report_map[report_type]
                report_data = report_fn()

        context.update(
            {
                "report_type": report_type,
                "report_title": report_title,
                "report_data": report_data,
                "active_cycle": active_cycle,
            }
        )
        return templates.TemplateResponse(
            request, "people/perf/pms/report_detail.html", context
        )
