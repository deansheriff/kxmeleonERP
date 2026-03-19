"""
Shared helpers for financial report context builders.

Contains utility functions and common query patterns used across
multiple report modules.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.finance.gl.account import Account
from app.models.finance.gl.account_category import AccountCategory, IFRSCategory
from app.models.finance.gl.fiscal_period import FiscalPeriod
from app.models.finance.gl.journal_entry import JournalEntry, JournalStatus
from app.models.finance.gl.journal_entry_line import JournalEntryLine
from app.models.finance.rpt.report_definition import ReportType
from app.services.common import coerce_uuid
from app.services.formatters import format_currency as _format_currency
from app.services.formatters import format_date as _format_date
from app.services.formatters import parse_date as _parse_date

# Journal entry types that represent actual cash movement.
# Used to filter GL queries for cash basis reporting.
CASH_BASIS_DOC_TYPES: frozenset[str] = frozenset(
    {
        "CUSTOMER_PAYMENT",
        "SUPPLIER_PAYMENT",
        "EXPENSE_PAYMENT",
        "BANK_TRANSFER",
    }
)

logger = logging.getLogger(__name__)

# Re-export for use by report modules
__all__ = [
    "Account",
    "AccountCategory",
    "CASH_BASIS_DOC_TYPES",
    "FiscalPeriod",
    "IFRSCategory",
    "JournalEntry",
    "JournalEntryLine",
    "JournalStatus",
    "ReportType",
    "coerce_uuid",
    "_format_currency",
    "_format_date",
    "_parse_date",
    "_iso_date",
    "_build_csv",
    "_ifrs_label",
    "_report_type_label",
    "_amount_from_category",
    "_apply_cash_basis_filter",
    "_category_balances",
    "_tax_totals_from_gl",
]


def _iso_date(d: date) -> str:
    """Format date as YYYY-MM-DD for HTML5 date inputs."""
    return d.isoformat()


def _build_csv(headers: list[str], rows: list[list[str]]) -> str:
    """Build a CSV string from headers and rows."""
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue()


def _ifrs_label(category: IFRSCategory | str | None) -> str:
    label_map: dict[IFRSCategory, str] = {
        IFRSCategory.ASSETS: "Assets",
        IFRSCategory.LIABILITIES: "Liabilities",
        IFRSCategory.EQUITY: "Equity",
        IFRSCategory.REVENUE: "Revenue",
        IFRSCategory.EXPENSES: "Expenses",
        IFRSCategory.OTHER_COMPREHENSIVE_INCOME: "Other Comprehensive Income",
    }
    if category is None:
        return ""
    if isinstance(category, str) and not isinstance(category, IFRSCategory):
        try:
            category = IFRSCategory(category)
        except ValueError:
            return category.replace("_", " ").title()
    if isinstance(category, IFRSCategory):
        if category in label_map:
            return label_map[category]
        return str(category.value)
    return category


def _report_type_label(report_type: ReportType) -> str:
    labels: dict[ReportType, str] = {
        ReportType.BALANCE_SHEET: "Statement of Financial Position",
        ReportType.INCOME_STATEMENT: "Statement of Profit or Loss",
        ReportType.CASH_FLOW: "Cash Flow Statement",
        ReportType.CHANGES_IN_EQUITY: "Changes in Equity",
        ReportType.TRIAL_BALANCE: "Trial Balance",
        ReportType.GENERAL_LEDGER: "General Ledger",
        ReportType.SUBLEDGER: "Subledger",
        ReportType.AGING: "Aging Report",
        ReportType.BUDGET_VS_ACTUAL: "Budget vs Actual",
        ReportType.TAX: "Tax Report",
        ReportType.REGULATORY: "Regulatory Report",
        ReportType.CUSTOM: "Custom Report",
    }
    if report_type in labels:
        return labels[report_type]
    return str(report_type.value)


def _amount_from_category(
    ifrs_category: IFRSCategory,
    debit: Decimal,
    credit: Decimal,
) -> Decimal:
    if ifrs_category in {IFRSCategory.ASSETS, IFRSCategory.EXPENSES}:
        return debit - credit
    return credit - debit


def _apply_cash_basis_filter(
    stmt: Any,
    db: Session,
    organization_id: Any,
) -> Any:
    """Restrict a JournalEntry-joined SELECT to cash-movement entries only.

    Includes entries where:
    1. source_document_type is an explicit payment type, OR
    2. The journal touches a cash/bank account (handles manual journals
       with NULL source_document_type).
    """
    cash_category_ids = list(
        db.scalars(
            select(AccountCategory.category_id).where(
                AccountCategory.organization_id == organization_id,
                AccountCategory.category_code.in_({"CASH", "BANK"}),
            )
        ).all()
    )

    # Correlated EXISTS: at least one line touches a cash/bank account
    cash_touch_conditions = [Account.is_cash_equivalent.is_(True)]
    if cash_category_ids:
        cash_touch_conditions.append(Account.category_id.in_(cash_category_ids))

    cash_touch = exists(
        select(JournalEntryLine.line_id)
        .join(Account, Account.account_id == JournalEntryLine.account_id)
        .where(
            JournalEntryLine.journal_entry_id == JournalEntry.journal_entry_id,
            or_(*cash_touch_conditions),
        )
    )

    return stmt.where(
        or_(
            JournalEntry.source_document_type.in_(CASH_BASIS_DOC_TYPES),
            cash_touch,
        )
    )


def _category_balances(
    db: Session,
    organization_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    as_of_date: date | None = None,
    basis: str = "accrual",
) -> dict[str, dict[str, Any]]:
    org_id = coerce_uuid(organization_id)

    stmt = (
        select(
            AccountCategory.category_code,
            AccountCategory.ifrs_category,
            func.coalesce(func.sum(JournalEntryLine.debit_amount_functional), 0).label(
                "debit"
            ),
            func.coalesce(func.sum(JournalEntryLine.credit_amount_functional), 0).label(
                "credit"
            ),
        )
        .join(Account, Account.category_id == AccountCategory.category_id)
        .join(JournalEntryLine, JournalEntryLine.account_id == Account.account_id)
        .join(
            JournalEntry,
            JournalEntry.journal_entry_id == JournalEntryLine.journal_entry_id,
        )
        .where(
            JournalEntry.organization_id == org_id,
            JournalEntry.status == JournalStatus.POSTED,
        )
    )

    if as_of_date:
        stmt = stmt.where(JournalEntry.posting_date <= as_of_date)
    else:
        if start_date:
            stmt = stmt.where(JournalEntry.posting_date >= start_date)
        if end_date:
            stmt = stmt.where(JournalEntry.posting_date <= end_date)

    if basis == "cash":
        stmt = _apply_cash_basis_filter(stmt, db, org_id)

    rows = db.execute(
        stmt.group_by(
            AccountCategory.category_code,
            AccountCategory.ifrs_category,
        )
    ).all()

    balances: dict[str, dict[str, Any]] = {}
    for code, ifrs_category, debit, credit in rows:
        debit = Decimal(str(debit or 0))
        credit = Decimal(str(credit or 0))
        balances[code] = {
            "ifrs_category": ifrs_category,
            "amount": _amount_from_category(ifrs_category, debit, credit),
        }

    return balances


def _tax_totals_from_gl(
    db: Session,
    organization_id: str,
    start_date: date,
    end_date: date,
) -> dict[str, Decimal]:
    """Aggregate tax totals from GL by querying the TAX-L category.

    Groups accounts by name pattern:
    - VAT/Output tax → output_tax (liability, credit-normal)
    - WHT → withholding (liability, credit-normal)
    - Everything else under TAX-L → input_tax proxy
    """
    org_id = coerce_uuid(organization_id)

    rows = db.execute(
        select(
            Account.account_code,
            Account.account_name,
            func.coalesce(func.sum(JournalEntryLine.debit_amount_functional), 0).label(
                "debit"
            ),
            func.coalesce(func.sum(JournalEntryLine.credit_amount_functional), 0).label(
                "credit"
            ),
        )
        .join(AccountCategory, Account.category_id == AccountCategory.category_id)
        .join(JournalEntryLine, JournalEntryLine.account_id == Account.account_id)
        .join(
            JournalEntry,
            JournalEntry.journal_entry_id == JournalEntryLine.journal_entry_id,
        )
        .where(
            JournalEntry.organization_id == org_id,
            JournalEntry.status == JournalStatus.POSTED,
            JournalEntry.posting_date >= start_date,
            JournalEntry.posting_date <= end_date,
            AccountCategory.category_code == "TAX-L",
        )
        .group_by(Account.account_code, Account.account_name)
    ).all()

    output_tax = Decimal("0")
    input_tax = Decimal("0")
    withholding = Decimal("0")

    for _code, name, debit, credit in rows:
        debit = Decimal(str(debit or 0))
        credit = Decimal(str(credit or 0))
        balance = credit - debit  # Liability accounts are credit-normal

        name_lower = (name or "").lower()
        if "vat" in name_lower or "output" in name_lower:
            output_tax += balance
        elif "wht" in name_lower or "withholding" in name_lower:
            withholding += balance
        else:
            # Other tax liabilities (income tax, education tax, etc.)
            input_tax += balance

    net_tax = output_tax - input_tax - withholding

    return {
        "output_tax": output_tax,
        "input_tax": input_tax,
        "withholding": withholding,
        "net_tax": net_tax,
    }
