"""BankingPayeeWebService component."""

from __future__ import annotations

from app.services.finance.banking.web_parts.base import (
    Account,
    Any,
    HTMLResponse,
    HTTPException,
    RedirectResponse,
    Request,
    Response,
    Session,
    UUID,
    WebAuthContext,
    _format_date,
    base_context,
    build_active_filters,
    coerce_uuid,
    func,
    logger,
    or_,
    select,
    templates,
)


class BankingPayeeWebService:
    """Banking web service methods for payees."""

    @staticmethod
    def list_payees_context(
        db: Session,
        organization_id: str,
        search: str | None = None,
        payee_type: str | None = None,
        page: int = 1,
        per_page: int = 25,
    ) -> dict:
        """Context for payees list page."""
        from app.models.finance.banking.payee import Payee, PayeeType

        org_id = coerce_uuid(organization_id)

        conditions: list[Any] = [
            Payee.organization_id == org_id,
            Payee.is_active.is_(True),
        ]

        if search:
            search_pattern = f"%{search}%"
            conditions.append(
                or_(
                    Payee.payee_name.ilike(search_pattern),
                    Payee.name_patterns.ilike(search_pattern),
                )
            )

        if payee_type:
            try:
                pt = PayeeType(payee_type)
                conditions.append(Payee.payee_type == pt)
            except ValueError:
                pass

        total = db.scalar(select(func.count(Payee.payee_id)).where(*conditions)) or 0
        payees = db.scalars(
            select(Payee)
            .where(*conditions)
            .order_by(Payee.payee_name)
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).all()

        # Get GL accounts for display
        account_map = {}
        account_ids = [p.default_account_id for p in payees if p.default_account_id]
        if account_ids:
            accounts = db.scalars(
                select(Account).where(
                    Account.organization_id == org_id,
                    Account.account_id.in_(account_ids),
                )
            ).all()
            account_map = {
                a.account_id: f"{a.account_code} - {a.account_name}" for a in accounts
            }

        payee_list = []
        for p in payees:
            default_account_id = p.default_account_id
            payee_list.append(
                {
                    "payee_id": str(p.payee_id),
                    "payee_name": p.payee_name,
                    "payee_type": p.payee_type.value if p.payee_type else "",
                    "name_patterns": p.name_patterns or "",
                    "default_account": account_map.get(default_account_id, "")
                    if default_account_id
                    else "",
                    "match_count": p.match_count,
                    "last_matched": _format_date(p.last_matched_at)
                    if p.last_matched_at
                    else "Never",
                }
            )

        total_pages = (total + per_page - 1) // per_page
        active_filters = build_active_filters(
            params={"search": search, "payee_type": payee_type},
            labels={"search": "Search", "payee_type": "Type"},
            options={
                "payee_type": {
                    t.value: t.value.replace("_", " ").title() for t in PayeeType
                }
            },
        )
        return {
            "payees": payee_list,
            "payee_types": [
                {"value": t.value, "label": t.value.replace("_", " ").title()}
                for t in PayeeType
            ],
            "search": search or "",
            "payee_type": payee_type or "",
            "selected_type": payee_type or "",
            "active_filters": active_filters,
            "page": page,
            "limit": per_page,
            "total_count": total,
            "total_pages": total_pages,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": total_pages,
            },
        }

    @staticmethod
    def payee_form_context(
        db: Session,
        organization_id: str,
        payee_id: str | None = None,
    ) -> dict:
        """Context for payee create/edit form."""
        from app.models.finance.banking.payee import Payee, PayeeType

        org_id = coerce_uuid(organization_id)

        # Get GL accounts for dropdown (template uses model objects)
        gl_accounts = list(
            db.scalars(
                select(Account)
                .where(
                    Account.organization_id == org_id,
                    Account.is_active.is_(True),
                )
                .order_by(Account.account_code)
            ).all()
        )

        # Tax codes for dropdown
        from app.models.finance.tax.tax_code import TaxCode

        tax_codes = list(
            db.scalars(
                select(TaxCode)
                .where(
                    TaxCode.organization_id == org_id,
                    TaxCode.is_active.is_(True),
                )
                .order_by(TaxCode.tax_code)
            ).all()
        )

        # Suppliers and customers for optional linking
        from app.models.finance.ap.supplier import Supplier
        from app.models.finance.ar.customer import Customer

        suppliers = list(
            db.scalars(
                select(Supplier)
                .where(Supplier.organization_id == org_id)
                .order_by(Supplier.legal_name)
            ).all()
        )
        customers = list(
            db.scalars(
                select(Customer)
                .where(Customer.organization_id == org_id)
                .order_by(Customer.legal_name)
            ).all()
        )

        payee = None
        if payee_id:
            payee = db.get(Payee, coerce_uuid(payee_id))
            if payee and payee.organization_id != org_id:
                payee = None

        return {
            "payee": payee,
            "is_edit": payee is not None,
            "payee_types": [
                {"value": t.value, "label": t.value.replace("_", " ").title()}
                for t in PayeeType
            ],
            "gl_accounts": gl_accounts,
            "tax_codes": tax_codes,
            "suppliers": suppliers,
            "customers": customers,
        }

    # =========================================================================
    # Transaction Rule Context Methods
    # =========================================================================
    def list_payees_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
        search: str | None,
        payee_type: str | None,
        page: int,
        limit: int = 25,
    ) -> HTMLResponse:
        context = base_context(request, auth, "Payees", "banking", db=db)
        context.update(
            self.list_payees_context(
                db,
                str(auth.organization_id),
                search=search,
                payee_type=payee_type,
                page=page,
                per_page=limit,
            )
        )
        return templates.TemplateResponse(
            request, "finance/banking/payees.html", context
        )

    def payee_new_form_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
    ) -> HTMLResponse:
        context = base_context(request, auth, "New Payee", "banking", db=db)
        context.update(self.payee_form_context(db, str(auth.organization_id)))
        return templates.TemplateResponse(
            request, "finance/banking/payee_form.html", context
        )

    def payee_detail_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
        payee_id: str,
    ) -> HTMLResponse:
        context = base_context(request, auth, "Edit Payee", "banking", db=db)
        context.update(
            self.payee_form_context(
                db,
                str(auth.organization_id),
                payee_id=payee_id,
            )
        )
        return templates.TemplateResponse(
            request, "finance/banking/payee_form.html", context
        )

    async def bulk_export_payees_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
    ) -> Response:
        """Handle bulk export payees request."""
        from app.schemas.bulk_actions import BulkExportRequest
        from app.services.finance.banking.bulk import get_payee_bulk_service

        body = await request.json()
        req = BulkExportRequest(**body)
        service = get_payee_bulk_service(
            db,
            coerce_uuid(auth.organization_id),
            coerce_uuid(auth.user_id),
        )
        return await service.bulk_export(req.ids, req.format)

    async def export_all_payees_response(
        self,
        auth: WebAuthContext,
        db: Session,
        search: str = "",
        payee_type: str = "",
    ) -> Response:
        """Export all payees matching filters."""
        from app.services.finance.banking.bulk import get_payee_bulk_service

        service = get_payee_bulk_service(
            db,
            coerce_uuid(auth.organization_id),
            coerce_uuid(auth.user_id),
        )
        extra_filters: dict[str, str] = {}
        if payee_type:
            extra_filters["payee_type"] = payee_type
        return await service.export_all(
            search=search, extra_filters=extra_filters if extra_filters else None
        )

    async def create_payee_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
    ) -> Response:
        """Handle POST to create a new payee from form data."""
        from app.models.finance.banking.payee import Payee, PayeeType

        org_id = auth.organization_id
        user_id = auth.user_id
        if org_id is None:
            raise HTTPException(status_code=401, detail="Authentication required")

        form = await request.form()
        try:
            payee = Payee(
                organization_id=coerce_uuid(org_id),
                payee_name=str(form.get("payee_name", "")),
                payee_type=PayeeType(str(form.get("payee_type", "OTHER"))),
                is_active="is_active" in form,
                name_patterns=str(form.get("name_patterns", "")) or None,
                default_account_id=UUID(str(form["default_account_id"]))
                if form.get("default_account_id")
                else None,
                default_tax_code_id=UUID(str(form["default_tax_code_id"]))
                if form.get("default_tax_code_id")
                else None,
                supplier_id=UUID(str(form["supplier_id"]))
                if form.get("supplier_id")
                else None,
                customer_id=UUID(str(form["customer_id"]))
                if form.get("customer_id")
                else None,
                notes=str(form.get("notes", "")) or None,
                created_by=coerce_uuid(user_id) if user_id else None,
            )
            db.add(payee)
            db.flush()
            db.commit()
            logger.info("Created payee %s: %s", payee.payee_id, payee.payee_name)
            return RedirectResponse(
                url="/finance/banking/payees",
                status_code=303,
            )
        except (ValueError, RuntimeError) as exc:
            logger.warning("Payee creation failed: %s", exc)
            return RedirectResponse(
                url=f"/finance/banking/payees/new?error={exc}",
                status_code=303,
            )

    async def update_payee_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
        payee_id: str,
    ) -> Response:
        """Handle POST to update an existing payee from form data."""
        from app.models.finance.banking.payee import Payee, PayeeType

        org_id = auth.organization_id
        if org_id is None:
            raise HTTPException(status_code=401, detail="Authentication required")

        form = await request.form()
        payee = db.get(Payee, coerce_uuid(payee_id))
        if not payee or payee.organization_id != coerce_uuid(org_id):
            raise HTTPException(status_code=404, detail="Payee not found")

        try:
            payee.payee_name = str(form.get("payee_name", payee.payee_name))
            ptype_raw = str(form.get("payee_type", ""))
            if ptype_raw:
                payee.payee_type = PayeeType(ptype_raw)
            payee.is_active = "is_active" in form
            payee.name_patterns = str(form.get("name_patterns", "")) or None
            payee.default_account_id = (
                UUID(str(form["default_account_id"]))
                if form.get("default_account_id")
                else None
            )
            payee.default_tax_code_id = (
                UUID(str(form["default_tax_code_id"]))
                if form.get("default_tax_code_id")
                else None
            )
            payee.supplier_id = (
                UUID(str(form["supplier_id"])) if form.get("supplier_id") else None
            )
            payee.customer_id = (
                UUID(str(form["customer_id"])) if form.get("customer_id") else None
            )
            payee.notes = str(form.get("notes", "")) or None
            db.commit()
            logger.info("Updated payee %s: %s", payee.payee_id, payee.payee_name)
            return RedirectResponse(
                url="/finance/banking/payees",
                status_code=303,
            )
        except (ValueError, RuntimeError) as exc:
            logger.warning("Payee update failed: %s", exc)
            return RedirectResponse(
                url=f"/finance/banking/payees/{payee_id}?error={exc}",
                status_code=303,
            )

    # =========================================================================
    # Dashboard
    # =========================================================================
