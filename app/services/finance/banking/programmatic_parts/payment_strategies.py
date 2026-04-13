"""Payment-oriented programmatic reconciliation strategies."""

from __future__ import annotations

from app.services.finance.banking.programmatic_parts.base import (
    Any,
    BankStatementLine,
    Decimal,
    MatchStrategy,
    ReconciliationRunContext,
    StatementLineType,
    dataclass,
)
from app.services.finance.banking.programmatic_parts.helpers import (
    _find_entity_for_line,
    _payment_intent_ref_lookup,
    _perform_match,
    _run_directional_date_amount_match,
    _run_directional_reference_match,
    _splynx_ref_lookup,
)
from app.services.finance.banking.programmatic_parts.providers import (
    CustomerReceiptProvider,
    PaymentIntentProvider,
    SplynxCustomerPaymentProvider,
    SupplierPaymentProvider,
)


@dataclass(frozen=True)
class PaymentIntentReferenceStrategy(MatchStrategy):
    strategy_id: str = "exact_external_reference"
    provider: PaymentIntentProvider = PaymentIntentProvider()
    source_type: str = "payment_intent"

    def run(self, service: Any, ctx: ReconciliationRunContext) -> None:
        if (
            not ctx.policy.allows_strategy(self.strategy_id)
            or not ctx.policy.allows_source_type(self.source_type)
            or not ctx.policy.allows_provider(self.provider.provider_key)
        ):
            return
        intents = self.provider.load(service, ctx)
        if not intents:
            return

        ref_to_intent = _payment_intent_ref_lookup(intents)
        matched_intent_ids = ctx.tracker(self.provider.provider_key)

        for line in ctx.still_unmatched_lines():
            try:
                intent = _find_entity_for_line(ctx, line, ref_to_intent)
                if not intent or intent.intent_id in matched_intent_ids:
                    continue

                tolerance = ctx.config.amount_tolerance if ctx.config else None
                if not service._amounts_match(
                    line.amount, intent.amount, tolerance=tolerance
                ):
                    continue

                journal_line = service._find_journal_line(
                    ctx.db,
                    ctx.organization_id,
                    str(intent.intent_id),
                    ctx.bank_account.gl_account_id,
                    extra_gl_account_ids=ctx.extra_gl_account_ids,
                )
                if not journal_line:
                    continue

                _perform_match(
                    service,
                    ctx,
                    line,
                    journal_line,
                    source_type="PAYMENT_INTENT",
                    source_id=intent.intent_id,
                    confidence=100,
                    explanation=f"Paystack reference {intent.paystack_reference} (exact match)",
                )
                matched_intent_ids.add(intent.intent_id)
            except Exception as exc:
                service.logger.exception(
                    "Error matching line %s via PaymentIntent: %s",
                    line.line_id,
                    exc,
                )
                ctx.result.errors.append(f"Line {line.line_number}: {exc}")

        service._match_expense_intents_by_date_amount(
            ctx.db,
            ctx.organization_id,
            ctx.bank_account,
            intents,
            ctx.unmatched_lines,
            ctx.matched_line_ids,
            matched_intent_ids,
            ctx.result,
            extra_gl_account_ids=ctx.extra_gl_account_ids,
        )


@dataclass(frozen=True)
class CustomerPaymentReferenceStrategy(MatchStrategy):
    strategy_id: str = "exact_synced_receivable_reference"
    provider: SplynxCustomerPaymentProvider = SplynxCustomerPaymentProvider()

    def run(self, service: Any, ctx: ReconciliationRunContext) -> None:
        if (
            not ctx.policy.allows_strategy(self.strategy_id)
            or not ctx.policy.allows_source_type(self.provider.source_type)
            or not ctx.policy.allows_provider(self.provider.provider_key)
        ):
            return
        payments = self.provider.load(service, ctx)
        if not payments:
            return
        ref_to_payment = _splynx_ref_lookup(service, payments)
        matched_payment_ids = ctx.tracker(self.provider.provider_key)

        for line in ctx.still_unmatched_lines():
            try:
                payment = _find_entity_for_line(ctx, line, ref_to_payment)
                if not payment or payment.payment_id in matched_payment_ids:
                    continue

                tolerance = ctx.config.amount_tolerance if ctx.config else None
                if not service._amounts_match(
                    line.amount, payment.amount, tolerance=tolerance
                ):
                    continue
                if not payment.correlation_id:
                    continue

                journal_line = service._find_journal_line(
                    ctx.db,
                    ctx.organization_id,
                    payment.correlation_id,
                    ctx.bank_account.gl_account_id,
                    extra_gl_account_ids=ctx.extra_gl_account_ids,
                )
                if not journal_line:
                    continue

                _perform_match(
                    service,
                    ctx,
                    line,
                    journal_line,
                    source_type="CUSTOMER_PAYMENT",
                    source_id=payment.payment_id,
                    confidence=95,
                    explanation=f"Splynx payment {payment.splynx_id} (reference match)",
                )
                matched_payment_ids.add(payment.payment_id)
            except Exception as exc:
                service.logger.exception(
                    "Error matching line %s via Splynx payment: %s",
                    line.line_id,
                    exc,
                )
                ctx.result.errors.append(f"Line {line.line_number}: {exc}")


