"""IAS 7 Cash Flow Statement — indirect method.

Produces a standard statement of cash flows with:
- Operating activities (indirect method: net income + adjustments + working capital)
- Investing activities (asset purchases/disposals)
- Financing activities (loans, equity, lease payments)
- Reconciliation to opening/closing cash balances
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance.gl.account import Account
from app.models.finance.gl.account_category import AccountCategory, IFRSCategory
from app.models.finance.gl.journal_entry import JournalEntry, JournalStatus
from app.models.finance.gl.journal_entry_line import JournalEntryLine
from app.services.common import coerce_uuid
from app.services.finance.rpt.common import (
    _category_balances,
    _format_currency,
    _format_date,
    _iso_date,
    _parse_date,
)

logger = logging.getLogger(__name__)

# ── Classification constants ──────────────────────────────────────────
# source_module values that indicate investing activities
INVESTING_MODULES: frozenset[str] = frozenset({"FA"})

# source_document_type values that are investing activities
INVESTING_DOC_TYPES: frozenset[str] = frozenset(
    {
        "ASSET_ACQUISITION",
        "ASSET_DISPOSAL",
        "ASSET_REVALUATION",
    }
)

# source_document_type values that are financing activities
FINANCING_DOC_TYPES: frozenset[str] = frozenset(
    {
        "LEASE_PAYMENT",
        "INITIAL_RECOGNITION",
        "LEASE_TERMINATION",
    }
)

# Non-cash items to add back (depreciation, amortisation)
NON_CASH_DOC_TYPES: frozenset[str] = frozenset(
    {
        "DEPRECIATION_RUN",
        "ROU_DEPRECIATION",
        "INTEREST_ACCRUAL",
    }
)


def _get_cash_account_ids(
    db: Session, org_id: Any
) -> list[Any]:
    """Get all account IDs for cash/bank accounts."""
    cash_category_ids = list(
        db.scalars(
            select(AccountCategory.category_id).where(
                AccountCategory.organization_id == org_id,
                AccountCategory.category_code.in_({"CASH", "BANK"}),
            )
        ).all()
    )

    if not cash_category_ids:
        return []

    return list(
        db.scalars(
            select(Account.account_id).where(
                Account.organization_id == org_id,
                Account.is_active.is_(True),
                Account.category_id.in_(cash_category_ids),
            )
        ).all()
    )


def _cash_balance_as_of(
    db: Session, org_id: Any, cash_account_ids: list[Any], ref_date: date
) -> Decimal:
    """Sum net cash balance (debit - credit) for cash accounts as of a date."""
    if not cash_account_ids:
        return Decimal("0")

    row = db.execute(
        select(
            func.coalesce(func.sum(JournalEntryLine.debit_amount_functional), 0).label(
                "debit"
            ),
            func.coalesce(
                func.sum(JournalEntryLine.credit_amount_functional), 0
            ).label("credit"),
        )
        .join(
            JournalEntry,
            JournalEntry.journal_entry_id == JournalEntryLine.journal_entry_id,
        )
        .where(
            JournalEntry.organization_id == org_id,
            JournalEntry.status == JournalStatus.POSTED,
            JournalEntry.posting_date <= ref_date,
            JournalEntryLine.account_id.in_(cash_account_ids),
        )
    ).one()

    return Decimal(str(row.debit or 0)) - Decimal(str(row.credit or 0))


def _classify_section(
    source_module: str | None,
    source_document_type: str | None,
) -> str:
    """Classify a journal entry into operating/investing/financing."""
    sdt = source_document_type or ""

    if sdt in NON_CASH_DOC_TYPES:
        return "non_cash_adjustment"

    if sdt in INVESTING_DOC_TYPES or (source_module or "") in INVESTING_MODULES:
        return "investing"

    if sdt in FINANCING_DOC_TYPES:
        return "financing"

    # Default: operating (conservative per IAS 7.14)
    return "operating"


def _cash_movements_by_section(
    db: Session,
    org_id: Any,
    cash_account_ids: list[Any],
    from_date: date,
    to_date: date,
) -> dict[str, list[dict[str, Any]]]:
    """Classify cash movements into IAS 7 sections.

    Queries journal entries that touch cash accounts during the period,
    then classifies each by source_module/source_document_type.
    """
    if not cash_account_ids:
        return {"operating": [], "investing": [], "financing": [], "unclassified": []}

    # Get journal entries that touch cash accounts in the period
    cash_journal_ids_stmt = (
        select(JournalEntryLine.journal_entry_id)
        .where(JournalEntryLine.account_id.in_(cash_account_ids))
        .distinct()
    )

    rows = db.execute(
        select(
            JournalEntry.source_module,
            JournalEntry.source_document_type,
            JournalEntry.description,
            func.coalesce(func.sum(JournalEntryLine.debit_amount_functional), 0).label(
                "debit"
            ),
            func.coalesce(
                func.sum(JournalEntryLine.credit_amount_functional), 0
            ).label("credit"),
        )
        .join(
            JournalEntry,
            JournalEntry.journal_entry_id == JournalEntryLine.journal_entry_id,
        )
        .where(
            JournalEntry.organization_id == org_id,
            JournalEntry.status == JournalStatus.POSTED,
            JournalEntry.posting_date >= from_date,
            JournalEntry.posting_date <= to_date,
            JournalEntryLine.account_id.in_(cash_account_ids),
            JournalEntryLine.journal_entry_id.in_(cash_journal_ids_stmt),
        )
        .group_by(
            JournalEntry.source_module,
            JournalEntry.source_document_type,
            JournalEntry.description,
        )
    ).all()

    sections: dict[str, list[dict[str, Any]]] = {
        "operating": [],
        "investing": [],
        "financing": [],
        "unclassified": [],
    }

    for source_module, source_document_type, description, debit, credit in rows:
        debit = Decimal(str(debit or 0))
        credit = Decimal(str(credit or 0))
        net = debit - credit  # Positive = cash inflow

        section = _classify_section(source_module, source_document_type)

        # Non-cash adjustments don't appear in cash flow sections directly
        if section == "non_cash_adjustment":
            continue

        label = _build_line_label(source_module, source_document_type, description)

        # Unclassified: manual journals with no source info
        if source_module is None and source_document_type is None:
            target = "unclassified"
        else:
            target = section

        sections[target].append(
            {
                "label": label,
                "amount": net,
                "source_module": source_module,
                "source_document_type": source_document_type,
            }
        )

    return sections


def _build_line_label(
    source_module: str | None,
    source_document_type: str | None,
    description: str | None,
) -> str:
    """Build a human-readable line label for the cash flow statement."""
    label_map: dict[str | None, str] = {
        "CUSTOMER_PAYMENT": "Receipts from customers",
        "SUPPLIER_PAYMENT": "Payments to suppliers",
        "EXPENSE_REIMBURSEMENT": "Expense reimbursements",
        "CASH_ADVANCE": "Cash advances",
        "ADVANCE_SETTLEMENT": "Advance settlements",
        "BANK_FEE": "Bank charges",
        "BANK_TRANSFER": "Bank transfers",
        "SALARY_SLIP": "Salary payments",
        "PAYROLL_ENTRY": "Payroll payments",
        "ASSET_ACQUISITION": "Purchase of property, plant and equipment",
        "ASSET_DISPOSAL": "Proceeds from disposal of assets",
        "LEASE_PAYMENT": "Lease payments",
        "LEASE_TERMINATION": "Lease termination",
        "TAX_TRANSACTION": "Tax payments",
        "TRANSFER_FEE": "Transfer fees",
        "EXPENSE_CLAIM": "Expense claims",
    }

    sdt = source_document_type or ""
    if sdt in label_map:
        return label_map[sdt]

    # Fallback to description or generic label
    if description:
        return description[:80]
    if source_module:
        return f"{source_module} transaction"
    return "Other cash movement"


def _aggregate_section_lines(
    lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate section lines by label, summing amounts."""
    aggregated: dict[str, Decimal] = {}
    for line in lines:
        label = line["label"]
        aggregated[label] = aggregated.get(label, Decimal("0")) + line["amount"]

    return [
        {
            "label": label,
            "amount": _format_currency(amount),
            "amount_raw": float(amount),
        }
        for label, amount in aggregated.items()
        if abs(amount) >= Decimal("0.01")
    ]


