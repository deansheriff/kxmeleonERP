"""
CategoryService — Account category hierarchy operations.

Tree traversal helpers for the GL chart of accounts category hierarchy.
Uses SQLAlchemy recursive CTEs so traversal is a single round trip
regardless of tree depth.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Integer, cast, func, literal, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from app.models.finance.gl.account_category import AccountCategory, IFRSCategory
from app.services.common import coerce_uuid

logger = logging.getLogger(__name__)


@dataclass
class CategoryNode:
    """Flat representation of a category in a hierarchy, depth-annotated."""

    category_id: UUID
    parent_category_id: UUID | None
    category_code: str
    category_name: str
    ifrs_category: IFRSCategory
    depth: int
    path: list[UUID]


class CategoryService:
    """
    Service for account category hierarchy management.

    All tree traversal uses recursive CTEs filtered by organization_id
    so multi-tenant isolation holds even across descendant walks.
    """

    @staticmethod
    def get_descendant_category_ids(
        db: Session,
        organization_id: UUID,
        category_id: UUID,
        *,
        include_self: bool = True,
        active_only: bool = True,
    ) -> list[UUID]:
        """
        Return every descendant category id under ``category_id``.

        Uses a recursive CTE so depth is unbounded but the walk is one query.
        """
        org_id = coerce_uuid(organization_id)
        root_id = coerce_uuid(category_id)

        base = (
            select(AccountCategory.category_id)
            .where(
                AccountCategory.category_id == root_id,
                AccountCategory.organization_id == org_id,
            )
            .cte("descendants", recursive=True)
        )

        recursive_clause = select(AccountCategory.category_id).where(
            AccountCategory.parent_category_id == base.c.category_id,
            AccountCategory.organization_id == org_id,
        )
        if active_only:
            recursive_clause = recursive_clause.where(
                AccountCategory.is_active.is_(True)
            )

        cte = base.union_all(recursive_clause)

        rows = db.execute(select(cte.c.category_id)).all()
        ids = [row[0] for row in rows]

        if not include_self and ids:
            ids = [cid for cid in ids if cid != root_id]

        return ids

    @staticmethod
    def get_ancestor_category_ids(
        db: Session,
        organization_id: UUID,
        category_id: UUID,
        *,
        include_self: bool = False,
    ) -> list[UUID]:
        """
        Return the chain of ancestor categories from the node up to the root.

        Ordered from closest parent to furthest ancestor.
        """
        org_id = coerce_uuid(organization_id)
        node_id = coerce_uuid(category_id)

        base = (
            select(
                AccountCategory.category_id,
                AccountCategory.parent_category_id,
                literal(0).label("depth"),
            )
            .where(
                AccountCategory.category_id == node_id,
                AccountCategory.organization_id == org_id,
            )
            .cte("ancestors", recursive=True)
        )

        recursive_clause = select(
            AccountCategory.category_id,
            AccountCategory.parent_category_id,
            (base.c.depth + 1).label("depth"),
        ).where(
            AccountCategory.category_id == base.c.parent_category_id,
            AccountCategory.organization_id == org_id,
        )

        cte = base.union_all(recursive_clause)

        rows = db.execute(
            select(cte.c.category_id, cte.c.depth).order_by(cte.c.depth)
        ).all()

        if not include_self:
            rows = [row for row in rows if row[1] > 0]

        return [row[0] for row in rows]

    @staticmethod
    def get_category_tree(
        db: Session,
        organization_id: UUID,
        *,
        active_only: bool = True,
    ) -> list[CategoryNode]:
        """
        Return the full category tree as a flat, depth-annotated list.

        Order: root ``display_order``, then depth-first walk by parent
        ``display_order``. Suitable for rendering indented tree UIs and
        for accumulating balances up the hierarchy.
        """
        org_id = coerce_uuid(organization_id)

        base_select = select(
            AccountCategory.category_id,
            AccountCategory.parent_category_id,
            AccountCategory.category_code,
            AccountCategory.category_name,
            AccountCategory.ifrs_category,
            AccountCategory.display_order,
            literal(0).label("depth"),
            func.array(
                [AccountCategory.category_id],
                type_=ARRAY(AccountCategory.category_id.type),
            ).label("path"),
            cast(
                func.array([AccountCategory.display_order]),
                ARRAY(Integer),
            ).label("sort_key"),
        ).where(
            AccountCategory.organization_id == org_id,
            AccountCategory.parent_category_id.is_(None),
        )
        if active_only:
            base_select = base_select.where(AccountCategory.is_active.is_(True))
        base = base_select.cte("tree", recursive=True)

        recursive_select = select(
            AccountCategory.category_id,
            AccountCategory.parent_category_id,
            AccountCategory.category_code,
            AccountCategory.category_name,
            AccountCategory.ifrs_category,
            AccountCategory.display_order,
            (base.c.depth + 1).label("depth"),
            func.array_append(base.c.path, AccountCategory.category_id).label("path"),
            func.array_append(base.c.sort_key, AccountCategory.display_order).label(
                "sort_key"
            ),
        ).where(
            AccountCategory.parent_category_id == base.c.category_id,
            AccountCategory.organization_id == org_id,
        )
        if active_only:
            recursive_select = recursive_select.where(
                AccountCategory.is_active.is_(True)
            )

        cte = base.union_all(recursive_select)

        stmt = select(
            cte.c.category_id,
            cte.c.parent_category_id,
            cte.c.category_code,
            cte.c.category_name,
            cte.c.ifrs_category,
            cte.c.depth,
            cte.c.path,
        ).order_by(cte.c.sort_key, cte.c.category_code)

        rows = db.execute(stmt).all()

        return [
            CategoryNode(
                category_id=row[0],
                parent_category_id=row[1],
                category_code=row[2],
                category_name=row[3],
                ifrs_category=(
                    row[4] if isinstance(row[4], IFRSCategory) else IFRSCategory(row[4])
                ),
                depth=row[5],
                path=list(row[6]) if row[6] is not None else [],
            )
            for row in rows
        ]

    @staticmethod
    def get_root_categories(
        db: Session,
        organization_id: UUID,
        *,
        active_only: bool = True,
    ) -> list[AccountCategory]:
        """Return top-level categories (no parent) for an organization."""
        org_id = coerce_uuid(organization_id)

        stmt = select(AccountCategory).where(
            AccountCategory.organization_id == org_id,
            AccountCategory.parent_category_id.is_(None),
        )
        if active_only:
            stmt = stmt.where(AccountCategory.is_active.is_(True))
        stmt = stmt.order_by(
            AccountCategory.display_order, AccountCategory.category_code
        )

        return list(db.scalars(stmt))


category_service = CategoryService()
