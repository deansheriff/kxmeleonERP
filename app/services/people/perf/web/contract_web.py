"""
Contract Web Service — OHCSF PMS web view service for performance contracts.

Provides view-focused operations for contract list, detail, create, and
signing workflow within the PMS module.
"""

from __future__ import annotations

import json
import logging

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.datastructures import FormData, UploadFile

from app.models.people.perf.pms_enums import ContractStatus, ContractType
from app.services.common import PaginationParams, coerce_uuid
from app.services.people.hr import EmployeeFilters, OrganizationService
from app.services.people.perf import PerformanceService
from app.templates import templates
from app.web.deps import WebAuthContext, base_context

from .base import parse_uuid

logger = logging.getLogger(__name__)


def _get_form_str(form: FormData | None, key: str, default: str = "") -> str:
    if form is None:
        return default
    value = form.get(key, default)
    if isinstance(value, UploadFile) or value is None:
        return default
    return str(value).strip()


class ContractWebService:
    """Web service for OHCSF performance contract pages."""

    # ─────────────────────────────────────────────────────────────────────────
    # List
    # ─────────────────────────────────────────────────────────────────────────

    def list_contracts_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
        status: str | None = None,
        cycle_id: str | None = None,
        search: str | None = None,
        page: int = 1,
    ) -> HTMLResponse:
        """Render the performance contracts list page."""
        org_id = coerce_uuid(auth.organization_id)
        pagination = PaginationParams.from_page(page, per_page=20)

        from app.services.people.perf.contract_service import (
            PerformanceContractService,
        )

        svc = PerformanceContractService(db)
        perf_svc = PerformanceService(db)

        parsed_status: ContractStatus | None = None
        if status:
            try:
                parsed_status = ContractStatus(status)
            except ValueError:
                parsed_status = None

        result = svc.list_contracts(
            org_id,
            status=parsed_status,
            cycle_id=parse_uuid(cycle_id),
            search=search if search else None,
            pagination=pagination,
        )

        cycles = perf_svc.list_cycles(
            org_id, pagination=PaginationParams(limit=100)
        ).items

        context = base_context(request, auth, "Performance Contracts", "perf", db=db)
        context["request"] = request
        context.update(
            {
                "contracts": result.items,
                "status": status,
                "cycle_id": cycle_id,
                "search": search,
                "statuses": [s.value for s in ContractStatus],
                "cycles": cycles,
                "page": result.page,
                "total_pages": result.total_pages,
                "total": result.total,
                "has_prev": result.has_prev,
                "has_next": result.has_next,
            }
        )
        return templates.TemplateResponse(
            request, "people/perf/pms/contracts.html", context
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Detail
    # ─────────────────────────────────────────────────────────────────────────

    def contract_detail_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
        contract_id: str,
        success: str | None = None,
        error: str | None = None,
    ) -> HTMLResponse | RedirectResponse:
        """Render the performance contract detail page."""
        org_id = coerce_uuid(auth.organization_id)

        from app.services.people.perf.contract_service import (
            PerformanceContractService,
        )
        from app.services.people.perf.monthly_review_service import (
            MonthlyReviewService,
        )

        svc = PerformanceContractService(db)
        review_svc = MonthlyReviewService(db)

        try:
            contract = svc.get_contract(org_id, coerce_uuid(contract_id))
        except Exception:
            return RedirectResponse(url="/people/perf/pms/contracts", status_code=303)

        # Fetch linked monthly reviews for the detail view
        reviews = review_svc.list_reviews(
            org_id,
            contract_id=contract.contract_id,
            pagination=PaginationParams(limit=50),
        ).items

        context = base_context(
            request,
            auth,
            f"Contract {contract.contract_code}",
            "perf",
            db=db,
        )
        context["request"] = request
        context.update(
            {
                "contract": contract,
                "reviews": reviews,
                "success": success,
                "error": error,
            }
        )
        return templates.TemplateResponse(
            request, "people/perf/pms/contract_detail.html", context
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Form (create)
    # ─────────────────────────────────────────────────────────────────────────

    def contract_form_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
        cycle_id: str | None = None,
        employee_id: str | None = None,
        form_data: dict | None = None,
        error: str | None = None,
    ) -> HTMLResponse:
        """Render the new performance contract form."""
        org_id = coerce_uuid(auth.organization_id)
        perf_svc = PerformanceService(db)
        org_svc = OrganizationService(db, org_id)

        cycles = perf_svc.list_cycles(
            org_id, pagination=PaginationParams(limit=100)
        ).items
        employees = org_svc.list_employees(
            EmployeeFilters(is_active=True),
            PaginationParams(limit=500),
        ).items

        context = base_context(request, auth, "New Performance Contract", "perf", db=db)
        context["request"] = request
        context.update(
            {
                "contract": None,
                "cycles": cycles,
                "employees": employees,
                "contract_types": [ct.value for ct in ContractType],
                "prefill_cycle_id": cycle_id,
                "prefill_employee_id": employee_id,
                "form_data": form_data or {},
                "error": error,
            }
        )
        return templates.TemplateResponse(
            request, "people/perf/pms/contract_form.html", context
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Create (POST)
    # ─────────────────────────────────────────────────────────────────────────

    async def create_contract_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
    ) -> HTMLResponse | RedirectResponse:
        """Handle performance contract creation."""
        form_data = await request.form()
        org_id = coerce_uuid(auth.organization_id)

        from app.services.people.perf.contract_service import (
            PerformanceContractService,
        )

        svc = PerformanceContractService(db)

        try:
            cycle_id_str = _get_form_str(form_data, "cycle_id")
            employee_id_str = _get_form_str(form_data, "employee_id")
            supervisor_id_str = _get_form_str(form_data, "supervisor_id")
            contract_code = _get_form_str(form_data, "contract_code")
            contract_type_str = _get_form_str(form_data, "contract_type")
            development_plan = _get_form_str(form_data, "development_plan") or None

            if not cycle_id_str:
                raise ValueError("Appraisal cycle is required")
            if not employee_id_str:
                raise ValueError("Employee is required")
            if not supervisor_id_str:
                raise ValueError("Supervisor is required")
            if not contract_code:
                raise ValueError("Contract code is required")
            if not contract_type_str:
                raise ValueError("Contract type is required")

            try:
                contract_type = ContractType(contract_type_str)
            except ValueError:
                raise ValueError(f"Invalid contract type: {contract_type_str}")

            # Parse objectives from JSON textarea
            objectives_raw = _get_form_str(form_data, "objectives_json", "[]")
            try:
                objectives = json.loads(objectives_raw) if objectives_raw else []
            except json.JSONDecodeError:
                raise ValueError("Objectives data is not valid JSON")

            # Parse competency IDs (optional)
            competency_raw = _get_form_str(form_data, "competency_ids_json", "")
            competency_ids = None
            if competency_raw:
                try:
                    competency_ids = json.loads(competency_raw)
                except json.JSONDecodeError:
                    competency_ids = None

            contract = svc.create_contract(
                org_id,
                cycle_id=coerce_uuid(cycle_id_str),
                employee_id=coerce_uuid(employee_id_str),
                supervisor_id=coerce_uuid(supervisor_id_str),
                contract_code=contract_code,
                contract_type=contract_type,
                objectives=objectives,
                competency_ids=competency_ids,
                development_plan=development_plan,
            )
            db.commit()
            return RedirectResponse(
                url=f"/people/perf/pms/contracts/{contract.contract_id}?saved=1",
                status_code=303,
            )
        except Exception as e:
            db.rollback()
            return self.contract_form_response(
                request,
                auth,
                db,
                form_data=dict(form_data),
                error=str(e),
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Sign actions
    # ─────────────────────────────────────────────────────────────────────────

    def sign_employee_response(
        self,
        auth: WebAuthContext,
        db: Session,
        contract_id: str,
    ) -> RedirectResponse:
        """Record employee signature on a contract."""
        org_id = coerce_uuid(auth.organization_id)

        from app.services.people.perf.contract_service import (
            PerformanceContractService,
        )

        svc = PerformanceContractService(db)
        try:
            svc.sign_employee(
                org_id,
                coerce_uuid(contract_id),
                actor_person_id=coerce_uuid(auth.person_id),
            )
            db.commit()
            success_msg = "Employee signature recorded."
        except Exception as e:
            db.rollback()
            logger.warning("Employee sign failed for contract %s: %s", contract_id, e)
            success_msg = None

        return RedirectResponse(
            url=f"/people/perf/pms/contracts/{contract_id}"
            + ("?saved=1" if success_msg else "?error=sign_failed"),
            status_code=303,
        )

    def sign_supervisor_response(
        self,
        auth: WebAuthContext,
        db: Session,
        contract_id: str,
    ) -> RedirectResponse:
        """Record supervisor signature on a contract."""
        org_id = coerce_uuid(auth.organization_id)

        from app.services.people.perf.contract_service import (
            PerformanceContractService,
        )

        svc = PerformanceContractService(db)
        try:
            svc.sign_supervisor(
                org_id,
                coerce_uuid(contract_id),
                actor_person_id=coerce_uuid(auth.person_id),
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("Supervisor sign failed for contract %s: %s", contract_id, e)
            return RedirectResponse(
                url=f"/people/perf/pms/contracts/{contract_id}?error=sign_failed",
                status_code=303,
            )

        return RedirectResponse(
            url=f"/people/perf/pms/contracts/{contract_id}?saved=1",
            status_code=303,
        )