@dataclass(frozen=True)
class UniqueDateAmountStrategy(MatchStrategy):
    strategy_id: str = "unique_date_amount"
    provider: SplynxCustomerPaymentProvider = SplynxCustomerPaymentProvider()

    def run(self, service: Any, ctx: ReconciliationRunContext) -> None:
        if (
            not ctx.policy.allows_strategy(self.strategy_id)
            or not ctx.policy.allows_source_type(self.provider.source_type)
            or not ctx.policy.allows_provider(self.provider.provider_key)
        ):
            return
        payments = [
            payment
            for payment in self.provider.load(service, ctx)
            if payment.payment_id not in ctx.tracker(self.provider.provider_key)
        ]
        if not payments:
            return
        payment_index: dict[tuple[object, int], list[Any]] = {}
        for payment in payments:
            if not payment.correlation_id:
                continue
            key = (payment.payment_date, int(Decimal(payment.amount) * 100))
            payment_index.setdefault(key, []).append(payment)

        line_index: dict[tuple[object, int], list[BankStatementLine]] = {}
        for line in ctx.still_unmatched_lines():
            key = (line.transaction_date, int(Decimal(line.amount) * 100))
            line_index.setdefault(key, []).append(line)

        matched_payment_ids = ctx.tracker(self.provider.provider_key)
        for key, indexed_payments in payment_index.items():
            available_lines = [
                line
                for line in line_index.get(key, [])
                if line.line_id not in ctx.matched_line_ids
            ]
            if not available_lines:
                continue

            pairs = min(len(indexed_payments), len(available_lines))
            for idx in range(pairs):
                payment = indexed_payments[idx]
                line = available_lines[idx]
                if payment.payment_id in matched_payment_ids:
                    continue
                try:
                    journal_line = service._find_journal_line(
                        ctx.db,
                        ctx.organization_id,
                        payment.correlation_id,
                        ctx.bank_account.gl_account_id,
                        extra_gl_account_ids=ctx.extra_gl_account_ids,
                    )
                    if not journal_line:
                        continue

                    _perform_match(
                        service,
                        ctx,
                        line,
                        journal_line,
                        source_type="CUSTOMER_PAYMENT",
                        source_id=payment.payment_id,
                        confidence=80,
                        explanation=f"Splynx payment {payment.splynx_id} (date+amount fallback)",
                    )
                    matched_payment_ids.add(payment.payment_id)
                except Exception as exc:
                    service.logger.exception(
                        "Error matching line %s via date+amount: %s",
                        line.line_id,
                        exc,
                    )
                    ctx.result.errors.append(f"Line {line.line_number}: {exc}")


@dataclass(frozen=True)
class SupplierPaymentReferenceStrategy(MatchStrategy):
    strategy_id: str = "exact_payable_reference"
    provider: SupplierPaymentProvider = SupplierPaymentProvider()

    def run(self, service: Any, ctx: ReconciliationRunContext) -> None:
        if (
            not ctx.policy.allows_strategy(self.strategy_id)
            or not ctx.policy.allows_source_type(self.provider.source_type)
            or not ctx.policy.allows_provider(self.provider.provider_key)
        ):
            return
        payments = self.provider.load(service, ctx)
        if not payments:
            return
        matched_payment_ids = ctx.tracker(self.provider.provider_key)
        _run_directional_reference_match(
            service,
            ctx,
            payments=payments,
            matched_payment_ids=matched_payment_ids,
            line_type=StatementLineType.debit,
            source_type="SUPPLIER_PAYMENT",
            explanation_prefix="AP payment",
        )
        _run_directional_date_amount_match(
            service,
            ctx,
            payments=payments,
            matched_payment_ids=matched_payment_ids,
            line_type=StatementLineType.debit,
            source_type="SUPPLIER_PAYMENT",
            explanation_prefix="AP payment",
        )


@dataclass(frozen=True)
class CustomerReceiptReferenceStrategy(MatchStrategy):
    strategy_id: str = "exact_receivable_reference"
    provider: CustomerReceiptProvider = CustomerReceiptProvider()

    def run(self, service: Any, ctx: ReconciliationRunContext) -> None:
        if (
            not ctx.policy.allows_strategy(self.strategy_id)
            or not ctx.policy.allows_source_type(self.provider.source_type)
            or not ctx.policy.allows_provider(self.provider.provider_key)
        ):
            return
        payments = self.provider.load(service, ctx)
        if not payments:
            return
        matched_payment_ids = ctx.tracker(self.provider.provider_key)
        _run_directional_reference_match(
            service,
            ctx,
            payments=payments,
            matched_payment_ids=matched_payment_ids,
            line_type=StatementLineType.credit,
            source_type="CUSTOMER_PAYMENT",
            explanation_prefix="AR payment",
        )
        _run_directional_date_amount_match(
            service,
            ctx,
            payments=payments,
            matched_payment_ids=matched_payment_ids,
            line_type=StatementLineType.credit,
            source_type="CUSTOMER_PAYMENT",
            explanation_prefix="AR payment",
        )
