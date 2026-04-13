"""CategorizationCoreService component."""

from __future__ import annotations

from typing import cast

from app.services.finance.banking.categorization_parts.base import (
    BankStatement,
    BankStatementLine,
    BatchCategorizationResult,
    CategorizationResult,
    CategorizationSuggestion,
    Payee,
    RuleAction,
    Session,
    StatementLineType,
    TransactionRule,
    UUID,
    coerce_uuid,
    datetime,
    func,
    logger,
    or_,
    select,
)


class CategorizationCoreService:
    """Transaction categorization methods for core."""

    @staticmethod
    def _next_copy_rule_name(
        db: Session,
        organization_id: UUID,
        base_name: str,
    ) -> str:
        """Generate a unique rule name under uq_rule_name constraints."""
        seed = (base_name or "Rule").strip() or "Rule"
        max_len = 100

        for idx in range(1, 1000):
            suffix = " (Copy)" if idx == 1 else f" (Copy {idx})"
            candidate = f"{seed[: max_len - len(suffix)]}{suffix}"
            exists = db.scalar(
                select(func.count())
                .select_from(TransactionRule)
                .where(
                    TransactionRule.organization_id == organization_id,
                    TransactionRule.rule_name == candidate,
                )
            )
            if not exists:
                return candidate

        # Fallback safety valve
        return f"{seed[:80]} (Copy {datetime.utcnow().strftime('%H%M%S')})"

    def categorize_line(
        self,
        db: Session,
        organization_id: UUID,
        line: BankStatementLine,
        check_duplicates: bool = True,
    ) -> CategorizationResult:
        """
        Categorize a single statement line.

        Args:
            db: Database session
            organization_id: Organization UUID
            line: The statement line to categorize
            check_duplicates: Whether to check for duplicate transactions

        Returns:
            CategorizationResult with suggestions
        """
        result = CategorizationResult(line_id=line.line_id)

        # Check for duplicates first
        if check_duplicates:
            duplicate = self._find_duplicate(db, organization_id, line)
            if duplicate:
                result.is_duplicate = True
                result.duplicate_of = duplicate.line_id
                return result

        # Try payee matching
        payee_suggestion = self._match_payee(db, organization_id, line)
        if payee_suggestion:
            result.suggestions.append(payee_suggestion)

        # Try rule matching
        rule_suggestions = self._match_rules(db, organization_id, line)
        result.suggestions.extend(rule_suggestions)

        # Sort by confidence (highest first)
        result.suggestions.sort(key=lambda s: s.confidence, reverse=True)

        return result

    def categorize_statement(
        self,
        db: Session,
        organization_id: UUID,
        statement_id: UUID,
        check_duplicates: bool = True,
    ) -> BatchCategorizationResult:
        """
        Categorize all unmatched lines in a statement.

        Args:
            db: Database session
            organization_id: Organization UUID
            statement_id: Statement UUID
            check_duplicates: Whether to check for duplicates

        Returns:
            BatchCategorizationResult with all results
        """
        # Get unmatched lines
        lines = list(
            db.execute(
                select(BankStatementLine)
                .where(
                    BankStatementLine.statement_id == statement_id,
                    BankStatementLine.is_matched == False,
                )
                .order_by(BankStatementLine.line_number)
            )
            .scalars()
            .all()
        )

        batch_result = BatchCategorizationResult(total_lines=len(lines))

        for line in lines:
            result = self.categorize_line(db, organization_id, line, check_duplicates)
            batch_result.results.append(result)

            if result.is_duplicate:
                batch_result.duplicate_count += 1
            elif result.suggestions:
                batch_result.categorized_count += 1
                if result.has_high_confidence_match:
                    batch_result.high_confidence_count += 1
                else:
                    batch_result.low_confidence_count += 1
            else:
                batch_result.no_match_count += 1

        return batch_result

    def _find_duplicate(
        self,
        db: Session,
        organization_id: UUID,
        line: BankStatementLine,
    ) -> BankStatementLine | None:
        """Check if a transaction is a duplicate."""
        # Look for same amount, date, and similar description in recent statements
        statement = db.get(BankStatement, line.statement_id)
        if not statement:
            return None

        # Find potential duplicates (same account, date, amount, type)
        # Scoped to organization_id to prevent cross-tenant matches
        duplicate = (
            db.execute(
                select(BankStatementLine)
                .join(BankStatement)
                .where(
                    BankStatement.bank_account_id == statement.bank_account_id,
                    BankStatement.organization_id == organization_id,
                    BankStatementLine.line_id != line.line_id,
                    BankStatementLine.transaction_date == line.transaction_date,
                    BankStatementLine.amount == line.amount,
                    BankStatementLine.transaction_type == line.transaction_type,
                )
            )
            .scalars()
            .first()
        )

        if duplicate:
            # Check if descriptions are similar (simple check)
            if line.description and duplicate.description:
                if (
                    self._similarity_score(line.description, duplicate.description)  # type: ignore[attr-defined]
                    > 0.8
                ):
                    return duplicate
            # If no description, match on reference
            elif line.bank_reference and duplicate.bank_reference:
                if line.bank_reference == duplicate.bank_reference:
                    return duplicate

        return None

    def _match_payee(
        self,
        db: Session,
        organization_id: UUID,
        line: BankStatementLine,
    ) -> CategorizationSuggestion | None:
        """Try to match the transaction to a known payee."""
        if not line.description and not line.payee_payer:
            return None

        search_text = f"{line.payee_payer or ''} {line.description or ''}".strip()
        if not search_text:
            return None

        # Get active payees
        payees = list(
            db.execute(
                select(Payee).where(
                    Payee.organization_id == organization_id,
                    Payee.is_active == True,
                )
            )
            .scalars()
            .all()
        )

        best_match: tuple[Payee, int] | None = None

        for payee in payees:
            if payee.matches_name(search_text):
                # Calculate confidence based on match quality
                confidence = self._calculate_payee_confidence(payee, search_text)  # type: ignore[attr-defined]
                if best_match is None or confidence > best_match[1]:
                    best_match = (payee, confidence)

        if best_match:
            payee, confidence = best_match
            return CategorizationSuggestion(
                account_id=payee.default_account_id,
                tax_code_id=payee.default_tax_code_id,
                payee_id=payee.payee_id,
                payee_name=payee.payee_name,
                confidence=confidence,
                match_reason=f"Matched payee: {payee.payee_name}",
            )

        return None

    def _match_rules(
        self,
        db: Session,
        organization_id: UUID,
        line: BankStatementLine,
    ) -> list[CategorizationSuggestion]:
        """Match the transaction against categorization rules."""
        suggestions = []

        # Get active rules, ordered by priority
        statement = db.get(BankStatement, line.statement_id)
        bank_account_id = statement.bank_account_id if statement else None

        rules = list(
            db.execute(
                select(TransactionRule)
                .where(
                    TransactionRule.organization_id == organization_id,
                    TransactionRule.is_active == True,
                    or_(
                        TransactionRule.bank_account_id == None,
                        TransactionRule.bank_account_id == bank_account_id,
                    ),
                )
                .order_by(TransactionRule.sort_order.asc())
            )
            .scalars()
            .all()
        )

        for rule in rules:
            # Check transaction type filter
            if line.transaction_type == StatementLineType.credit:
                if not rule.applies_to_credits:
                    continue
            else:
                if not rule.applies_to_debits:
                    continue

            # Try to match the rule
            match_result = self._evaluate_rule(rule, line)  # type: ignore[attr-defined]
            if match_result:
                confidence, reason = match_result

                if confidence >= rule.min_confidence:
                    suggestion = CategorizationSuggestion(
                        account_id=rule.target_account_id,
                        tax_code_id=rule.tax_code_id,
                        payee_id=rule.payee_id,
                        rule_id=rule.rule_id,
                        rule_name=rule.rule_name,
                        confidence=confidence,
                        match_reason=reason,
                        action=rule.action,
                        split_config=rule.split_config
                        if rule.action == RuleAction.SPLIT
                        else None,
                    )
                    suggestions.append(suggestion)

        return suggestions

    def apply_rules_to_statement(
        self,
        db: Session,
        organization_id: UUID,
        statement_id: UUID,
        _applied_by: UUID | None = None,
    ) -> BatchCategorizationResult:
        """
        Run categorization rules against unprocessed statement lines.

        Lines that already have a categorization_status or are matched are
        skipped.  For each match the best suggestion is persisted on the
        line.  Rules with ``auto_apply=True`` whose confidence meets the
        rule's ``min_confidence`` are applied immediately.

        Returns:
            BatchCategorizationResult with processing counts.
        """

        # Fetch lines that haven't been categorized yet and aren't matched
        lines = list(
            db.execute(
                select(BankStatementLine)
                .where(
                    BankStatementLine.statement_id == statement_id,
                    BankStatementLine.is_matched.is_(False),
                    BankStatementLine.categorization_status.is_(None),
                )
                .order_by(BankStatementLine.line_number)
            )
            .scalars()
            .all()
        )

        batch = self._process_categorization_batch(db, organization_id, lines)

        db.flush()
        logger.info(
            "Applied rules to statement %s: %d lines, %d categorized, "
            "%d auto-applied, %d no match",
            statement_id,
            batch.total_lines,
            batch.categorized_count,
            batch.high_confidence_count,
            batch.no_match_count,
        )
        return batch

    def apply_rules_to_account(
        self,
        db: Session,
        organization_id: UUID,
        bank_account_id: UUID,
        _applied_by: UUID | None = None,
    ) -> BatchCategorizationResult:
        """Run categorization rules against unprocessed lines for a bank account.

        Queries across all statements for the given bank account, processing
        lines that haven't been categorized yet and aren't matched.

        Returns:
            BatchCategorizationResult with processing counts.
        """
        lines = list(
            db.execute(
                select(BankStatementLine)
                .join(BankStatement)
                .where(
                    BankStatement.organization_id == organization_id,
                    BankStatement.bank_account_id == bank_account_id,
                    BankStatementLine.is_matched.is_(False),
                    BankStatementLine.categorization_status.is_(None),
                )
                .order_by(
                    BankStatementLine.transaction_date,
                    BankStatementLine.line_number,
                )
            )
            .scalars()
            .all()
        )

        batch = self._process_categorization_batch(db, organization_id, lines)

        db.flush()
        logger.info(
            "Applied rules to account %s: %d lines, %d categorized, "
            "%d auto-applied, %d no match",
            bank_account_id,
            batch.total_lines,
            batch.categorized_count,
            batch.high_confidence_count,
            batch.no_match_count,
        )
        return batch

    def _process_categorization_batch(
        self,
        db: Session,
        organization_id: UUID,
        lines: list[BankStatementLine],
    ) -> BatchCategorizationResult:
        """Shared batch loop: categorize lines, persist suggestions, auto-apply.

        Does NOT flush — callers are responsible for flushing/committing.
        """
        from app.models.finance.banking.bank_statement import CategorizationStatus

        batch = BatchCategorizationResult(total_lines=len(lines))

        for line in lines:
            result = self.categorize_line(db, organization_id, line)
            batch.results.append(result)

            if result.is_duplicate:
                batch.duplicate_count += 1
                continue

            best = result.best_suggestion
            if not best:
                batch.no_match_count += 1
                continue

            # Persist suggestion on the line
            line.suggested_account_id = best.account_id
            line.suggested_rule_id = best.rule_id
            line.suggested_confidence = best.confidence
            line.suggested_match_reason = (best.match_reason or "")[:200]

            # Determine categorization status
            if best.rule_id:
                rule = db.get(TransactionRule, best.rule_id)
                if rule and rule.auto_apply and best.confidence >= rule.min_confidence:
                    line.categorization_status = CategorizationStatus.AUTO_APPLIED
                    self.record_rule_feedback(
                        db, organization_id, best.rule_id, accepted=True
                    )
                    batch.categorized_count += 1
                    batch.high_confidence_count += 1
                    continue

            if best.action == RuleAction.FLAG_REVIEW:
                line.categorization_status = CategorizationStatus.FLAGGED
            else:
                line.categorization_status = CategorizationStatus.SUGGESTED

            batch.categorized_count += 1
            if best.confidence >= 80:
                batch.high_confidence_count += 1
            else:
                batch.low_confidence_count += 1

        return batch

    def accept_suggestion(
        self,
        db: Session,
        organization_id: UUID,
        line_id: UUID,
        accepted_by: UUID | None = None,  # noqa: ARG002 — part of public API
    ) -> BankStatementLine:
        """
        Accept a categorization suggestion on a statement line.

        Raises ValueError if the line is not found or not in a reviewable
        state.
        """
        from app.models.finance.banking.bank_statement import CategorizationStatus

        line = (
            db.execute(
                select(BankStatementLine)
                .join(BankStatement)
                .where(
                    BankStatementLine.line_id == line_id,
                    BankStatement.organization_id == organization_id,
                )
            )
            .scalars()
            .first()
        )
        if not line:
            raise ValueError("Statement line not found")

        reviewable = {CategorizationStatus.SUGGESTED, CategorizationStatus.FLAGGED}
        if line.categorization_status not in reviewable:
            raise ValueError(
                f"Line is not in a reviewable state "
                f"(current: {line.categorization_status})"
            )

        line.categorization_status = CategorizationStatus.ACCEPTED

        if line.suggested_rule_id:
            self.record_rule_feedback(
                db, organization_id, line.suggested_rule_id, accepted=True
            )

        db.flush()
        logger.info("Accepted suggestion for line %s", line_id)
        return line

    def reject_suggestion(
        self,
        db: Session,
        organization_id: UUID,
        line_id: UUID,
    ) -> BankStatementLine:
        """
        Reject a categorization suggestion on a statement line.

        Clears all suggestion fields and records negative feedback on the
        matched rule.

        Raises ValueError if the line is not found or not in a reviewable
        state.
        """
        from app.models.finance.banking.bank_statement import CategorizationStatus

        line = (
            db.execute(
                select(BankStatementLine)
                .join(BankStatement)
                .where(
                    BankStatementLine.line_id == line_id,
                    BankStatement.organization_id == organization_id,
                )
            )
            .scalars()
            .first()
        )
        if not line:
            raise ValueError("Statement line not found")

        reviewable = {CategorizationStatus.SUGGESTED, CategorizationStatus.FLAGGED}
        if line.categorization_status not in reviewable:
            raise ValueError(
                f"Line is not in a reviewable state "
                f"(current: {line.categorization_status})"
            )

        # Record feedback before clearing
        rule_id = line.suggested_rule_id
        if rule_id:
            self.record_rule_feedback(db, organization_id, rule_id, accepted=False)

        line.categorization_status = CategorizationStatus.REJECTED
        line.suggested_account_id = None
        line.suggested_rule_id = None
        line.suggested_confidence = None
        line.suggested_match_reason = None

        db.flush()
        logger.info("Rejected suggestion for line %s", line_id)
        return line

    # Payee management methods
    def record_rule_feedback(
        self,
        db: Session,
        organization_id: UUID,
        rule_id: UUID,
        accepted: bool,
    ) -> None:
        """Record user feedback on a rule suggestion."""
        org_id = coerce_uuid(organization_id)
        rule = (
            db.execute(
                select(TransactionRule).where(
                    TransactionRule.rule_id == coerce_uuid(rule_id),
                    TransactionRule.organization_id == org_id,
                )
            )
            .scalars()
            .first()
        )
        if rule:
            rule.match_count += 1
            rule.last_matched_at = datetime.utcnow()
            if accepted:
                rule.success_count += 1
            else:
                rule.reject_count += 1
            db.flush()

    def learn_from_categorization(
        self,
        db: Session,
        organization_id: UUID,
        line: BankStatementLine,
        account_id: UUID,
        created_by: UUID | None = None,
    ) -> Payee | None:
        """
        Learn from a manual categorization to create/update payee.

        When a user manually categorizes a transaction, we can learn
        the payee name and default account for future auto-categorization.
        """
        payee_name = line.payee_payer or line.description
        if not payee_name:
            return None

        # Clean up the name (take first significant part)
        payee_name = payee_name.strip()[:200]

        # Check if payee already exists
        existing = (
            db.execute(
                select(Payee).where(
                    Payee.organization_id == organization_id,
                    Payee.payee_name == payee_name,
                )
            )
            .scalars()
            .first()
        )

        if existing:
            # Update match count and possibly default account
            existing.match_count += 1
            existing.last_matched_at = datetime.utcnow()
            if not existing.default_account_id:
                existing.default_account_id = account_id
            db.flush()
            return existing
        else:
            # Create new payee
            return cast(
                Payee,
                self.create_payee(  # type: ignore[attr-defined]
                    db=db,
                    organization_id=organization_id,
                    payee_name=payee_name,
                    default_account_id=account_id,
                    created_by=created_by,
                ),
            )
