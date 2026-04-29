"""Reconcile VAT GL accounts to Tax Pro Max FY2025 cash-basis filings.

The org files VAT on cash basis (Section 13a) but the GL is on accrual,
producing a ~₦100M gap at YE2025 between accounts (2120, 1440, 4031) and
the Tax Pro Max filed positions. This reconciliation:

  1. Creates a new account ``2125 Deferred Output VAT`` for the portion of
     output VAT that relates to uncollected receivables (not yet due to FIRS
     under cash-basis filing).
  2. Books one consolidated reconciling journal "RECONCILE-VAT-2025" with
     10 lines that align GL to Tax Pro at YE2025.

Source values:
  * ``2120`` GL balance: NGN 106,090,379 (cumulative output VAT raised, accrual)
  * Tax Pro filed Sales VAT FY2025: NGN 48,273,963
  * Difference (deferred): NGN 57,816,416 → moved to new 2125
  * Tax Pro Input VAT applied: NGN 27,290,000 → CR 1440
  * Tax Pro WHT-VAT applied: NGN 17,391,154 (= full GL 4031 balance) → CR 4031
  * Tax Pro cash paid: NGN 1,783,968 → CR Zenith Bank (1200)
  * AP misclass reversal: NGN 1,415,583 → reverse from 2120 to 1440

Resulting GL position should match Tax Pro within ~NGN 100k:
  * 2120 ≈ 3,224,424 (vs Tax Pro YE outstanding 3,330,322)
  * 2125 = 57,816,416 (new deferred VAT, recognised when receivables collected)
  * 1440 ≈ 5,875,062 (residual unclaimed input VAT credit)
  * 4031 = 0 (fully consumed)
  * 1200 reduced by 1,783,968

Net P&L impact: zero. All movements are balance-sheet reclassifications.

Revision ID: 20260427_reconcile_vat_taxpro
Revises: 20260427_backfill_match_source
Create Date: 2026-04-27
"""

from __future__ import annotations

from alembic import op


revision = "20260427_reconcile_vat_taxpro"
down_revision = "20260427_backfill_match_source"
branch_labels = None
depends_on = None


ORG_ID = "00000000-0000-0000-0000-000000000001"
JOURNAL_NUMBER = "RECONCILE-VAT-2025"


