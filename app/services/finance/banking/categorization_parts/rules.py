"""CategorizationRuleService component."""

from __future__ import annotations

from app.services.finance.banking.categorization_parts.base import (
    BankAccount,
    BankAccountStatus,
    RuleAction,
    RuleType,
    Session,
    TransactionRule,
    UUID,
    coerce_uuid,
    func,
    logger,
    or_,
    select,
)


class CategorizationRuleService:
    """Transaction categorization methods for rules."""

    def create_rule(
        self,
        db: Session,
        organization_id: UUID,
        rule_name: str,
        rule_type: RuleType,
        conditions: dict,
        action: RuleAction = RuleAction.CATEGORIZE,
        target_account_id: UUID | None = None,
        tax_code_id: UUID | None = None,
        bank_account_id: UUID | None = None,
        payee_id: UUID | None = None,
        auto_apply: bool = False,
        min_confidence: int = 80,
        applies_to_credits: bool = True,
        applies_to_debits: bool = True,
        split_config: dict | None = None,
        description: str | None = None,
        created_by: UUID | None = None,
    ) -> TransactionRule:
        """Create a new categorization rule.

        The rule is placed at the end of the evaluation order
        (sort_order = max existing + 1).
        """
        # Auto-assign sort_order: append after the last rule for this org
        max_order = db.scalar(
            select(func.max(TransactionRule.sort_order)).where(
                TransactionRule.organization_id == organization_id,
            )
        )
        next_order = (max_order + 1) if max_order is not None else 0

        rule = TransactionRule(
            organization_id=organization_id,
            rule_name=rule_name,
            rule_type=rule_type,
            conditions=conditions,
            action=action,
            target_account_id=target_account_id,
            tax_code_id=tax_code_id,
            bank_account_id=bank_account_id,
            payee_id=payee_id,
            sort_order=next_order,
            auto_apply=auto_apply,
            min_confidence=min_confidence,
            applies_to_credits=applies_to_credits,
            applies_to_debits=applies_to_debits,
            split_config=split_config,
            description=description,
            created_by=created_by,
        )
        db.add(rule)
        db.flush()
        return rule

    def update_rule(
        self,
        db: Session,
        organization_id: UUID,
        rule_id: UUID,
        **kwargs,
    ) -> TransactionRule | None:
        """Update a rule."""
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
        if not rule:
            return None

        allowed_fields = [
            "rule_name",
            "description",
            "rule_type",
            "conditions",
            "action",
            "target_account_id",
            "tax_code_id",
            "bank_account_id",
            "payee_id",
            "auto_apply",
            "min_confidence",
            "applies_to_credits",
            "applies_to_debits",
            "split_config",
            "is_active",
        ]

        for key, value in kwargs.items():
            if key in allowed_fields:
                setattr(rule, key, value)

        db.flush()
        return rule

    def duplicate_rule_to_accounts(
        self,
        db: Session,
        organization_id: UUID,
        source_rule_id: UUID,
        bank_account_ids: list[UUID],
        *,
        include_global: bool = False,
        created_by: UUID | None = None,
    ) -> list[TransactionRule]:
        """Duplicate one rule to multiple bank accounts (and optional global)."""
        org_id = coerce_uuid(organization_id)
        source_rule = (
            db.execute(
                select(TransactionRule).where(
                    TransactionRule.rule_id == coerce_uuid(source_rule_id),
                    TransactionRule.organization_id == org_id,
                )
            )
            .scalars()
            .first()
        )
        if not source_rule:
            raise ValueError("Rule not found")

        unique_bank_ids = list(dict.fromkeys(coerce_uuid(v) for v in bank_account_ids))
        # Skip the source rule's own bank account — it already has this rule
        if source_rule.bank_account_id:
            unique_bank_ids = [
                bid for bid in unique_bank_ids if bid != source_rule.bank_account_id
            ]
        if not unique_bank_ids and not include_global:
            raise ValueError(
                "Select at least one target account or include global copy"
            )

        bank_accounts: list[BankAccount] = []
        if unique_bank_ids:
            bank_accounts = list(
                db.execute(
                    select(BankAccount).where(
                        BankAccount.organization_id == org_id,
                        BankAccount.bank_account_id.in_(unique_bank_ids),
                        BankAccount.status == BankAccountStatus.active,
                    )
                )
                .scalars()
                .all()
            )
            found_ids = {a.bank_account_id for a in bank_accounts}
            missing = [bid for bid in unique_bank_ids if bid not in found_ids]
            if missing:
                raise ValueError("One or more selected bank accounts are invalid")
            bank_accounts.sort(
                key=lambda acct: unique_bank_ids.index(acct.bank_account_id)
            )

        created: list[TransactionRule] = []
        for account in bank_accounts:
            clone = self.create_rule(
                db=db,
                organization_id=org_id,
                rule_name=self._next_copy_rule_name(  # type: ignore[attr-defined]
                    db,
                    org_id,
                    f"{source_rule.rule_name} - {account.account_name}",
                ),
                rule_type=source_rule.rule_type,
                conditions=source_rule.conditions,
                action=source_rule.action,
                target_account_id=source_rule.target_account_id,
                tax_code_id=source_rule.tax_code_id,
                bank_account_id=account.bank_account_id,
                payee_id=source_rule.payee_id,
                auto_apply=source_rule.auto_apply,
                min_confidence=source_rule.min_confidence,
                applies_to_credits=source_rule.applies_to_credits,
                applies_to_debits=source_rule.applies_to_debits,
                split_config=source_rule.split_config,
                description=source_rule.description,
                created_by=created_by,
            )
            clone.is_active = source_rule.is_active
            created.append(clone)

        if include_global:
            clone = self.create_rule(
                db=db,
                organization_id=org_id,
                rule_name=self._next_copy_rule_name(  # type: ignore[attr-defined]
                    db,
                    org_id,
                    f"{source_rule.rule_name} - All Accounts",
                ),
                rule_type=source_rule.rule_type,
                conditions=source_rule.conditions,
                action=source_rule.action,
                target_account_id=source_rule.target_account_id,
                tax_code_id=source_rule.tax_code_id,
                bank_account_id=None,
                payee_id=source_rule.payee_id,
                auto_apply=source_rule.auto_apply,
                min_confidence=source_rule.min_confidence,
                applies_to_credits=source_rule.applies_to_credits,
                applies_to_debits=source_rule.applies_to_debits,
                split_config=source_rule.split_config,
                description=source_rule.description,
                created_by=created_by,
            )
            clone.is_active = source_rule.is_active
            created.append(clone)

        db.flush()
        return created

    def list_rules(
        self,
        db: Session,
        organization_id: UUID,
        rule_type: RuleType | None = None,
        is_active: bool | None = True,
        bank_account_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TransactionRule]:
        """List rules with filters."""
        stmt = select(TransactionRule).where(
            TransactionRule.organization_id == organization_id
        )

        if rule_type:
            stmt = stmt.where(TransactionRule.rule_type == rule_type)
        if is_active is not None:
            stmt = stmt.where(TransactionRule.is_active == is_active)
        if bank_account_id:
            stmt = stmt.where(
                or_(
                    TransactionRule.bank_account_id == None,
                    TransactionRule.bank_account_id == bank_account_id,
                )
            )

        return list(
            db.execute(
                stmt.order_by(
                    TransactionRule.sort_order.asc(), TransactionRule.rule_name
                )
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def swap_rule_order(
        self,
        db: Session,
        organization_id: UUID,
        rule_id: UUID,
        direction: str,
    ) -> bool:
        """Swap a rule's sort_order with its neighbor.

        Args:
            db: Database session
            organization_id: Organization UUID
            rule_id: The rule to move
            direction: "up" (lower sort_order) or "down" (higher sort_order)

        Returns:
            True if the swap succeeded, False if the rule is already at the boundary.
        """
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
        if not rule:
            return False

        # Find the neighbor to swap with
        if direction == "up":
            neighbor = (
                db.execute(
                    select(TransactionRule)
                    .where(
                        TransactionRule.organization_id == org_id,
                        TransactionRule.sort_order < rule.sort_order,
                    )
                    .order_by(TransactionRule.sort_order.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
        elif direction == "down":
            neighbor = (
                db.execute(
                    select(TransactionRule)
                    .where(
                        TransactionRule.organization_id == org_id,
                        TransactionRule.sort_order > rule.sort_order,
                    )
                    .order_by(TransactionRule.sort_order.asc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
        else:
            return False

        if not neighbor:
            return False

        # Swap sort_order values
        rule.sort_order, neighbor.sort_order = neighbor.sort_order, rule.sort_order
        db.flush()
        logger.info(
            "Swapped rule %s (order %d) with %s (order %d)",
            rule.rule_id,
            rule.sort_order,
            neighbor.rule_id,
            neighbor.sort_order,
        )
        return True
