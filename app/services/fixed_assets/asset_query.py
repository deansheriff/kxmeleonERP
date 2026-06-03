"""
Shared fixed asset query builder for list + export.
"""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.models.fixed_assets.asset import Asset, AssetStatus
from app.models.fixed_assets.asset_category import AssetCategory
from app.models.finance.core_org.location import Location
from app.services.common import coerce_uuid


def _try_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return cast(UUID, coerce_uuid(value, raise_http=False))
    except (TypeError, ValueError):
        return None


def _parse_status(value: str | None) -> AssetStatus | None:
    if not value:
        return None
    try:
        return AssetStatus(value)
    except ValueError:
        try:
            return AssetStatus(value.upper())
        except ValueError:
            return None


def build_asset_query(
    db: Session,
    organization_id: str,
    search: str | None = None,
    category: str | None = None,
    status: str | None = None,
    location: str | None = None,
) -> Select:
    """
    Build the base asset query with filters applied.
    """
    org_id = coerce_uuid(organization_id)
    status_value = _parse_status(status)
    category_id = _try_uuid(category)
    location_id = _try_uuid(location)

    query = (
        select(Asset)
        .join(AssetCategory, Asset.category_id == AssetCategory.category_id)
        .outerjoin(Location, Asset.location_id == Location.location_id)
    )
    query = query.where(Asset.organization_id == org_id)

    if status_value:
        query = query.where(Asset.status == status_value)
    if category_id:
        query = query.where(Asset.category_id == category_id)
    elif category:
        query = query.where(AssetCategory.category_code == category)
    if location_id:
        query = query.where(Asset.location_id == location_id)
    elif location:
        query = query.where(Location.location_code == location)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Asset.asset_number.ilike(search_pattern),
                Asset.asset_name.ilike(search_pattern),
                Asset.serial_number.ilike(search_pattern),
                Asset.barcode.ilike(search_pattern),
            )
        )

    return query


def build_employee_assigned_assets_query(
    organization_id: str | UUID,
    employee_id: str | UUID,
) -> Select:
    """
    Build a tenant-scoped query for assets currently assigned to an employee.
    """
    org_id = coerce_uuid(organization_id)
    custodian_id = coerce_uuid(employee_id)

    return (
        select(Asset)
        .join(AssetCategory, Asset.category_id == AssetCategory.category_id)
        .outerjoin(Location, Asset.location_id == Location.location_id)
        .where(
            Asset.organization_id == org_id,
            Asset.custodian_employee_id == custodian_id,
            Asset.status != AssetStatus.RETIRED,
        )
        .order_by(Asset.asset_number.asc())
    )


def list_employee_assigned_assets(
    db: Session,
    organization_id: str | UUID,
    employee_id: str | UUID,
) -> list[Asset]:
    """
    Return assets currently held by an employee in one organization.
    """
    query = build_employee_assigned_assets_query(organization_id, employee_id)
    return list(db.scalars(query))
