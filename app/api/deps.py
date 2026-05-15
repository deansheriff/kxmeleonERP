from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.rls import enable_rls_bypass_sync
from app.services.auth_dependencies import (
    optional_web_session,
    require_admin_bypass,
    require_audit_auth,
    require_permission,
    require_role,
    require_tenant_auth,
    require_tenant_permission,
    require_tenant_role,
    require_user_auth,
    require_web_session,
)
from app.services.common import coerce_uuid
from app.services.feature_flags import (
    FEATURE_BANK_RECONCILIATION,
    FEATURE_BUDGETING,
    FEATURE_FIXED_ASSETS,
    FEATURE_INVENTORY,
    FEATURE_LEASES,
    FEATURE_MULTI_CURRENCY,
    FEATURE_PROJECT_ACCOUNTING,
    FEATURE_RECURRING_TRANSACTIONS,
    is_feature_enabled,
    require_feature,
)

__all__ = [
    "require_audit_auth",
    "require_permission",
    "require_role",
    "require_user_auth",
    "require_tenant_auth",
    "require_tenant_role",
    "require_tenant_permission",
    "require_organization_id",
    "get_db_admin_bypass",
    "require_current_employee_id",
    "get_current_employee_id_optional",
    "require_admin_bypass",
    "require_web_session",
    "optional_web_session",
    "require_feature",
    "is_feature_enabled",
    "FEATURE_INVENTORY",
    "FEATURE_FIXED_ASSETS",
    "FEATURE_LEASES",
    "FEATURE_BUDGETING",
    "FEATURE_MULTI_CURRENCY",
    "FEATURE_PROJECT_ACCOUNTING",
    "FEATURE_BANK_RECONCILIATION",
    "FEATURE_RECURRING_TRANSACTIONS",
]


def _get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_admin_bypass():
    """DB session dependency for genuinely cross-tenant admin routes.

    Yields a Session that bypasses tenant scoping at *both* layers:
    - PostgreSQL: ``SET LOCAL app.bypass_rls = 'true'`` makes the RLS
      policies return rows regardless of GUC (the policies are
      ``should_bypass_rls() OR organization_id = get_current_org_id()``).
    - Python: ``session.info["allow_cross_org"] = True`` tells the
      ``do_orm_execute`` listener (when enabled) to skip its
      WHERE-injection — otherwise it would raise
      MissingOrgContextError on every org-scoped SELECT.

    Use only for routes that genuinely operate across all tenants:
    super-admin audit log views, system maintenance endpoints, etc.
    Routes that operate within a single org should depend on
    ``get_db_with_org`` instead — they get RLS protection for free.

    Caller is responsible for authentication: this dep doesn't require
    or check auth on its own. Pair with ``require_audit_auth`` or a
    similar admin gate in the route signature.

    Auto-commits on successful yield, rolls back on exception.
    """
    db = SessionLocal()
    try:
        enable_rls_bypass_sync(db)
        db.info["allow_cross_org"] = True
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def require_organization_id(auth: dict = Depends(require_tenant_auth)) -> UUID:
    """Return the authenticated user's organization_id as a UUID."""
    organization_id = auth.get("organization_id")
    if not organization_id:
        raise HTTPException(status_code=403, detail="Organization access required")
    return UUID(organization_id)


def require_current_employee_id(
    auth: dict = Depends(require_tenant_auth),
    db: Session = Depends(_get_db),
) -> UUID:
    """
    Return the employee_id for the authenticated user.

    Looks up the Employee record linked to the current Person (user).
    Raises 403 if the user is not linked to an employee record.
    """
    from app.models.people.hr.employee import Employee

    person_id = auth.get("person_id")
    if not person_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    person_uuid = coerce_uuid(person_id)
    employee = db.scalar(select(Employee).where(Employee.person_id == person_uuid))
    if not employee:
        raise HTTPException(
            status_code=403, detail="No employee record linked to this user account"
        )
    return employee.employee_id


def get_current_employee_id_optional(
    auth: dict = Depends(require_tenant_auth),
    db: Session = Depends(_get_db),
) -> UUID | None:
    """
    Return the employee_id for the authenticated user, or None if not linked.

    Used for endpoints where employee_id is optional (e.g., admin actions).
    """
    from app.models.people.hr.employee import Employee

    person_id = auth.get("person_id")
    if not person_id:
        return None

    person_uuid = coerce_uuid(person_id)
    employee = db.scalar(select(Employee).where(Employee.person_id == person_uuid))
    return employee.employee_id if employee else None
