"""Programmatic reconciliation helper functions."""

from __future__ import annotations

from app.services.finance.banking.programmatic_parts.base import (
    Any,
    BankAccount,
    BankStatementLine,
    Decimal,
    PaymentIntent,
    ReconciliationRunContext,
    StatementLineType,
    UUID,
    select,
)


def _find_entity_for_line(
    ctx: ReconciliationRunContext,
    line: BankStatementLine,
    ref_lookup: dict[str, Any],
) -> Any | None:
    normalized = ctx.normalized_lines.get(line.line_id)
    if not normalized:
        return None
    searchable_text = normalized.searchable_text.lower()
    for ref, entity in ref_lookup.items():
        if ref.lower() in searchable_text:
            return entity
    return None


def _payment_intent_ref_lookup(
    intents: list[PaymentIntent],
) -> dict[str, PaymentIntent]:
    return {
        intent.paystack_reference: intent
        for intent in intents
        if getattr(intent, "paystack_reference", None)
    }


def _splynx_ref_lookup(service: Any, payments: list[Any]) -> dict[str, Any]:
    ref_to_payment: dict[str, Any] = {}
    for payment in payments:
        paystack_ref = service._extract_paystack_ref(payment.description)
        if paystack_ref:
            ref_to_payment[paystack_ref] = payment
    for payment in payments:
        if payment.reference and payment.reference not in ref_to_payment:
            ref_to_payment[payment.reference] = payment
    return ref_to_payment


def _perform_match(
    service: Any,
    ctx: ReconciliationRunContext,
    line: BankStatementLine,
    journal_line: Any,
    *,
    source_type: str,
    source_id: UUID | None,
    confidence: int,
    explanation: str,
) -> None:
    service._perform_match(
        ctx.db,
        ctx.organization_id,
        line,
        journal_line,
        source_type=source_type,
        source_id=source_id,
    )
    service._log_match(
        ctx.db,
        ctx.organization_id,
        line=line,
        source_type=source_type,
        source_id=source_id,
        journal_line_id=journal_line.line_id,
        confidence=confidence,
        explanation=explanation,
    )
    ctx.matched_line_ids.add(line.line_id)
    ctx.result.matched += 1


def _reference_payment_lookup(payments: list[Any]) -> dict[str, Any]:
    ref_to_payment: dict[str, Any] = {}
    for payment in payments:
        if getattr(payment, "payment_number", None):
            ref_to_payment[payment.payment_number] = payment
        if (
            getattr(payment, "reference", None)
            and payment.reference not in ref_to_payment
        ):
            ref_to_payment[payment.reference] = payment
    return ref_to_payment


def _run_directional_reference_match(
    service: Any,
    ctx: ReconciliationRunContext,
    *,
    payments: list[Any],
    matched_payment_ids: set[UUID],
    line_type: StatementLineType,
    source_type: str,
    explanation_prefix: str,
) -> None:
    ref_to_payment = _reference_payment_lookup(payments)
    if not ref_to_payment:
        return

    for line in ctx.still_unmatched_lines():
        if line.transaction_type != line_type:
            continue
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
                source_type=source_type,
                source_id=payment.payment_id,
                confidence=100,
                explanation=f"{explanation_prefix} {payment.payment_number} (reference match)",
            )
            matched_payment_ids.add(payment.payment_id)
        except Exception as exc:
            service.logger.exception(
                "Error matching line %s via %s ref: %s",
                line.line_id,
                explanation_prefix,
                exc,
            )
            ctx.result.errors.append(f"Line {line.line_number}: {exc}")


def _run_directional_date_amount_match(
    service: Any,
    ctx: ReconciliationRunContext,
    *,
    payments: list[Any],
    matched_payment_ids: set[UUID],
    line_type: StatementLineType,
    source_type: str,
    explanation_prefix: str,
) -> None:
    payment_index: dict[tuple[object, int], list[Any]] = {}
    for payment in payments:
        if payment.payment_id in matched_payment_ids or not payment.correlation_id:
            continue
        key = (payment.payment_date, int(Decimal(payment.amount) * 100))
        payment_index.setdefault(key, []).append(payment)

    line_index: dict[tuple[object, int], list[BankStatementLine]] = {}
    for line in ctx.still_unmatched_lines():
        if line.transaction_type != line_type:
            continue
        key = (line.transaction_date, int(Decimal(line.amount) * 100))
        line_index.setdefault(key, []).append(line)

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
                    source_type=source_type,
                    source_id=payment.payment_id,
                    confidence=80,
                    explanation=f"{explanation_prefix} {payment.payment_number} (date+amount fallback)",
                )
                matched_payment_ids.add(payment.payment_id)
            except Exception as exc:
                service.logger.exception(
                    "Error matching line %s via %s date+amount: %s",
                    line.line_id,
                    explanation_prefix,
                    exc,
                )
                ctx.result.errors.append(f"Line {line.line_number}: {exc}")


def build_extra_gl_account_ids(
    db: Any,
    organization_id: Any,
    bank_account: BankAccount,
) -> set[Any] | None:
    all_bank_gl_ids = set(
        db.scalars(
            select(BankAccount.gl_account_id).where(
                BankAccount.organization_id == organization_id,
                BankAccount.gl_account_id.isnot(None),
                BankAccount.gl_account_id != bank_account.gl_account_id,
            )
        ).all()
    )
    return all_bank_gl_ids or None
