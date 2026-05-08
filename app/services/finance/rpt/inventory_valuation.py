"""Inventory valuation reconciliation report context builder."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.services.common import coerce_uuid
from app.services.finance.rpt.common import _format_currency
from app.services.inventory.valuation_reconciliation import (
    ValuationReconciliationService,
)
from app.services.inventory.wac_valuation import WACValuationService


def _format_quantity(value: Decimal) -> str:
    normalized = value.quantize(Decimal("0.000001")).normalize()
    return format(normalized, "f")


def inventory_valuation_reconciliation_context(
    db: Session,
    organization_id: str,
) -> dict[str, Any]:
    """Get context for inventory valuation versus GL reconciliation."""
    org_id = coerce_uuid(organization_id)
    service = ValuationReconciliationService(db)
    try:
        result = service.reconcile(org_id)
        detail_rows = service.detail_rows(org_id, result.fiscal_period_id)
        mismatched_rows = [row for row in detail_rows if not row.is_balanced]
        return {
            "has_data": True,
            "fiscal_period_id": str(result.fiscal_period_id),
            "inventory_total": _format_currency(result.inventory_total),
            "gl_total": _format_currency(result.gl_total),
            "difference": _format_currency(result.difference),
            "difference_raw": float(result.difference),
            "is_balanced": result.is_balanced,
            "valuation_rows": [
                {
                    "item_id": str(row.item_id),
                    "warehouse_id": str(row.warehouse_id),
                    "item_code": row.item_code,
                    "item_name": row.item_name,
                    "warehouse_name": row.warehouse_name,
                    "quantity_on_hand": _format_quantity(row.quantity_on_hand),
                    "current_wac": _format_currency(row.current_wac),
                    "inventory_value": _format_currency(row.inventory_value),
                    "gl_value": _format_currency(row.gl_value),
                    "difference": _format_currency(row.difference),
                    "difference_raw": float(row.difference),
                    "is_balanced": row.is_balanced,
                }
                for row in detail_rows
            ],
            "valuation_row_count": len(detail_rows),
            "valuation_mismatch_count": len(mismatched_rows),
        }
    except ValueError:
        return {
            "has_data": False,
            "fiscal_period_id": "",
            "inventory_total": _format_currency(Decimal("0")),
            "gl_total": _format_currency(Decimal("0")),
            "difference": _format_currency(Decimal("0")),
            "difference_raw": 0.0,
            "is_balanced": True,
            "valuation_rows": [],
            "valuation_row_count": 0,
            "valuation_mismatch_count": 0,
        }


def wac_breakdown_context(
    db: Session,
    organization_id: str,
    *,
    item_id: str,
    warehouse_id: str,
) -> dict[str, Any]:
    """Get context for one item/warehouse WAC breakdown page."""
    org_id = coerce_uuid(organization_id)
    selected_item_id = coerce_uuid(item_id)
    selected_warehouse_id = coerce_uuid(warehouse_id)
    service = ValuationReconciliationService(db)
    result = service.reconcile(org_id)
    detail_rows = service.detail_rows(org_id, result.fiscal_period_id, limit=500)
    selected_row = next(
        (
            row
            for row in detail_rows
            if row.item_id == selected_item_id
            and row.warehouse_id == selected_warehouse_id
        ),
        None,
    )
    if selected_row is None:
        raise ValueError("No valuation row found for selected item and warehouse.")

    breakdown_rows = WACValuationService(db).breakdown_rows(
        org_id,
        selected_item_id,
        selected_warehouse_id,
    )
    return {
        "has_data": True,
        "fiscal_period_id": str(result.fiscal_period_id),
        "item_id": str(selected_row.item_id),
        "warehouse_id": str(selected_row.warehouse_id),
        "item_code": selected_row.item_code,
        "item_name": selected_row.item_name,
        "warehouse_name": selected_row.warehouse_name,
        "quantity_on_hand": _format_quantity(selected_row.quantity_on_hand),
        "current_wac": _format_currency(selected_row.current_wac),
        "inventory_value": _format_currency(selected_row.inventory_value),
        "gl_value": _format_currency(selected_row.gl_value),
        "difference": _format_currency(selected_row.difference),
        "is_balanced": selected_row.is_balanced,
        "wac_breakdown_rows": [
            {
                "transaction_date": row.transaction_date,
                "transaction_type": row.transaction_type.replace("_", " ").title(),
                "reference": row.reference or "-",
                "quantity_in": _format_quantity(row.quantity_in),
                "quantity_out": _format_quantity(row.quantity_out),
                "unit_cost": _format_currency(row.unit_cost),
                "value_in": _format_currency(row.value_in),
                "value_out": _format_currency(row.value_out),
                "quantity_after": _format_quantity(row.quantity_after),
                "wac_after": _format_currency(row.wac_after),
                "total_value_after": _format_currency(row.total_value_after),
            }
            for row in breakdown_rows
        ],
        "wac_breakdown_row_count": len(breakdown_rows),
    }
