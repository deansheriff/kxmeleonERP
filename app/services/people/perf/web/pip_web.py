"""
PIP Web Service — OHCSF Performance Management System.

Handles list, detail, new form, and create responses for
PerformanceImprovementPlan records.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.models.people.perf.pms_enums import PIPCauseCategory, PIPStatus
from app.services.common import PaginationParams, coerce_uuid
from app.services.people.perf.pip_service import (
    PIPService,
)
from app.templates import templates
from app.web.deps import WebAuthContext, base_context

from .base import parse_date, parse_uuid

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PIPWebService:
    """Web service for PIP list, detail, and create views."""

    @staticmethod
    def _form_text(value: object | None, default: str = "") -> str:
        if isinstance(value, str):
            return value.strip()
        return default

    def list_pips_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
        status: str | None = None,
        search: str | None = None,
        page: int = 1,
    ) -> HTMLResponse:
        """Render PIPs list page."""
        org_id = coerce_uuid(auth.organization_id)
        pagination = PaginationParams.from_page(page, per_page=25)
        svc = PIPService(db)

        pip_status: PIPStatus | None = None
        if status:
            try:
                pip_status = PIPStatus(status)
            except ValueError:
                pip_status = None

        result = svc.list_pips(
            org_id,
            status=pip_status,
            search=self._form_text(search) if search else None,
            pagination=pagination,
        )

        context = base_context(request, auth, "Performance Improvement Plans", "perf", db=db)
        context["request"] = request
        context.update(
            {
                "pips": result.items,
                "status": status,
                "search": search,
                "statuses": [s.value for s in PIPStatus],
                "page": result.page,
                "total_pages": result.total_pages,
                "total": result.total,
                "has_prev": result.has_prev,
                "has_next": result.has_next,
            }
        )
        return templates.TemplateResponse(
            request, "people/perf/pms/pips.html", context
        )

    def pip_detail_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
        pip_id: str,
    ) -> HTMLResponse:
        """Render PIP detail page."""
        org_id = coerce_uuid(auth.organization_id)
        svc = PIPService(db)

        pip_uuid = parse_uuid(pip_id)
        if pip_uuid is None:
            context = base_context(request, auth, "PIP Not Found", "perf", db=db)
            context["request"] = request
            context.update({"pip": None, "error": "Invalid PIP ID"})
            return templates.TemplateResponse(
                request, "people/perf/pms/pip_detail.html", context, status_code=404
            )

        try:
            pip = svc.get_pip(org_id, pip_uuid)
        except Exception as e:
            context = base_context(request, auth, "PIP Not Found", "perf", db=db)
            context["request"] = request
            context.update({"pip": None, "error": str(e)})
            return templates.TemplateResponse(
                request, "people/perf/pms/pip_detail.html", context, status_code=404
            )

        context = base_context(
            request, auth, f"PIP {pip.pip_code}", "perf", db=db
        )
        context["request"] = request
        success = request.query_params.get("saved")
        context.update(
            {
                "pip": pip,
                "success": success,
                "improvement_areas": pip.improvement_areas or [],
                "review_intervals": pip.review_intervals or [],
            }
        )
        return templates.TemplateResponse(
            request, "people/perf/pms/pip_detail.html", context
        )

    def pip_new_form_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
    ) -> HTMLResponse:
        """Render new PIP form."""
        org_id = coerce_uuid(auth.organization_id)

        # Load employees for dropdowns
        from app.services.people.hr import EmployeeFilters
        from app.services.people.hr.employees import EmployeeService

        emp_svc = EmployeeService(db, org_id)
        employees = emp_svc.list_employees(
            EmployeeFilters(is_active=True), PaginationParams(limit=500)
        ).items

        context = base_context(request, auth, "New Performance Improvement Plan", "perf", db=db)
        context["request"] = request
        context.update(
            {
                "pip": None,
                "form_data": {},
                "error": None,
                "employees": employees,
                "cause_categories": [c.value for c in PIPCauseCategory],
            }
        )
        return templates.TemplateResponse(
            request, "people/perf/pms/pip_form.html", context
        )

    async def create_pip_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
    ) -> HTMLResponse | RedirectResponse:
        """Handle PIP creation."""
        form_data = await request.form()
        org_id = coerce_uuid(auth.organization_id)
        svc = PIPService(db)

        try:
            start_date = parse_date(self._form_text(form_data.get("start_date")))
            end_date = parse_date(self._form_text(form_data.get("end_date")))
            if not start_date or not end_date:
                raise ValueError("Start and end dates are required")

            employee_id = parse_uuid(self._form_text(form_data.get("employee_id")))
            supervisor_id = parse_uuid(self._form_text(form_data.get("supervisor_id")))
            hr_officer_id = parse_uuid(self._form_text(form_data.get("hr_officer_id")))
            if not employee_id or not supervisor_id or not hr_officer_id:
                raise ValueError("Employee, supervisor, and HR officer are required")

            # Parse improvement areas from form (simple text areas)
            areas_text = self._form_text(form_data.get("improvement_areas"))
            improvement_areas = [
                {"area": line.strip(), "target": ""}
                for line in areas_text.splitlines()
                if line.strip()
            ] if areas_text else []

            pip = svc.create_pip(
                org_id,
                employee_id=employee_id,
                supervisor_id=supervisor_id,
                hr_officer_id=hr_officer_id,
                pip_code=self._form_text(form_data.get("pip_code")),
                start_date=start_date,
                end_date=end_date,
                reason=self._form_text(form_data.get("reason")),
                cause_category=self._form_text(form_data.get("cause_category")),
                improvement_areas=improvement_areas,
                support_measures=self._form_text(form_data.get("support_measures")) or None,
            )
            db.commit()
            return RedirectResponse(
                url=f"/people/perf/pms/pips/{pip.pip_id}?saved=1",
                status_code=303,
            )
        except Exception as e:
            db.rollback()

            from app.services.people.hr import EmployeeFilters
            from app.services.people.hr.employees import EmployeeService

            emp_svc = EmployeeService(db, org_id)
            employees = emp_svc.list_employees(
                EmployeeFilters(is_active=True), PaginationParams(limit=500)
            ).items

            context = base_context(
                request, auth, "New Performance Improvement Plan", "perf", db=db
            )
            context["request"] = request
            context.update(
                {
                    "pip": None,
                    "form_data": dict(form_data),
                    "error": str(e),
                    "employees": employees,
                    "cause_categories": [c.value for c in PIPCauseCategory],
                }
            )
            return templates.TemplateResponse(
                request, "people/perf/pms/pip_form.html", context
            )