def upgrade() -> None:
    # 1. Create new account 2125 Deferred Output VAT (idempotent).
    op.execute(
        f"""
        INSERT INTO gl.account (
            account_id, organization_id, category_id,
            account_code, account_name, description,
            account_type, normal_balance,
            is_multi_currency,
            is_active, is_posting_allowed, is_budgetable,
            is_reconciliation_required, is_cash_equivalent, is_financial_instrument,
            created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            '{ORG_ID}'::uuid,
            (
                SELECT category_id
                FROM gl.account_category
                WHERE organization_id = '{ORG_ID}'::uuid
                  AND is_active = true
                  AND (
                      category_code = 'TAX-L'
                      OR ifrs_category = 'LIABILITIES'
                  )
                ORDER BY CASE WHEN category_code = 'TAX-L' THEN 0 ELSE 1 END,
                         display_order,
                         created_at
                LIMIT 1
            ),
            '2125',
            'Deferred Output VAT',
            'Output VAT on accrual basis revenue not yet collected from '
            'customers. Under VAT Act Section 13a (cash-basis filing) this '
            'amount is not due to FIRS until the underlying receivables '
            'are paid. Reclassified from 2120 (current VAT Payable) on '
            '2026-04-27 via journal RECONCILE-VAT-2025.',
            'POSTING',
            'CREDIT',
            false,
            true, true, true, false, false, false,
            now(), now()
        WHERE NOT EXISTS (
            SELECT 1 FROM gl.account
            WHERE organization_id = '{ORG_ID}'::uuid
              AND account_code = '2125'
        )
          AND EXISTS (
            SELECT 1
            FROM gl.account_category
            WHERE organization_id = '{ORG_ID}'::uuid
              AND is_active = true
              AND (
                  category_code = 'TAX-L'
                  OR ifrs_category = 'LIABILITIES'
              )
        )
        """
    )

    # 2. Create the reconciliation journal + posting batch + 10 lines + 10
    #    posted ledger lines. Wrapped in a DO block so we can declare local
    #    UUIDs and reuse them across the inserts.
    op.execute(
        f"""
        DO $$
        DECLARE
            v_org UUID := '{ORG_ID}'::uuid;
            v_journal UUID := gen_random_uuid();
            v_batch UUID := gen_random_uuid();
            v_year UUID;
            v_period UUID;
            v_acc_2120 UUID;
            v_acc_2125 UUID;
            v_acc_1440 UUID;
            v_acc_4031 UUID;
            v_acc_1200 UUID;
            v_recon_date DATE := DATE '2026-04-27';
            v_now TIMESTAMPTZ := now();
        BEGIN
            -- Skip if journal already exists (idempotency).
            IF EXISTS (
                SELECT 1 FROM gl.journal_entry
                WHERE organization_id = v_org
                  AND journal_number = '{JOURNAL_NUMBER}'
            ) THEN
                RETURN;
            END IF;

            -- Resolve account UUIDs.
            SELECT account_id INTO v_acc_2120 FROM gl.account
            WHERE organization_id = v_org AND account_code = '2120';
            SELECT account_id INTO v_acc_2125 FROM gl.account
            WHERE organization_id = v_org AND account_code = '2125';
            SELECT account_id INTO v_acc_1440 FROM gl.account
            WHERE organization_id = v_org AND account_code = '1440';
            SELECT account_id INTO v_acc_4031 FROM gl.account
            WHERE organization_id = v_org AND account_code = '4031';
            SELECT account_id INTO v_acc_1200 FROM gl.account
            WHERE organization_id = v_org AND account_code = '1200';

            -- Use the fiscal period that contains the reconciliation date.
            -- If none exists yet, provision a dedicated adjustment period so
            -- the posting stays attached to a valid 2026 GL period.
            SELECT fiscal_period_id, fiscal_year_id
              INTO v_period, v_year
            FROM gl.fiscal_period
            WHERE organization_id = v_org
              AND start_date <= v_recon_date
              AND end_date >= v_recon_date
            ORDER BY
                CASE WHEN status IN ('OPEN', 'REOPENED') THEN 0 ELSE 1 END,
                start_date DESC
            LIMIT 1;

            IF v_year IS NULL THEN
                SELECT fiscal_year_id
                  INTO v_year
                FROM gl.fiscal_year
                WHERE organization_id = v_org
                  AND start_date <= v_recon_date
                  AND end_date >= v_recon_date
                ORDER BY start_date DESC
                LIMIT 1;
            END IF;

            IF v_year IS NULL THEN
                INSERT INTO gl.fiscal_year (
                    fiscal_year_id, organization_id, year_code, year_name,
                    start_date, end_date, is_adjustment_year, is_closed, created_at
                )
                VALUES (
                    gen_random_uuid(), v_org, 'FY2026', 'FY 2026',
                    DATE '2026-01-01', DATE '2026-12-31', false, false, v_now
                )
                ON CONFLICT (organization_id, year_code) DO NOTHING;

                SELECT fiscal_year_id
                  INTO v_year
                FROM gl.fiscal_year
                WHERE organization_id = v_org
                  AND year_code = 'FY2026';
            END IF;

            IF v_period IS NULL THEN
                INSERT INTO gl.fiscal_period (
                    fiscal_period_id, organization_id, fiscal_year_id,
                    period_number, period_name,
                    start_date, end_date,
                    is_adjustment_period, is_closing_period,
                    status, reopen_count, created_at
                )
                VALUES (
                    gen_random_uuid(), v_org, v_year,
                    (
                        SELECT COALESCE(MAX(period_number), 0) + 1
                        FROM gl.fiscal_period
                        WHERE fiscal_year_id = v_year
                    ),
                    'VAT Reconciliation Apr 2026',
                    v_recon_date, v_recon_date,
                    true, false,
                    'OPEN'::period_status, 0, v_now
                );

                SELECT fiscal_period_id
                  INTO v_period
                FROM gl.fiscal_period
                WHERE organization_id = v_org
                  AND fiscal_year_id = v_year
                  AND start_date = v_recon_date
                  AND end_date = v_recon_date
                  AND is_adjustment_period = true
                ORDER BY created_at DESC
                LIMIT 1;
            END IF;

            IF v_period IS NULL THEN
                RAISE EXCEPTION
                    'Unable to resolve or create fiscal period for VAT reconciliation on % (org=%)',
                    v_recon_date,
                    v_org;
            END IF;

            -- Posting batch.
            INSERT INTO gl.posting_batch (
                batch_id, organization_id, fiscal_period_id,
                idempotency_key, source_module, batch_description,
                total_entries, posted_entries, failed_entries,
                status, submitted_at, submitted_by_user_id,
                processing_started_at, completed_at
            ) VALUES (
                v_batch, v_org, v_period,
                'RECONCILE-VAT-2025-' || extract(epoch FROM v_now)::text,
                'GL', 'Reconcile VAT GL to Tax Pro Max FY2025 filings',
                1, 1, 0, 'POSTED', v_now, v_org, v_now, v_now
            );

            -- Journal entry header.
            INSERT INTO gl.journal_entry (
                journal_entry_id, organization_id, journal_number,
                journal_type, entry_date, posting_date, fiscal_period_id,
                description, currency_code, exchange_rate,
                total_debit, total_credit,
                total_debit_functional, total_credit_functional,
                status, posting_batch_id, is_reversal, is_intercompany,
                source_module, source_document_type,
                created_by_user_id, posted_by_user_id, posted_at, created_at, version
            ) VALUES (
                v_journal, v_org, '{JOURNAL_NUMBER}',
                'ADJUSTMENT'::journal_type, '2026-04-27', '2026-04-27', v_period,
                'Reconcile VAT GL to Tax Pro Max FY2025 cash-basis filings. ' ||
                'Defers NGN 57,816,416 VAT on uncollected receivables to new ' ||
                'account 2125; applies Input VAT and WHT-VAT credits used per ' ||
                'monthly returns; records cash remittances; reverses AP misclass.',
                'NGN', 1.0,
                105697121.00, 105697121.00,
                105697121.00, 105697121.00,
                'POSTED', v_batch, false, false,
                'GL', 'RECLASS',
                v_org, v_org, v_now, v_now, 1
            );

            -- 10 journal entry lines + 10 posted ledger lines, expanded
            -- explicitly for audit clarity.
            -- 1. DR 1440 (Input VAT) 1,415,583 — correct AP misclass destination.
            -- 2. CR 2120 (VAT Payable) 1,415,583 — reverse misclass.
            -- 3. DR 2120 57,816,416 — defer accrual VAT.
            -- 4. CR 2125 57,816,416 — recognise deferred VAT.
            -- 5. DR 2120 27,290,000 — apply Input VAT credit.
            -- 6. CR 1440 27,290,000 — reduce Input VAT receivable.
            -- 7. DR 2120 17,391,154 — apply WHT-VAT credit (full balance).
            -- 8. CR 4031 17,391,154 — clear WHT-VAT receivable.
            -- 9. DR 2120 1,783,968 — record cash remittance.
            -- 10. CR 1200 (Zenith Bank) 1,783,968 — bank outflow.

            INSERT INTO gl.journal_entry_line (
                line_id, journal_entry_id, line_number, account_id, description,
                debit_amount, credit_amount, debit_amount_functional,
                credit_amount_functional, currency_code, exchange_rate, created_at
            ) VALUES
                (gen_random_uuid(), v_journal, 1, v_acc_1440,
                 'Reverse misclassified AP invoice VAT (was DR 2120, should be DR 1440)',
                 1415583.00, 0, 1415583.00, 0, 'NGN', 1.0, v_now),
                (gen_random_uuid(), v_journal, 2, v_acc_2120,
                 'Reverse misclassified AP invoice VAT (was DR 2120, should be DR 1440)',
                 0, 1415583.00, 0, 1415583.00, 'NGN', 1.0, v_now),
                (gen_random_uuid(), v_journal, 3, v_acc_2120,
                 'Defer VAT on uncollected receivables (cash-basis filing per Section 13a)',
                 57816416.00, 0, 57816416.00, 0, 'NGN', 1.0, v_now),
                (gen_random_uuid(), v_journal, 4, v_acc_2125,
                 'Recognise Deferred Output VAT — VAT becomes due to FIRS on collection',
                 0, 57816416.00, 0, 57816416.00, 'NGN', 1.0, v_now),
                (gen_random_uuid(), v_journal, 5, v_acc_2120,
                 'Apply Input VAT credit utilized on FY2025 monthly returns',
                 27290000.00, 0, 27290000.00, 0, 'NGN', 1.0, v_now),
                (gen_random_uuid(), v_journal, 6, v_acc_1440,
                 'Reduce Input VAT receivable for credits used (FY2025 returns)',
                 0, 27290000.00, 0, 27290000.00, 'NGN', 1.0, v_now),
                (gen_random_uuid(), v_journal, 7, v_acc_2120,
                 'Apply WHT-VAT (Form A) credits utilized — full GL 4031 balance',
                 17391154.00, 0, 17391154.00, 0, 'NGN', 1.0, v_now),
                (gen_random_uuid(), v_journal, 8, v_acc_4031,
                 'Clear WHT-VAT receivable for credits applied against output VAT',
                 0, 17391154.00, 0, 17391154.00, 'NGN', 1.0, v_now),
                (gen_random_uuid(), v_journal, 9, v_acc_2120,
                 'Record cash remittances to FIRS (Jan-May 2025 monthly payments)',
                 1783968.00, 0, 1783968.00, 0, 'NGN', 1.0, v_now),
                (gen_random_uuid(), v_journal, 10, v_acc_1200,
                 'Bank outflow for FIRS VAT payments (proxy: Zenith Bank, refine if known)',
                 0, 1783968.00, 0, 1783968.00, 'NGN', 1.0, v_now);

            -- Posted ledger lines mirror each journal line.
            INSERT INTO gl.posted_ledger_line (
                ledger_line_id, posting_year, organization_id,
                journal_entry_id, journal_line_id, posting_batch_id,
                fiscal_period_id, account_id, account_code,
                entry_date, posting_date, description,
                debit_amount, credit_amount,
                source_module, source_document_type,
                posted_at, posted_by_user_id
            )
            SELECT
                gen_random_uuid(), 2026, v_org,
                v_journal, jel.line_id, v_batch,
                v_period, jel.account_id, a.account_code,
                '2026-04-27'::date, '2026-04-27'::date, jel.description,
                jel.debit_amount, jel.credit_amount,
                'GL', 'RECLASS',
                v_now, v_org
            FROM gl.journal_entry_line jel
            JOIN gl.account a ON a.account_id = jel.account_id
            WHERE jel.journal_entry_id = v_journal;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        DECLARE
            v_org UUID := '{ORG_ID}'::uuid;
            v_journal UUID;
            v_batch UUID;
            v_acc_2125 UUID;
        BEGIN
            SELECT journal_entry_id, posting_batch_id
              INTO v_journal, v_batch
            FROM gl.journal_entry
            WHERE organization_id = v_org AND journal_number = '{JOURNAL_NUMBER}';

            IF v_journal IS NULL THEN
                RETURN;
            END IF;

            DELETE FROM gl.posted_ledger_line WHERE journal_entry_id = v_journal;
            DELETE FROM gl.journal_entry_line WHERE journal_entry_id = v_journal;
            DELETE FROM gl.journal_entry WHERE journal_entry_id = v_journal;
            DELETE FROM gl.posting_batch WHERE batch_id = v_batch;

            -- Drop the new 2125 account only if it has no other postings.
            SELECT account_id INTO v_acc_2125 FROM gl.account
            WHERE organization_id = v_org AND account_code = '2125';
            IF v_acc_2125 IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1 FROM gl.posted_ledger_line WHERE account_id = v_acc_2125
               )
               AND NOT EXISTS (
                   SELECT 1 FROM gl.journal_entry_line WHERE account_id = v_acc_2125
               ) THEN
                DELETE FROM gl.account WHERE account_id = v_acc_2125;
            END IF;
        END $$;
        """
    )
