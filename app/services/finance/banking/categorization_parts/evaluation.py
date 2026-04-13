"""CategorizationEvaluationService component."""

from __future__ import annotations

from app.services.finance.banking.categorization_parts.base import (
    BankStatementLine,
    Decimal,
    Payee,
    RuleType,
    StatementLineType,
    TransactionRule,
    logger,
    re,
)


class CategorizationEvaluationService:
    """Transaction categorization methods for evaluation."""

    def _evaluate_rule(
        self,
        rule: TransactionRule,
        line: BankStatementLine,
    ) -> tuple[int, str] | None:
        """
        Evaluate if a rule matches a transaction line.

        Returns:
            Tuple of (confidence, reason) if matched, None otherwise
        """
        conditions = rule.conditions or {}

        if rule.rule_type == RuleType.PAYEE_MATCH:
            return self._eval_payee_match(conditions, line)
        elif rule.rule_type == RuleType.DESCRIPTION_CONTAINS:
            return self._eval_description_contains(conditions, line)
        elif rule.rule_type == RuleType.DESCRIPTION_REGEX:
            return self._eval_description_regex(conditions, line)
        elif rule.rule_type == RuleType.AMOUNT_RANGE:
            return self._eval_amount_range(conditions, line)
        elif rule.rule_type == RuleType.REFERENCE_MATCH:
            return self._eval_reference_match(conditions, line)
        elif rule.rule_type == RuleType.COMBINED:
            return self._eval_combined(conditions, line)

        return None

    def _eval_payee_match(
        self,
        conditions: dict,
        line: BankStatementLine,
    ) -> tuple[int, str] | None:
        """Evaluate payee pattern match (word-boundary aware)."""
        patterns = conditions.get("patterns", [])
        # Also support legacy single "payee_name" field
        legacy_name = conditions.get("payee_name", "")
        if legacy_name and not patterns:
            patterns = [legacy_name]
        case_sensitive = conditions.get("case_sensitive", False)

        search_text = f"{line.payee_payer or ''} {line.description or ''}"
        flags = 0 if case_sensitive else re.IGNORECASE

        for pattern in patterns:
            if not pattern:
                continue
            escaped = re.escape(pattern)
            if re.search(rf"\b{escaped}\b", search_text, flags):
                return (90, f"Payee pattern matched: {pattern}")

        return None

    def _eval_description_contains(
        self,
        conditions: dict,
        line: BankStatementLine,
    ) -> tuple[int, str] | None:
        """Evaluate description contains match."""
        text = conditions.get("text", "")
        # Also support legacy "keywords" array format
        keywords = conditions.get("keywords", [])
        case_sensitive = conditions.get("case_sensitive", False)

        if not line.description:
            return None

        description = line.description if case_sensitive else line.description.upper()

        # Check single text field first
        if text:
            check_text = text if case_sensitive else text.upper()
            if check_text in description:
                return (85, f"Description contains: {text}")

        # Check keywords array (legacy format)
        for kw in keywords:
            if not kw:
                continue
            check_kw = kw if case_sensitive else kw.upper()
            if check_kw in description:
                return (85, f"Description contains: {kw}")

        return None

    def _eval_description_regex(
        self,
        conditions: dict,
        line: BankStatementLine,
    ) -> tuple[int, str] | None:
        """Evaluate regex pattern match."""
        pattern = conditions.get("pattern", "")

        if not line.description or not pattern:
            return None

        try:
            if re.search(pattern, line.description, re.IGNORECASE):
                return (80, f"Regex matched: {pattern}")
        except re.error as exc:
            logger.warning(
                "Invalid regex pattern in categorization rule: %r - %s",
                pattern,
                exc,
            )

        return None

    def _eval_amount_range(
        self,
        conditions: dict,
        line: BankStatementLine,
    ) -> tuple[int, str] | None:
        """Evaluate amount range match."""
        min_amount = Decimal(str(conditions.get("min", 0)))
        max_amount = Decimal(str(conditions.get("max", float("inf"))))
        trans_type = conditions.get("transaction_type")

        # Check transaction type if specified
        if trans_type:
            if (
                trans_type == "credit"
                and line.transaction_type != StatementLineType.credit
            ):
                return None
            if (
                trans_type == "debit"
                and line.transaction_type != StatementLineType.debit
            ):
                return None

        if min_amount <= line.amount <= max_amount:
            # Exact amount match gets higher confidence than a range
            if min_amount == max_amount:
                confidence = 85
                reason = f"Exact amount match: {min_amount}"
            else:
                confidence = 70
                reason = f"Amount in range: {min_amount} - {max_amount}"
            return (confidence, reason)

        return None

    def _eval_reference_match(
        self,
        conditions: dict,
        line: BankStatementLine,
    ) -> tuple[int, str] | None:
        """Evaluate reference pattern match."""
        pattern = conditions.get("pattern", "")

        if not pattern:
            return None

        # Check various reference fields
        ref_fields = [line.reference, line.bank_reference, line.check_number]

        for ref in ref_fields:
            if ref:
                try:
                    if re.search(pattern, ref, re.IGNORECASE):
                        return (85, f"Reference matched: {pattern}")
                except re.error as exc:
                    logger.warning(
                        "Invalid regex pattern in reference match: %r - %s",
                        pattern,
                        exc,
                    )

        return None

    def _eval_combined(
        self,
        conditions: dict,
        line: BankStatementLine,
    ) -> tuple[int, str] | None:
        """Evaluate combined conditions."""
        operator = conditions.get("operator", "AND")
        sub_rules = conditions.get("rules", [])

        if not sub_rules:
            return None

        results = []
        for sub_rule in sub_rules:
            sub_type = sub_rule.get("type")
            sub_conditions = sub_rule.get("conditions", {})

            result = None
            if sub_type == "PAYEE_MATCH":
                result = self._eval_payee_match(sub_conditions, line)
            elif sub_type == "DESCRIPTION_CONTAINS":
                result = self._eval_description_contains(sub_conditions, line)
            elif sub_type == "AMOUNT_RANGE":
                result = self._eval_amount_range(sub_conditions, line)
            elif sub_type == "DESCRIPTION_REGEX":
                result = self._eval_description_regex(sub_conditions, line)
            elif sub_type == "REFERENCE_MATCH":
                result = self._eval_reference_match(sub_conditions, line)

            if result:
                results.append(result)

        if not results:
            return None

        if operator == "AND":
            if len(results) == len(sub_rules):
                avg_confidence = sum(r[0] for r in results) // len(results)
                return (avg_confidence, "All conditions matched")
        elif operator == "OR":
            best = max(results, key=lambda r: r[0])
            return best

        return None

    def _calculate_payee_confidence(self, payee: Payee, search_text: str) -> int:
        """Calculate confidence score for a payee match."""
        search_upper = search_text.upper()
        name_upper = payee.payee_name.upper()

        # Exact name match = 95% (word-boundary aware)
        if Payee.word_boundary_match(payee.payee_name, search_text):
            # Higher confidence if it's at the start
            if search_upper.startswith(name_upper):
                return 95
            return 90

        # Pattern match = 80-85% (word-boundary aware)
        if payee.name_patterns:
            patterns = [p.strip() for p in payee.name_patterns.split("|")]
            for pattern in patterns:
                if pattern and Payee.word_boundary_match(pattern, search_text):
                    return 85

        return 75

    def _similarity_score(self, s1: str, s2: str) -> float:
        """Calculate simple similarity between two strings."""
        if not s1 or not s2:
            return 0.0

        s1_upper = s1.upper()
        s2_upper = s2.upper()

        if s1_upper == s2_upper:
            return 1.0

        # Simple word overlap similarity
        words1 = set(s1_upper.split())
        words2 = set(s2_upper.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union)

    # ------------------------------------------------------------------
    # Apply / Accept / Reject methods
    # ------------------------------------------------------------------