def ias7_cash_flow_context(
    db: Session,
    organization_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Build context for IAS 7 indirect method cash flow statement."""
    org_id = coerce_uuid(organization_id)
    today = date.today()
    from_date = _parse_date(start_date) or today.replace(day=1)
    to_date = _parse_date(end_date) or today

    # ── Step 1: Net income (accrual basis) ──
    accrual_balances = _category_balances(
        db=db,
        organization_id=organization_id,
        start_date=from_date,
        end_date=to_date,
        basis="accrual",
    )

    def cat_amount(code: str) -> Decimal:
        return Decimal(str(accrual_balances.get(code, {}).get("amount", Decimal("0"))))

    revenue = cat_amount("REV")
    cogs = cat_amount("COS")
    opex = cat_amount("EXP")
    net_income = revenue - cogs - opex

    # ── Step 2: Non-cash adjustments (depreciation, amortisation) ──
    non_cash = _query_non_cash_adjustments(db, org_id, from_date, to_date)
    depreciation = non_cash.get("depreciation", Decimal("0"))
    total_non_cash = depreciation

    # ── Step 3: Working capital changes ──
    # Compare balances at start vs end of period
    opening_day = from_date - timedelta(days=1)

    opening_balances = _category_balances(
        db=db,
        organization_id=organization_id,
        as_of_date=opening_day,
    )
    closing_balances = _category_balances(
        db=db,
        organization_id=organization_id,
        as_of_date=to_date,
    )

    def balance_delta(code: str) -> Decimal:
        opening = Decimal(str(opening_balances.get(code, {}).get("amount", Decimal("0"))))
        closing = Decimal(str(closing_balances.get(code, {}).get("amount", Decimal("0"))))
        return closing - opening

    # For assets: increase = use of cash (negative), decrease = source of cash
    # For liabilities: increase = source of cash (positive)
    ar_change = -balance_delta("AR")  # Negate: increase in AR = cash used
    inv_change = -balance_delta("INV")  # Negate: increase in inventory = cash used
    ap_change = balance_delta("AP")  # Increase in AP = cash source
    total_working_capital = ar_change + inv_change + ap_change

    net_operating = net_income + total_non_cash + total_working_capital

    # ── Step 4: Cash account movements by section ──
    cash_account_ids = _get_cash_account_ids(db, org_id)
    sections = _cash_movements_by_section(
        db, org_id, cash_account_ids, from_date, to_date
    )

    investing_lines = _aggregate_section_lines(sections["investing"])
    financing_lines = _aggregate_section_lines(sections["financing"])
    unclassified_lines = _aggregate_section_lines(sections["unclassified"])

    net_investing = sum(
        (Decimal(str(line["amount_raw"])) for line in investing_lines), Decimal("0")
    )
    net_financing = sum(
        (Decimal(str(line["amount_raw"])) for line in financing_lines), Decimal("0")
    )

    # ── Step 5: Opening and closing cash balances ──
    opening_cash = _cash_balance_as_of(db, org_id, cash_account_ids, opening_day)
    closing_cash = _cash_balance_as_of(db, org_id, cash_account_ids, to_date)

    net_change = net_operating + net_investing + net_financing
    reconciliation_diff = closing_cash - opening_cash - net_change
    is_reconciled = abs(reconciliation_diff) < Decimal("0.01")

    # ── Build working capital detail lines ──
    working_capital_lines = [
        {
            "label": "(Increase)/Decrease in trade receivables",
            "amount": _format_currency(ar_change),
            "amount_raw": float(ar_change),
        },
        {
            "label": "(Increase)/Decrease in inventories",
            "amount": _format_currency(inv_change),
            "amount_raw": float(inv_change),
        },
        {
            "label": "Increase/(Decrease) in trade payables",
            "amount": _format_currency(ap_change),
            "amount_raw": float(ap_change),
        },
    ]

    return {
        "start_date": _format_date(from_date),
        "start_date_iso": _iso_date(from_date),
        "end_date": _format_date(to_date),
        "end_date_iso": _iso_date(to_date),
        # Operating activities (indirect method)
        "net_income": _format_currency(net_income),
        "net_income_raw": float(net_income),
        "is_profit": net_income >= 0,
        "depreciation": _format_currency(depreciation),
        "depreciation_raw": float(depreciation),
        "total_non_cash": _format_currency(total_non_cash),
        "total_non_cash_raw": float(total_non_cash),
        "working_capital_lines": working_capital_lines,
        "total_working_capital": _format_currency(total_working_capital),
        "total_working_capital_raw": float(total_working_capital),
        "net_operating": _format_currency(net_operating),
        "net_operating_raw": float(net_operating),
        # Investing activities
        "investing_lines": investing_lines,
        "net_investing": _format_currency(net_investing),
        "net_investing_raw": float(net_investing),
        # Financing activities
        "financing_lines": financing_lines,
        "net_financing": _format_currency(net_financing),
        "net_financing_raw": float(net_financing),
        # Unclassified (manual journals)
        "unclassified_lines": unclassified_lines,
        "has_unclassified": len(unclassified_lines) > 0,
        # Cash reconciliation
        "net_change": _format_currency(net_change),
        "net_change_raw": float(net_change),
        "opening_cash": _format_currency(opening_cash),
        "opening_cash_raw": float(opening_cash),
        "closing_cash": _format_currency(closing_cash),
        "closing_cash_raw": float(closing_cash),
        "reconciliation_diff": _format_currency(reconciliation_diff),
        "is_reconciled": is_reconciled,
    }


def _query_non_cash_adjustments(
    db: Session, org_id: Any, from_date: date, to_date: date
) -> dict[str, Decimal]:
    """Query depreciation and amortisation amounts for the period."""
    row = db.execute(
        select(
            func.coalesce(func.sum(JournalEntryLine.debit_amount_functional), 0).label(
                "debit"
            ),
            func.coalesce(
                func.sum(JournalEntryLine.credit_amount_functional), 0
            ).label("credit"),
        )
        .join(
            JournalEntry,
            JournalEntry.journal_entry_id == JournalEntryLine.journal_entry_id,
        )
        .join(Account, Account.account_id == JournalEntryLine.account_id)
        .join(AccountCategory, Account.category_id == AccountCategory.category_id)
        .where(
            JournalEntry.organization_id == org_id,
            JournalEntry.status == JournalStatus.POSTED,
            JournalEntry.posting_date >= from_date,
            JournalEntry.posting_date <= to_date,
            JournalEntry.source_document_type.in_(NON_CASH_DOC_TYPES),
            # Only expense-side entries (depreciation expense accounts)
            AccountCategory.ifrs_category == IFRSCategory.EXPENSES,
        )
    ).one()

    debit = Decimal(str(row.debit or 0))
    credit = Decimal(str(row.credit or 0))
    # Depreciation expense = debit - credit (expense accounts are debit-normal)
    return {"depreciation": debit - credit}


def export_ias7_cash_flow_csv(
    organization_id: str,
    db: Session,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Export IAS 7 cash flow statement as CSV."""
    from app.services.finance.rpt.common import _build_csv

    ctx = ias7_cash_flow_context(db, organization_id, start_date, end_date)
    headers = ["Section", "Line Item", "Amount"]
    rows: list[list[str]] = []

    # Operating
    rows.append(["Operating Activities", "Net Income", str(ctx["net_income_raw"])])
    rows.append(["Operating Activities", "Depreciation & Amortisation", str(ctx["depreciation_raw"])])
    for line in ctx["working_capital_lines"]:
        rows.append(["Operating Activities", line["label"], str(line["amount_raw"])])
    rows.append(["Operating Activities", "Net Cash from Operating", str(ctx["net_operating_raw"])])

    # Investing
    for line in ctx["investing_lines"]:
        rows.append(["Investing Activities", line["label"], str(line["amount_raw"])])
    rows.append(["Investing Activities", "Net Cash from Investing", str(ctx["net_investing_raw"])])

    # Financing
    for line in ctx["financing_lines"]:
        rows.append(["Financing Activities", line["label"], str(line["amount_raw"])])
    rows.append(["Financing Activities", "Net Cash from Financing", str(ctx["net_financing_raw"])])

    # Summary
    rows.append(["", "Net Change in Cash", str(ctx["net_change_raw"])])
    rows.append(["", "Opening Cash Balance", str(ctx["opening_cash_raw"])])
    rows.append(["", "Closing Cash Balance", str(ctx["closing_cash_raw"])])

    return _build_csv(headers, rows)
