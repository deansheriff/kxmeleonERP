"""CategorizationPayeeService component."""

from __future__ import annotations

from app.services.finance.banking.categorization_parts.base import (
    Payee,
    PayeeType,
    Session,
    UUID,
    coerce_uuid,
    datetime,
    or_,
    select,
)


class CategorizationPayeeService:
    """Transaction categorization methods for payees."""

    def create_payee(
        self,
        db: Session,
        organization_id: UUID,
        payee_name: str,
        payee_type: PayeeType = PayeeType.OTHER,
        name_patterns: str | None = None,
        default_account_id: UUID | None = None,
        default_tax_code_id: UUID | None = None,
        supplier_id: UUID | None = None,
        customer_id: UUID | None = None,
        notes: str | None = None,
        created_by: UUID | None = None,
    ) -> Payee:
        """Create a new payee."""
        payee = Payee(
            organization_id=organization_id,
            payee_name=payee_name,
            payee_type=payee_type,
            name_patterns=name_patterns,
            default_account_id=default_account_id,
            default_tax_code_id=default_tax_code_id,
            supplier_id=supplier_id,
            customer_id=customer_id,
            notes=notes,
            created_by=created_by,
        )
        db.add(payee)
        db.flush()
        return payee

    def update_payee(
        self,
        db: Session,
        organization_id: UUID,
        payee_id: UUID,
        **kwargs,
    ) -> Payee | None:
        """Update a payee."""
        org_id = coerce_uuid(organization_id)
        payee = (
            db.execute(
                select(Payee).where(
                    Payee.payee_id == coerce_uuid(payee_id),
                    Payee.organization_id == org_id,
                )
            )
            .scalars()
            .first()
        )
        if not payee:
            return None

        allowed_fields = [
            "payee_name",
            "payee_type",
            "name_patterns",
            "default_account_id",
            "default_tax_code_id",
            "supplier_id",
            "customer_id",
            "notes",
            "is_active",
        ]

        for key, value in kwargs.items():
            if key in allowed_fields:
                setattr(payee, key, value)

        db.flush()
        return payee

    def list_payees(
        self,
        db: Session,
        organization_id: UUID,
        payee_type: PayeeType | None = None,
        is_active: bool | None = True,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Payee]:
        """List payees with filters."""
        stmt = select(Payee).where(Payee.organization_id == organization_id)

        if payee_type:
            stmt = stmt.where(Payee.payee_type == payee_type)
        if is_active is not None:
            stmt = stmt.where(Payee.is_active == is_active)
        if search:
            search_pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Payee.payee_name.ilike(search_pattern),
                    Payee.name_patterns.ilike(search_pattern),
                )
            )

        return list(
            db.execute(stmt.order_by(Payee.payee_name).offset(offset).limit(limit))
            .scalars()
            .all()
        )

    def increment_payee_match(
        self,
        db: Session,
        organization_id: UUID,
        payee_id: UUID,
    ) -> None:
        """Increment match count for a payee."""
        org_id = coerce_uuid(organization_id)
        payee = (
            db.execute(
                select(Payee).where(
                    Payee.payee_id == coerce_uuid(payee_id),
                    Payee.organization_id == org_id,
                )
            )
            .scalars()
            .first()
        )
        if payee:
            payee.match_count += 1
            payee.last_matched_at = datetime.utcnow()
            db.flush()

    # Rule management methods
