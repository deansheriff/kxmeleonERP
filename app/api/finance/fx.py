"""
FX Rate Lookup API — exchange rate endpoint for form auto-fill.

Returns the latest SPOT rate for a given target currency relative to
the organization's functional currency.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select as select  # noqa: F401  # test-mocking seam
from sqlalchemy.orm import Session

from app.api.deps import get_db_with_org, require_tenant_auth
from app.services.common import coerce_uuid
from app.services.finance.platform.fx import FXService

router = APIRouter(prefix="/fx", tags=["fx"])


@router.get("/rate")
def lookup_rate(
    to: str = Query(
        ..., min_length=3, max_length=3, description="Target currency code"
    ),
    rate_date: date | None = Query(
        None, alias="date", description="Effective date (default: today)"
    ),
    auth: dict = Depends(require_tenant_auth),
    db: Session = Depends(get_db_with_org),
) -> dict:
    """
    Look up the latest SPOT exchange rate for a currency pair.

    The 'from' currency is always the organization's functional currency.
    Returns ``{"rate": null}`` when no rate is found (never 404).
    """
    org_id = coerce_uuid(auth["organization_id"])
    return FXService.lookup_spot_rate(db, org_id, to, rate_date)
