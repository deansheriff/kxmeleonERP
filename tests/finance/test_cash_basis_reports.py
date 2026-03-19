"""Tests for cash basis reporting and IAS 7 cash flow classification."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.services.finance.rpt.common import CASH_BASIS_DOC_TYPES
from app.services.finance.rpt.ias7_cash_flow import (
    FINANCING_DOC_TYPES,
    INVESTING_DOC_TYPES,
    INVESTING_MODULES,
    NON_CASH_DOC_TYPES,
    _aggregate_section_lines,
    _build_line_label,
    _classify_section,
)

# ── CASH_BASIS_DOC_TYPES constant tests ──


class TestCashBasisDocTypes:
    def test_contains_expected_types(self):
        assert "CUSTOMER_PAYMENT" in CASH_BASIS_DOC_TYPES
        assert "SUPPLIER_PAYMENT" in CASH_BASIS_DOC_TYPES
        assert "EXPENSE_PAYMENT" in CASH_BASIS_DOC_TYPES
        assert "BANK_TRANSFER" in CASH_BASIS_DOC_TYPES

    def test_excludes_invoice_types(self):
        assert "INVOICE" not in CASH_BASIS_DOC_TYPES
        assert "SUPPLIER_INVOICE" not in CASH_BASIS_DOC_TYPES
        assert "CUSTOMER_INVOICE" not in CASH_BASIS_DOC_TYPES

    def test_is_frozen(self):
        assert isinstance(CASH_BASIS_DOC_TYPES, frozenset)


# ── IAS 7 classification tests ──


class TestClassifySection:
    def test_customer_payment_is_operating(self):
        assert _classify_section("AR", "CUSTOMER_PAYMENT") == "operating"

    def test_supplier_payment_is_operating(self):
        assert _classify_section("AP", "SUPPLIER_PAYMENT") == "operating"

    def test_asset_acquisition_is_investing(self):
        assert _classify_section("FA", "ASSET_ACQUISITION") == "investing"

    def test_asset_disposal_is_investing(self):
        assert _classify_section("FA", "ASSET_DISPOSAL") == "investing"

    def test_fa_module_default_is_investing(self):
        assert _classify_section("FA", "SOME_OTHER_TYPE") == "investing"

    def test_lease_payment_is_financing(self):
        assert _classify_section("LEASE", "LEASE_PAYMENT") == "financing"

    def test_lease_termination_is_financing(self):
        assert _classify_section("LEASE", "LEASE_TERMINATION") == "financing"

    def test_depreciation_is_non_cash(self):
        assert _classify_section("FA", "DEPRECIATION_RUN") == "non_cash_adjustment"

    def test_rou_depreciation_is_non_cash(self):
        assert _classify_section("LEASE", "ROU_DEPRECIATION") == "non_cash_adjustment"

    def test_null_source_is_operating(self):
        assert _classify_section(None, None) == "operating"

    def test_unknown_module_is_operating(self):
        assert _classify_section("UNKNOWN", "UNKNOWN_TYPE") == "operating"

    def test_payroll_is_operating(self):
        assert _classify_section("PAYROLL", "SALARY_SLIP") == "operating"


class TestBuildLineLabel:
    def test_customer_payment_label(self):
        assert _build_line_label("AR", "CUSTOMER_PAYMENT", None) == "Receipts from customers"

    def test_supplier_payment_label(self):
        assert _build_line_label("AP", "SUPPLIER_PAYMENT", None) == "Payments to suppliers"

    def test_asset_acquisition_label(self):
        label = _build_line_label("FA", "ASSET_ACQUISITION", None)
        assert label == "Purchase of property, plant and equipment"

    def test_unknown_type_uses_description(self):
        label = _build_line_label("EXP", "CUSTOM_TYPE", "Monthly office rent")
        assert label == "Monthly office rent"

    def test_no_description_uses_module(self):
        label = _build_line_label("EXP", "CUSTOM_TYPE", None)
        assert label == "EXP transaction"

    def test_no_info_returns_generic(self):
        label = _build_line_label(None, None, None)
        assert label == "Other cash movement"

    def test_long_description_truncated(self):
        long_desc = "A" * 100
        label = _build_line_label(None, "CUSTOM", long_desc)
        assert len(label) <= 80


class TestAggregateSectionLines:
    def test_aggregates_by_label(self):
        lines = [
            {"label": "Receipts from customers", "amount": Decimal("1000")},
            {"label": "Receipts from customers", "amount": Decimal("2000")},
            {"label": "Payments to suppliers", "amount": Decimal("-500")},
        ]
        result = _aggregate_section_lines(lines)
        labels = {r["label"] for r in result}
        assert "Receipts from customers" in labels
        assert "Payments to suppliers" in labels

        customer_line = next(r for r in result if r["label"] == "Receipts from customers")
        assert customer_line["amount_raw"] == 3000.0

    def test_filters_zero_amounts(self):
        lines = [
            {"label": "Zero entry", "amount": Decimal("0.001")},
        ]
        result = _aggregate_section_lines(lines)
        assert len(result) == 0

    def test_empty_input(self):
        result = _aggregate_section_lines([])
        assert result == []


class TestClassificationConstants:
    def test_investing_modules_contains_fa(self):
        assert "FA" in INVESTING_MODULES

    def test_investing_doc_types(self):
        assert "ASSET_ACQUISITION" in INVESTING_DOC_TYPES
        assert "ASSET_DISPOSAL" in INVESTING_DOC_TYPES

    def test_financing_doc_types(self):
        assert "LEASE_PAYMENT" in FINANCING_DOC_TYPES

    def test_non_cash_doc_types(self):
        assert "DEPRECIATION_RUN" in NON_CASH_DOC_TYPES
        assert "ROU_DEPRECIATION" in NON_CASH_DOC_TYPES
        assert "INTEREST_ACCRUAL" in NON_CASH_DOC_TYPES

    def test_no_overlap_between_sets(self):
        """Non-cash types should not appear in investing or financing."""
        assert NON_CASH_DOC_TYPES.isdisjoint(INVESTING_DOC_TYPES)
        assert NON_CASH_DOC_TYPES.isdisjoint(FINANCING_DOC_TYPES)
        assert INVESTING_DOC_TYPES.isdisjoint(FINANCING_DOC_TYPES)


class TestIncomeStatementBasisParam:
    """Test that income_statement_context passes basis through correctly."""

    @patch("app.services.finance.rpt.income_statement._category_balances")
    @patch("app.services.finance.rpt.income_statement.coerce_uuid")
    def test_cash_basis_forwarded(self, mock_coerce, mock_balances):
        from app.services.finance.rpt.income_statement import income_statement_context

        mock_coerce.return_value = "org-123"
        mock_balances.return_value = {}
        db = MagicMock()
        # Mock the fiscal period query
        db.scalars.return_value.first.return_value = None

        ctx = income_statement_context(db, "org-123", basis="cash")
        assert ctx["basis"] == "cash"
        assert ctx["is_cash_basis"] is True

        # Verify _category_balances was called with basis="cash"
        mock_balances.assert_called_once()
        call_kwargs = mock_balances.call_args
        assert call_kwargs.kwargs.get("basis") == "cash" or call_kwargs[1].get("basis") == "cash"

    @patch("app.services.finance.rpt.income_statement._category_balances")
    @patch("app.services.finance.rpt.income_statement.coerce_uuid")
    def test_accrual_basis_default(self, mock_coerce, mock_balances):
        from app.services.finance.rpt.income_statement import income_statement_context

        mock_coerce.return_value = "org-123"
        mock_balances.return_value = {}
        db = MagicMock()
        db.scalars.return_value.first.return_value = None

        ctx = income_statement_context(db, "org-123")
        assert ctx["basis"] == "accrual"
        assert ctx["is_cash_basis"] is False


class TestTrialBalanceBasisParam:
    """Test that trial_balance_context includes basis in context."""

    @patch("app.services.finance.rpt.trial_balance._apply_cash_basis_filter")
    @patch("app.services.finance.rpt.trial_balance.coerce_uuid")
    def test_cash_basis_applies_filter(self, mock_coerce, mock_filter):
        from app.services.finance.rpt.trial_balance import trial_balance_context

        mock_coerce.return_value = "org-123"
        mock_filter.return_value = MagicMock()  # Return modified statement
        db = MagicMock()
        db.scalars.return_value.first.return_value = None
        db.execute.return_value.all.return_value = []

        ctx = trial_balance_context(db, "org-123", basis="cash")
        assert ctx["basis"] == "cash"
        assert ctx["is_cash_basis"] is True
        mock_filter.assert_called_once()

    @patch("app.services.finance.rpt.trial_balance.coerce_uuid")
    def test_accrual_does_not_apply_filter(self, mock_coerce):
        from app.services.finance.rpt.trial_balance import trial_balance_context

        mock_coerce.return_value = "org-123"
        db = MagicMock()
        db.scalars.return_value.first.return_value = None
        db.execute.return_value.all.return_value = []

        ctx = trial_balance_context(db, "org-123", basis="accrual")
        assert ctx["basis"] == "accrual"
        assert ctx["is_cash_basis"] is False
