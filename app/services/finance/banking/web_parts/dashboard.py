"""BankingDashboardWebService component."""

from __future__ import annotations

from app.services.finance.banking.web_parts.base import (
    Any,
    BankAccount,
    BankAccountStatus,
    BankReconciliation,
    BankStatementLine,
    Decimal,
    HTMLResponse,
    JournalEntry,
    JournalEntryLine,
    JournalStatus,
    ReconciliationStatus,
    Request,
    Session,
    UUID,
    WebAuthContext,
    _format_currency,
    _format_date,
    _gl_line_as_transaction,
    base_context,
    coerce_uuid,
    date,
    func,
    org_context_service,
    resolve_payment_metadata_batch,
    select,
    templates,
)


class BankingDashboardWebService:
    """Banking web service methods for dashboard."""

    @staticmethod
    def dashboard_context(
        db: Session,
        organization_id: str,
    ) -> dict[str, Any]:
        """Build context for the banking dashboard page."""
        org_id = coerce_uuid(organization_id)

        # ── Account totals ──
        accounts = list(
            db.scalars(
                select(BankAccount)
                .where(
                    BankAccount.organization_id == org_id,
                    BankAccount.status == BankAccountStatus.active,
                )
                .order_by(BankAccount.bank_name, BankAccount.account_name)
            ).all()
        )

        total_balance = sum(
            (a.last_statement_balance or Decimal("0") for a in accounts),
            Decimal("0"),
        )

        # ── Unreconciled transaction count ──
        gl_account_ids = [a.gl_account_id for a in accounts if a.gl_account_id]

        unreconciled_count = 0
        if gl_account_ids:
            # Count posted GL lines against bank accounts that are unmatched
            # (no matching bank statement line)
            unreconciled_count = (
                db.scalar(
                    select(func.count(JournalEntryLine.line_id))
                    .join(
                        JournalEntry,
                        JournalEntryLine.journal_entry_id
                        == JournalEntry.journal_entry_id,
                    )
                    .where(
                        JournalEntry.organization_id == org_id,
                        JournalEntry.status == JournalStatus.POSTED,
                        JournalEntryLine.account_id.in_(gl_account_ids),
                        ~JournalEntryLine.line_id.in_(
                            select(BankStatementLine.matched_journal_line_id).where(
                                BankStatementLine.matched_journal_line_id.isnot(None)
                            )
                        ),
                    )
                )
                or 0
            )

        # ── MTD inflows/outflows ──
        today = date.today()
        month_start = today.replace(day=1)
        inflows_mtd = Decimal("0")
        outflows_mtd = Decimal("0")

        if gl_account_ids:
            mtd_row = db.execute(
                select(
                    func.coalesce(
                        func.sum(JournalEntryLine.debit_amount), Decimal("0")
                    ).label("total_debits"),
                    func.coalesce(
                        func.sum(JournalEntryLine.credit_amount), Decimal("0")
                    ).label("total_credits"),
                )
                .join(
                    JournalEntry,
                    JournalEntryLine.journal_entry_id == JournalEntry.journal_entry_id,
                )
                .where(
                    JournalEntry.organization_id == org_id,
                    JournalEntry.status == JournalStatus.POSTED,
                    JournalEntryLine.account_id.in_(gl_account_ids),
                    JournalEntry.entry_date >= month_start,
                    JournalEntry.entry_date <= today,
                )
            ).one()
            # For bank asset accounts: debit = money in, credit = money out
            inflows_mtd = mtd_row.total_debits or Decimal("0")
            outflows_mtd = mtd_row.total_credits or Decimal("0")

        # ── Reconciliation status ──
        recon_counts: dict[ReconciliationStatus, int] = {
            row[0]: row[1]
            for row in db.execute(
                select(
                    BankReconciliation.status,
                    func.count(BankReconciliation.reconciliation_id),
                )
                .where(BankReconciliation.organization_id == org_id)
                .group_by(BankReconciliation.status)
            ).all()
        }

        # ── Recent transactions (last 10) ──
        recent_transactions: list[dict[str, Any]] = []
        if gl_account_ids:
            gl_to_bank: dict[UUID, BankAccount] = {}
            for acct in accounts:
                if acct.gl_account_id and acct.gl_account_id not in gl_to_bank:
                    gl_to_bank[acct.gl_account_id] = acct

            txn_stmt = (
                select(JournalEntryLine, JournalEntry)
                .join(
                    JournalEntry,
                    JournalEntryLine.journal_entry_id == JournalEntry.journal_entry_id,
                )
                .where(
                    JournalEntry.organization_id == org_id,
                    JournalEntry.status == JournalStatus.POSTED,
                    JournalEntryLine.account_id.in_(gl_account_ids),
                )
                .order_by(JournalEntry.entry_date.desc())
                .limit(10)
            )
            rows = db.execute(txn_stmt).all()

            # Batch-resolve payment metadata
            metadata_pairs = [
                (
                    getattr(entry, "source_document_type", None),
                    getattr(entry, "source_document_id", None),
                )
                for _line, entry in rows
            ]
            metadata_map = resolve_payment_metadata_batch(db, metadata_pairs)

            for line, entry in rows:
                bank_acct = gl_to_bank.get(line.account_id)
                if not bank_acct:
                    continue
                currency = (
                    bank_acct.currency_code
                    or org_context_service.get_functional_currency(db, org_id)
                )
                doc_id = getattr(entry, "source_document_id", None)
                meta = metadata_map.get(doc_id) if doc_id else None
                txn = _gl_line_as_transaction(line, entry, bank_acct, currency, meta)
                recent_transactions.append(txn)

        # ── Account balances for display ──
        account_balances = [
            {
                "bank_account_id": a.bank_account_id,
                "bank_name": a.bank_name,
                "account_name": a.account_name,
                "account_number": a.account_number,
                "currency_code": a.currency_code,
                "balance": _format_currency(a.last_statement_balance, a.currency_code),
                "last_reconciled_date": _format_date(a.last_reconciled_date),
                "status": a.status.value if a.status else "",
            }
            for a in accounts
        ]

        org_currency = (
            accounts[0].currency_code
            if accounts
            else org_context_service.get_functional_currency(db, org_id)
        )

        return {
            "total_balance": _format_currency(total_balance, org_currency),
            "unreconciled_count": unreconciled_count,
            "inflows_mtd": _format_currency(inflows_mtd, org_currency),
            "outflows_mtd": _format_currency(outflows_mtd, org_currency),
            "recent_transactions": recent_transactions,
            "account_balances": account_balances,
            "account_count": len(accounts),
            "recon_draft": recon_counts.get(ReconciliationStatus.draft, 0),
            "recon_pending_review": recon_counts.get(
                ReconciliationStatus.pending_review, 0
            ),
            "recon_approved": recon_counts.get(ReconciliationStatus.approved, 0),
            "recon_rejected": recon_counts.get(ReconciliationStatus.rejected, 0),
        }

    def dashboard_response(
        self,
        request: Request,
        auth: WebAuthContext,
        db: Session,
    ) -> HTMLResponse:
        """Render the banking dashboard page."""
        context = base_context(request, auth, "Banking", "banking", db=db)
        context.update(self.dashboard_context(db, str(auth.organization_id)))
        return templates.TemplateResponse(
            request, "finance/banking/dashboard.html", context
        )
