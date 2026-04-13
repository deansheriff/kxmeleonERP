"""
Tests for CategoryService tree helpers.

CategoryService uses raw recursive CTEs via ``db.execute(text(...))``
so tests mock the execute call to return row tuples shaped like the SQL
SELECT projection.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.models.finance.gl.account_category import IFRSCategory
from app.services.finance.gl.category import CategoryNode, CategoryService


@pytest.fixture
def service():
    return CategoryService()


@pytest.fixture
def org_id():
    return uuid.uuid4()


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = MagicMock()
    db.scalars = MagicMock()
    return db


class TestDescendantIds:
    def test_returns_self_and_children(self, service, mock_db, org_id):
        root = uuid.uuid4()
        child_a = uuid.uuid4()
        child_b = uuid.uuid4()
        mock_db.execute.return_value.all.return_value = [
            (root,),
            (child_a,),
            (child_b,),
        ]

        result = service.get_descendant_category_ids(mock_db, org_id, root)

        assert result == [root, child_a, child_b]
        mock_db.execute.assert_called_once()

    def test_exclude_self(self, service, mock_db, org_id):
        root = uuid.uuid4()
        child = uuid.uuid4()
        mock_db.execute.return_value.all.return_value = [(root,), (child,)]

        result = service.get_descendant_category_ids(
            mock_db, org_id, root, include_self=False
        )

        assert result == [child]

    def test_empty_tree(self, service, mock_db, org_id):
        mock_db.execute.return_value.all.return_value = []

        result = service.get_descendant_category_ids(mock_db, org_id, uuid.uuid4())

        assert result == []


class TestAncestorIds:
    def test_returns_parents_without_self(self, service, mock_db, org_id):
        node = uuid.uuid4()
        parent = uuid.uuid4()
        grandparent = uuid.uuid4()
        mock_db.execute.return_value.all.return_value = [
            (node, 0),
            (parent, 1),
            (grandparent, 2),
        ]

        result = service.get_ancestor_category_ids(mock_db, org_id, node)

        assert result == [parent, grandparent]

    def test_include_self(self, service, mock_db, org_id):
        node = uuid.uuid4()
        parent = uuid.uuid4()
        mock_db.execute.return_value.all.return_value = [(node, 0), (parent, 1)]

        result = service.get_ancestor_category_ids(
            mock_db, org_id, node, include_self=True
        )

        assert result == [node, parent]

    def test_root_node_no_parents(self, service, mock_db, org_id):
        root = uuid.uuid4()
        mock_db.execute.return_value.all.return_value = [(root, 0)]

        result = service.get_ancestor_category_ids(mock_db, org_id, root)

        assert result == []


class TestCategoryTree:
    def test_builds_depth_annotated_nodes(self, service, mock_db, org_id):
        root_id = uuid.uuid4()
        child_id = uuid.uuid4()
        mock_db.execute.return_value.all.return_value = [
            (
                root_id,
                None,
                "AST",
                "Assets",
                "ASSETS",
                0,
                [root_id],
            ),
            (
                child_id,
                root_id,
                "AST-CUR",
                "Current Assets",
                "ASSETS",
                1,
                [root_id, child_id],
            ),
        ]

        nodes = service.get_category_tree(mock_db, org_id)

        assert len(nodes) == 2
        assert isinstance(nodes[0], CategoryNode)
        assert nodes[0].depth == 0
        assert nodes[0].parent_category_id is None
        assert nodes[0].ifrs_category is IFRSCategory.ASSETS
        assert nodes[1].depth == 1
        assert nodes[1].parent_category_id == root_id
        assert nodes[1].path == [root_id, child_id]

    def test_empty_org_returns_empty(self, service, mock_db, org_id):
        mock_db.execute.return_value.all.return_value = []

        nodes = service.get_category_tree(mock_db, org_id)

        assert nodes == []
