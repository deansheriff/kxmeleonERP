"""Tests for WAC valuation and reconciliation services."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.models.inventory.inventory_transaction import TransactionType
from app.models.inventory.item import CostingMethod
from app.services.inventory.valuation_reconciliation import (
    ValuationReconciliationService,
)
from app.services.inventory.wac_valuation import WACRebuildRow, WACValuationService


def test_wac_receipt_calculation():
    service = WACValuationService(MagicMock())

    with patch.object(
        service,
        "get_snapshot",
        return_value=SimpleNamespace(
            quantity=Decimal("100"),
            wac=Decimal("10"),
            total_value=Decimal("1000"),
        ),
    ):
        result = service.calculate_receipt_cost(
            uuid4(),
            uuid4(),
            uuid4(),
            receipt_qty=Decimal("50"),
            receipt_unit_cost=Decimal("16"),
        )

    assert result.new_wac == Decimal("12.000000")
    assert result.new_balance_qty == Decimal("150")
    assert result.new_balance_value == Decimal("1800.000000")


def test_wac_issue_uses_current_wac():
    service = WACValuationService(MagicMock())

    with patch.object(
        service,
        "get_snapshot",
        return_value=SimpleNamespace(
            quantity=Decimal("150"),
            wac=Decimal("12"),
            total_value=Decimal("1800"),
        ),
    ):
        result = service.calculate_issue_cost(
            uuid4(),
            uuid4(),
            uuid4(),
            issue_qty=Decimal("30"),
        )

    assert result.unit_cost == Decimal("12")
    assert result.new_wac == Decimal("12")
    assert result.total_cost == Decimal("360.000000")
    assert result.new_balance_qty == Decimal("120")


def test_wac_issue_insufficient_stock_raises():
    service = WACValuationService(MagicMock())

    with patch.object(
        service,
        "get_snapshot",
        return_value=SimpleNamespace(
            quantity=Decimal("10"),
            wac=Decimal("100"),
            total_value=Decimal("1000"),
        ),
    ):
        with pytest.raises(ValueError, match="Insufficient stock"):
            service.calculate_issue_cost(
                uuid4(),
                uuid4(),
                uuid4(),
                issue_qty=Decimal("20"),
            )


def test_reconciliation_uses_latest_period_when_unspecified():
    org_id = uuid4()
    period_id = uuid4()
    db = MagicMock()
    db.scalar.side_effect = [
        period_id,  # latest period id
        date(2026, 3, 31),  # period end date
        Decimal("1200.00"),  # inventory total
        Decimal("1000.00"),  # gl total
    ]
    service = ValuationReconciliationService(db)

    result = service.reconcile(org_id)

    assert result.fiscal_period_id == period_id
    assert result.inventory_total == Decimal("1200.00")
    assert result.gl_total == Decimal("1000.00")
    assert result.difference == Decimal("200.00")
    assert result.is_balanced is False


def test_latest_period_prefers_most_recent_inventory_balance_period():
    org_id = uuid4()
    period_with_inventory = uuid4()
    db = MagicMock()
    db.scalar.side_effect = [
        period_with_inventory,  # latest inventory-backed period
        date(2026, 3, 31),  # period end date
        Decimal("1200.00"),  # inventory total
        Decimal("1000.00"),  # gl total
    ]
    service = ValuationReconciliationService(db)

    result = service.reconcile(org_id)

    assert result.fiscal_period_id == period_with_inventory
    assert result.gl_total == Decimal("1000.00")


def test_build_rebuild_rows_replays_receipts_and_issues():
    org_id = uuid4()
    item_id = uuid4()
    warehouse_id = uuid4()
    item = SimpleNamespace(costing_method=CostingMethod.WEIGHTED_AVERAGE)

    receipt_1 = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_type=TransactionType.RECEIPT,
        quantity_before=Decimal("0"),
        quantity_after=Decimal("10"),
        quantity=Decimal("10"),
        total_cost=Decimal("100"),
    )
    receipt_2 = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_type=TransactionType.RECEIPT,
        quantity_before=Decimal("10"),
        quantity_after=Decimal("15"),
        quantity=Decimal("5"),
        total_cost=Decimal("75"),
    )
    issue = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_type=TransactionType.ISSUE,
        quantity_before=Decimal("15"),
        quantity_after=Decimal("12"),
        quantity=Decimal("3"),
        total_cost=Decimal("35"),
    )

    rows = WACValuationService._build_rebuild_rows(
        [(receipt_1, item), (receipt_2, item), (issue, item)]
    )

    assert rows == [
        WACRebuildRow(
            organization_id=org_id,
            item_id=item_id,
            warehouse_id=warehouse_id,
            quantity_on_hand=Decimal("12.000000"),
            current_wac=Decimal("11.666667"),
            total_value=Decimal("140.000000"),
            last_transaction_id=issue.transaction_id,
            transaction_count=3,
        )
    ]


def test_build_rebuild_rows_uses_stored_issue_cost():
    org_id = uuid4()
    item_id = uuid4()
    warehouse_id = uuid4()
    item = SimpleNamespace(costing_method=CostingMethod.WEIGHTED_AVERAGE)

    receipt = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_type=TransactionType.RECEIPT,
        quantity_before=Decimal("0"),
        quantity_after=Decimal("10"),
        quantity=Decimal("10"),
        total_cost=Decimal("100"),
    )
    issue = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_type=TransactionType.ISSUE,
        quantity_before=Decimal("10"),
        quantity_after=Decimal("8"),
        quantity=Decimal("2"),
        total_cost=Decimal("30"),
    )

    rows = WACValuationService._build_rebuild_rows([(receipt, item), (issue, item)])

    assert rows[0].quantity_on_hand == Decimal("8.000000")
    assert rows[0].total_value == Decimal("70.000000")
    assert rows[0].current_wac == Decimal("8.750000")


def test_build_breakdown_rows_returns_running_wac_trail():
    org_id = uuid4()
    item_id = uuid4()
    warehouse_id = uuid4()
    item = SimpleNamespace(costing_method=CostingMethod.WEIGHTED_AVERAGE)

    receipt = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_date=date(2026, 1, 1),
        transaction_type=TransactionType.RECEIPT,
        quantity_before=Decimal("0"),
        quantity_after=Decimal("10"),
        quantity=Decimal("10"),
        unit_cost=Decimal("10"),
        total_cost=Decimal("100"),
        reference="REC-1",
    )
    receipt_2 = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_date=date(2026, 1, 2),
        transaction_type=TransactionType.RECEIPT,
        quantity_before=Decimal("10"),
        quantity_after=Decimal("15"),
        quantity=Decimal("5"),
        unit_cost=Decimal("16"),
        total_cost=Decimal("80"),
        reference="REC-2",
    )
    issue = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_date=date(2026, 1, 3),
        transaction_type=TransactionType.ISSUE,
        quantity_before=Decimal("15"),
        quantity_after=Decimal("12"),
        quantity=Decimal("3"),
        unit_cost=Decimal("12"),
        total_cost=Decimal("36"),
        reference="ISS-1",
    )

    rows = WACValuationService._build_breakdown_rows(
        [(receipt, item), (receipt_2, item), (issue, item)]
    )

    assert len(rows) == 3
    assert rows[0].quantity_in == Decimal("10")
    assert rows[0].wac_after == Decimal("10.000000")
    assert rows[1].quantity_after == Decimal("15.000000")
    assert rows[1].wac_after == Decimal("12.000000")
    assert rows[2].quantity_out == Decimal("3")
    assert rows[2].value_out == Decimal("36.000000")
    assert rows[2].quantity_after == Decimal("12.000000")
    assert rows[2].total_value_after == Decimal("144.000000")


def test_build_rebuild_rows_falls_back_to_wac_for_zero_cost_issue():
    org_id = uuid4()
    item_id = uuid4()
    warehouse_id = uuid4()
    item = SimpleNamespace(costing_method=CostingMethod.WEIGHTED_AVERAGE)

    receipt = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_type=TransactionType.RECEIPT,
        quantity_before=Decimal("0"),
        quantity_after=Decimal("10"),
        quantity=Decimal("10"),
        total_cost=Decimal("470000"),
    )
    zero_cost_issue = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_type=TransactionType.ISSUE,
        quantity_before=Decimal("10"),
        quantity_after=Decimal("1"),
        quantity=Decimal("9"),
        total_cost=Decimal("0"),
    )

    rows = WACValuationService._build_rebuild_rows(
        [(receipt, item), (zero_cost_issue, item)]
    )

    assert rows[0].quantity_on_hand == Decimal("1.000000")
    assert rows[0].total_value == Decimal("47000.000000")
    assert rows[0].current_wac == Decimal("47000.000000")


def test_build_rebuild_rows_applies_zero_quantity_opening_adjustment():
    org_id = uuid4()
    item_id = uuid4()
    warehouse_id = uuid4()
    item = SimpleNamespace(costing_method=CostingMethod.WEIGHTED_AVERAGE)

    opening = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_type=TransactionType.ADJUSTMENT,
        quantity_before=Decimal("4130"),
        quantity_after=Decimal("4130"),
        quantity=Decimal("0"),
        total_cost=Decimal("1858500"),
    )
    issue = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_type=TransactionType.ISSUE,
        quantity_before=Decimal("4130"),
        quantity_after=Decimal("4129"),
        quantity=Decimal("1"),
        total_cost=Decimal("450"),
    )

    rows = WACValuationService._build_rebuild_rows([(opening, item), (issue, item)])

    assert rows[0].quantity_on_hand == Decimal("4129.000000")
    assert rows[0].total_value == Decimal("1858050.000000")
    assert rows[0].current_wac == Decimal("450.000000")


def test_build_rebuild_rows_zero_quantity_adjustment_resets_value():
    org_id = uuid4()
    item_id = uuid4()
    warehouse_id = uuid4()
    item = SimpleNamespace(costing_method=CostingMethod.WEIGHTED_AVERAGE)

    receipt = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_type=TransactionType.RECEIPT,
        quantity_before=Decimal("0"),
        quantity_after=Decimal("10"),
        quantity=Decimal("10"),
        total_cost=Decimal("100"),
    )
    reconciliation = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_type=TransactionType.ADJUSTMENT,
        quantity_before=Decimal("10"),
        quantity_after=Decimal("10"),
        quantity=Decimal("0"),
        total_cost=Decimal("80"),
    )

    rows = WACValuationService._build_rebuild_rows(
        [(receipt, item), (reconciliation, item)]
    )

    assert rows[0].quantity_on_hand == Decimal("10.000000")
    assert rows[0].total_value == Decimal("80.000000")
    assert rows[0].current_wac == Decimal("8.000000")


def test_build_rebuild_rows_resets_to_zero_when_stock_is_depleted():
    org_id = uuid4()
    item_id = uuid4()
    warehouse_id = uuid4()
    item = SimpleNamespace(costing_method=CostingMethod.WEIGHTED_AVERAGE)

    receipt = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_type=TransactionType.RECEIPT,
        quantity_before=Decimal("0"),
        quantity_after=Decimal("4"),
        quantity=Decimal("4"),
        total_cost=Decimal("40"),
    )
    issue_all = SimpleNamespace(
        organization_id=org_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        transaction_id=uuid4(),
        transaction_type=TransactionType.ISSUE,
        quantity_before=Decimal("4"),
        quantity_after=Decimal("0"),
        quantity=Decimal("4"),
        total_cost=Decimal("40"),
    )

    rows = WACValuationService._build_rebuild_rows([(receipt, item), (issue_all, item)])

    assert rows[0].quantity_on_hand == Decimal("0")
    assert rows[0].current_wac == Decimal("0")
    assert rows[0].total_value == Decimal("0")
