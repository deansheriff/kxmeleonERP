"""Programmatic reconciliation engine."""

from __future__ import annotations

from app.services.finance.banking.programmatic_parts.base import (
    Any,
    MatchStrategy,
    ReconciliationRunContext,
    extract_line_signals,
    normalize_statement_line,
)
from app.services.finance.banking.programmatic_parts.payment_strategies import (
    CustomerPaymentReferenceStrategy,
    CustomerReceiptReferenceStrategy,
    PaymentIntentReferenceStrategy,
    SupplierPaymentReferenceStrategy,
    UniqueDateAmountStrategy,
)
from app.services.finance.banking.programmatic_parts.providers import (
    SplynxCustomerPaymentProvider,
)
from app.services.finance.banking.programmatic_parts.special_strategies import (
    BankFeeStrategy,
    ExpenseReimbursementStrategy,
    InterbankCounterpartStrategy,
    LegacyCustomRuleStrategy,
    PayrollEntryStrategy,
)


class ProgrammaticReconciliationEngine:
    def __init__(self) -> None:
        self.strategies: tuple[MatchStrategy, ...] = (
            PaymentIntentReferenceStrategy(),
            CustomerPaymentReferenceStrategy(),
            UniqueDateAmountStrategy(),
            SupplierPaymentReferenceStrategy(),
            CustomerReceiptReferenceStrategy(),
            PayrollEntryStrategy(),
            BankFeeStrategy(),
            InterbankCounterpartStrategy(),
            ExpenseReimbursementStrategy(),
            LegacyCustomRuleStrategy(),
        )

    def run(self, service: Any, ctx: ReconciliationRunContext) -> None:
        ctx.normalized_lines = {
            line.line_id: normalize_statement_line(line) for line in ctx.unmatched_lines
        }
        ctx.line_signals = {
            line_id: extract_line_signals(normalized)
            for line_id, normalized in ctx.normalized_lines.items()
        }
        # Preserve the original query order from AutoReconciliationService:
        # preload Splynx payments once before running the pass sequence.
        SplynxCustomerPaymentProvider().load(service, ctx)

        for strategy in self.strategies:
            if not ctx.still_unmatched_lines():
                break
            strategy.run(service, ctx)
