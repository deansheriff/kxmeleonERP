"""
Tests for StrategicObjectiveService — OHCSF PMS.

Tests focus on:
- Error class hierarchy
- get_objective / list_objectives
- create_objective: flush + log
- update_objective: allowed fields only
- delete_objective: guard against children / linked KPIs
- get_cascade_tree: hierarchical tree from flat list
- get_alignment_report: KPI gap identification

Uses MagicMock for the DB session so no DB is required.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.people.perf.strategic_objective import StrategicObjective
from app.services.people.perf.strategic_objective_service import (
    StrategicObjectiveNotFoundError,
    StrategicObjectiveService,
    StrategicObjectiveServiceError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ORG_ID = uuid.uuid4()
CYCLE_ID = uuid.uuid4()
DEPT_ID = uuid.uuid4()
OBJ_ID = uuid.uuid4()
CHILD_ID = uuid.uuid4()


def make_service() -> StrategicObjectiveService:
    db = MagicMock()
    return StrategicObjectiveService(db)


def make_objective(
    *,
    objective_id: uuid.UUID | None = None,
    cycle_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    parent_objective_id: uuid.UUID | None = None,
    objective_code: str = "SO-001",
    description: str = "Test objective",
    weight: Decimal | None = None,
) -> StrategicObjective:
    obj = StrategicObjective(
        organization_id=ORG_ID,
        cycle_id=cycle_id or CYCLE_ID,
        department_id=department_id,
        parent_objective_id=parent_objective_id,
        objective_code=objective_code,
        description=description,
        weight=weight,
    )
    obj.objective_id = objective_id or uuid.uuid4()
    return obj


# ---------------------------------------------------------------------------
# Error class hierarchy
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    def test_not_found_is_base(self) -> None:
        err = StrategicObjectiveNotFoundError(uuid.uuid4())
        assert isinstance(err, StrategicObjectiveServiceError)

    def test_not_found_message_contains_id(self) -> None:
        some_id = uuid.uuid4()
        err = StrategicObjectiveNotFoundError(some_id)
        assert str(some_id) in str(err)

    def test_base_is_exception(self) -> None:
        err = StrategicObjectiveServiceError("some error")
        assert isinstance(err, Exception)


# ---------------------------------------------------------------------------
# get_objective
# ---------------------------------------------------------------------------


class TestGetObjective:
    def test_returns_record_when_found(self) -> None:
        svc = make_service()
        obj = make_objective()
        svc.db.scalar.return_value = obj

        result = svc.get_objective(ORG_ID, obj.objective_id)

        assert result is obj

    def test_raises_not_found_when_missing(self) -> None:
        svc = make_service()
        svc.db.scalar.return_value = None

        with pytest.raises(StrategicObjectiveNotFoundError) as exc_info:
            svc.get_objective(ORG_ID, OBJ_ID)

        assert exc_info.value.objective_id == OBJ_ID


# ---------------------------------------------------------------------------
# list_objectives
# ---------------------------------------------------------------------------


class TestListObjectives:
    def test_returns_paginated_result(self) -> None:
        svc = make_service()
        obj = make_objective()
        svc.db.scalar.return_value = 1  # count
        svc.db.scalars.return_value.all.return_value = [obj]

        result = svc.list_objectives(ORG_ID)

        assert result.total >= 0

    def test_accepts_cycle_id_filter(self) -> None:
        svc = make_service()
        svc.db.scalar.return_value = 0
        svc.db.scalars.return_value.all.return_value = []

        result = svc.list_objectives(ORG_ID, cycle_id=CYCLE_ID)

        assert result.total == 0

    def test_accepts_department_id_filter(self) -> None:
        svc = make_service()
        svc.db.scalar.return_value = 0
        svc.db.scalars.return_value.all.return_value = []

        result = svc.list_objectives(ORG_ID, department_id=DEPT_ID)

        assert result.total == 0

    def test_accepts_search_filter(self) -> None:
        svc = make_service()
        svc.db.scalar.return_value = 0
        svc.db.scalars.return_value.all.return_value = []

        result = svc.list_objectives(ORG_ID, search="strategic")

        assert result.total == 0


# ---------------------------------------------------------------------------
# create_objective
# ---------------------------------------------------------------------------


class TestCreateObjective:
    def test_returns_objective_with_correct_fields(self) -> None:
        svc = make_service()

        result = svc.create_objective(
            ORG_ID,
            cycle_id=CYCLE_ID,
            objective_code="SO-001",
            description="Improve service delivery",
        )

        assert result.organization_id == ORG_ID
        assert result.cycle_id == CYCLE_ID
        assert result.objective_code == "SO-001"
        assert result.description == "Improve service delivery"

    def test_optional_fields_accepted(self) -> None:
        svc = make_service()

        result = svc.create_objective(
            ORG_ID,
            cycle_id=CYCLE_ID,
            objective_code="SO-002",
            description="Dept goal",
            department_id=DEPT_ID,
            parent_objective_id=OBJ_ID,
            source_document="State Development Plan 2026",
            target_description="Achieve 80% within Q4",
            weight=Decimal("25.00"),
        )

        assert result.department_id == DEPT_ID
        assert result.parent_objective_id == OBJ_ID
        assert result.source_document == "State Development Plan 2026"
        assert result.target_description == "Achieve 80% within Q4"
        assert result.weight == Decimal("25.00")

    def test_db_add_and_flush_called(self) -> None:
        svc = make_service()

        svc.create_objective(
            ORG_ID,
            cycle_id=CYCLE_ID,
            objective_code="SO-003",
            description="Test",
        )

        svc.db.add.assert_called_once()
        svc.db.flush.assert_called_once()

    def test_optional_fields_default_to_none(self) -> None:
        svc = make_service()

        result = svc.create_objective(
            ORG_ID,
            cycle_id=CYCLE_ID,
            objective_code="SO-004",
            description="Minimal",
        )

        assert result.department_id is None
        assert result.parent_objective_id is None
        assert result.source_document is None
        assert result.target_description is None
        assert result.weight is None


# ---------------------------------------------------------------------------
# update_objective
# ---------------------------------------------------------------------------


class TestUpdateObjective:
    def test_updates_allowed_fields(self) -> None:
        svc = make_service()
        obj = make_objective()
        svc.db.scalar.return_value = obj

        result = svc.update_objective(
            ORG_ID,
            obj.objective_id,
            description="Updated description",
            weight=Decimal("30.00"),
            source_document="New plan",
            target_description="New target",
        )

        assert result.description == "Updated description"
        assert result.weight == Decimal("30.00")
        assert result.source_document == "New plan"
        assert result.target_description == "New target"

    def test_raises_not_found_for_missing_objective(self) -> None:
        svc = make_service()
        svc.db.scalar.return_value = None

        with pytest.raises(StrategicObjectiveNotFoundError):
            svc.update_objective(ORG_ID, OBJ_ID, description="New")

    def test_db_flush_called_on_update(self) -> None:
        svc = make_service()
        obj = make_objective()
        svc.db.scalar.return_value = obj

        svc.update_objective(ORG_ID, obj.objective_id, description="Changed")

        svc.db.flush.assert_called_once()

    def test_ignores_unknown_kwargs(self) -> None:
        """Non-allowed kwargs must not raise, they are silently ignored."""
        svc = make_service()
        obj = make_objective()
        svc.db.scalar.return_value = obj

        # Should not raise
        result = svc.update_objective(
            ORG_ID,
            obj.objective_id,
            nonexistent_field="boom",
        )
        assert result is obj


# ---------------------------------------------------------------------------
# delete_objective
# ---------------------------------------------------------------------------


class TestDeleteObjective:
    def test_deletes_leaf_objective(self) -> None:
        svc = make_service()
        obj = make_objective()
        svc.db.scalar.return_value = obj
        # No children, no KPIs
        svc.db.scalars.return_value.all.return_value = []

        svc.delete_objective(ORG_ID, obj.objective_id)

        svc.db.delete.assert_called_once_with(obj)
        svc.db.flush.assert_called_once()

    def test_raises_not_found_for_missing_objective(self) -> None:
        svc = make_service()
        svc.db.scalar.return_value = None

        with pytest.raises(StrategicObjectiveNotFoundError):
            svc.delete_objective(ORG_ID, OBJ_ID)

    def test_raises_when_child_objectives_exist(self) -> None:
        svc = make_service()
        obj = make_objective()
        child = make_objective(
            objective_code="SO-CHILD",
            parent_objective_id=obj.objective_id,
        )
        svc.db.scalar.return_value = obj

        # First scalars call returns children, so we simulate it having children
        def scalar_side_effect(stmt):
            return obj

        def scalars_side_effect(stmt):
            mock = MagicMock()
            mock.all.return_value = [child]
            return mock

        svc.db.scalar.side_effect = scalar_side_effect
        svc.db.scalars.side_effect = scalars_side_effect

        with pytest.raises(StrategicObjectiveServiceError, match="child"):
            svc.delete_objective(ORG_ID, obj.objective_id)

    def test_raises_when_linked_kpis_exist(self) -> None:
        svc = make_service()
        obj = make_objective()

        call_count = 0

        def scalars_side_effect(stmt):
            nonlocal call_count
            mock = MagicMock()
            if call_count == 0:
                # First call: check for children — none
                mock.all.return_value = []
            else:
                # Second call: check for linked KPIs — one exists
                mock.all.return_value = [MagicMock()]
            call_count += 1
            return mock

        svc.db.scalar.return_value = obj
        svc.db.scalars.side_effect = scalars_side_effect

        with pytest.raises(StrategicObjectiveServiceError, match="KPI"):
            svc.delete_objective(ORG_ID, obj.objective_id)


# ---------------------------------------------------------------------------
# get_cascade_tree
# ---------------------------------------------------------------------------


class TestCascadeTree:
    def test_returns_empty_list_for_no_objectives(self) -> None:
        svc = make_service()
        svc.db.scalars.return_value.all.return_value = []

        result = svc.get_cascade_tree(ORG_ID, CYCLE_ID)

        assert result == []

    def test_builds_hierarchy_from_flat_list(self) -> None:
        """Root objectives become top-level entries; children are nested."""
        svc = make_service()

        root_id = uuid.uuid4()
        child_id = uuid.uuid4()
        grandchild_id = uuid.uuid4()

        root = make_objective(
            objective_id=root_id,
            objective_code="SO-ROOT",
            description="Root objective",
            parent_objective_id=None,
        )
        child = make_objective(
            objective_id=child_id,
            objective_code="SO-CHILD",
            description="Child objective",
            parent_objective_id=root_id,
        )
        grandchild = make_objective(
            objective_id=grandchild_id,
            objective_code="SO-GRAND",
            description="Grandchild objective",
            parent_objective_id=child_id,
        )

        svc.db.scalars.return_value.all.return_value = [root, child, grandchild]

        tree = svc.get_cascade_tree(ORG_ID, CYCLE_ID)

        assert len(tree) == 1
        root_node = tree[0]
        assert root_node["objective_id"] == root_id
        assert len(root_node["children"]) == 1

        child_node = root_node["children"][0]
        assert child_node["objective_id"] == child_id
        assert len(child_node["children"]) == 1

        grandchild_node = child_node["children"][0]
        assert grandchild_node["objective_id"] == grandchild_id
        assert grandchild_node["children"] == []

    def test_multiple_root_objectives(self) -> None:
        svc = make_service()

        root_a = make_objective(objective_id=uuid.uuid4(), objective_code="SO-A")
        root_b = make_objective(objective_id=uuid.uuid4(), objective_code="SO-B")

        svc.db.scalars.return_value.all.return_value = [root_a, root_b]

        tree = svc.get_cascade_tree(ORG_ID, CYCLE_ID)

        assert len(tree) == 2

    def test_tree_nodes_contain_expected_keys(self) -> None:
        svc = make_service()
        root = make_objective(objective_id=uuid.uuid4(), objective_code="SO-001")
        svc.db.scalars.return_value.all.return_value = [root]

        tree = svc.get_cascade_tree(ORG_ID, CYCLE_ID)

        node = tree[0]
        assert "objective_id" in node
        assert "objective_code" in node
        assert "description" in node
        assert "children" in node

    def test_orphan_nodes_attached_to_root_when_parent_missing(self) -> None:
        """Objectives whose parent is not in the result set are treated as root nodes."""
        svc = make_service()

        missing_parent_id = uuid.uuid4()
        orphan = make_objective(
            objective_id=uuid.uuid4(),
            objective_code="SO-ORPHAN",
            parent_objective_id=missing_parent_id,
        )

        svc.db.scalars.return_value.all.return_value = [orphan]

        tree = svc.get_cascade_tree(ORG_ID, CYCLE_ID)

        assert len(tree) == 1
        assert tree[0]["objective_code"] == "SO-ORPHAN"


# ---------------------------------------------------------------------------
# get_alignment_report
# ---------------------------------------------------------------------------


class TestAlignmentReport:
    def test_returns_expected_top_level_keys(self) -> None:
        svc = make_service()
        svc.db.scalars.return_value.all.return_value = []
        svc.db.scalar.return_value = 0

        report = svc.get_alignment_report(ORG_ID, CYCLE_ID)

        assert "objectives" in report
        assert "total_objectives" in report
        assert "aligned_count" in report
        assert "gap_count" in report
        assert "alignment_percentage" in report

    def test_empty_cycle_returns_zero_counts(self) -> None:
        svc = make_service()
        svc.db.scalars.return_value.all.return_value = []

        report = svc.get_alignment_report(ORG_ID, CYCLE_ID)

        assert report["total_objectives"] == 0
        assert report["aligned_count"] == 0
        assert report["gap_count"] == 0
        assert report["alignment_percentage"] == 0.0

    def test_identifies_gaps(self) -> None:
        """Objectives with no linked KPIs are flagged as gaps."""
        svc = make_service()

        obj_a = make_objective(objective_id=uuid.uuid4(), objective_code="SO-A")
        obj_b = make_objective(objective_id=uuid.uuid4(), objective_code="SO-B")

        # Both objectives are in the list
        call_count = 0

        def scalars_side_effect(stmt):
            nonlocal call_count
            mock = MagicMock()
            if call_count == 0:
                # First call: list objectives for the cycle
                mock.all.return_value = [obj_a, obj_b]
            call_count += 1
            return mock

        def scalar_side_effect(stmt):
            # KPI count queries: obj_a has 2 KPIs, obj_b has 0
            # We need to return based on the objective being queried.
            # In the service, scalar is called per objective for count.
            return 0  # default: no KPIs

        svc.db.scalars.side_effect = scalars_side_effect
        svc.db.scalar.side_effect = scalar_side_effect

        report = svc.get_alignment_report(ORG_ID, CYCLE_ID)

        assert report["total_objectives"] == 2
        assert report["gap_count"] == 2  # both have 0 KPIs

        for entry in report["objectives"]:
            assert entry["has_gap"] is True

    def test_aligned_objectives_counted_correctly(self) -> None:
        """Objectives with at least one linked KPI are counted as aligned."""
        svc = make_service()

        obj_a = make_objective(objective_id=uuid.uuid4(), objective_code="SO-A")

        call_count = 0

        def scalars_side_effect(stmt):
            nonlocal call_count
            mock = MagicMock()
            if call_count == 0:
                mock.all.return_value = [obj_a]
            call_count += 1
            return mock

        kpi_call_count = 0

        def scalar_side_effect(stmt):
            nonlocal kpi_call_count
            kpi_call_count += 1
            return 3  # obj_a has 3 KPIs

        svc.db.scalars.side_effect = scalars_side_effect
        svc.db.scalar.side_effect = scalar_side_effect

        report = svc.get_alignment_report(ORG_ID, CYCLE_ID)

        assert report["total_objectives"] == 1
        assert report["aligned_count"] == 1
        assert report["gap_count"] == 0
        assert report["alignment_percentage"] == 100.0
        assert report["objectives"][0]["has_gap"] is False
        assert report["objectives"][0]["kpi_count"] == 3

    def test_objective_entries_have_expected_keys(self) -> None:
        svc = make_service()
        obj = make_objective(objective_id=uuid.uuid4(), objective_code="SO-001")

        def scalars_side_effect(stmt):
            mock = MagicMock()
            mock.all.return_value = [obj]
            return mock

        svc.db.scalars.side_effect = scalars_side_effect
        svc.db.scalar.return_value = 0

        report = svc.get_alignment_report(ORG_ID, CYCLE_ID)

        entry = report["objectives"][0]
        assert "objective_id" in entry
        assert "code" in entry
        assert "description" in entry
        assert "kpi_count" in entry
        assert "has_gap" in entry

    def test_alignment_percentage_calculation(self) -> None:
        """alignment_percentage = (aligned / total) * 100."""
        svc = make_service()

        obj_a = make_objective(objective_id=uuid.uuid4(), objective_code="SO-A")
        obj_b = make_objective(objective_id=uuid.uuid4(), objective_code="SO-B")
        obj_c = make_objective(objective_id=uuid.uuid4(), objective_code="SO-C")
        obj_d = make_objective(objective_id=uuid.uuid4(), objective_code="SO-D")

        list_call = 0

        def scalars_side_effect(stmt):
            nonlocal list_call
            mock = MagicMock()
            if list_call == 0:
                mock.all.return_value = [obj_a, obj_b, obj_c, obj_d]
            list_call += 1
            return mock

        kpi_counts = iter([2, 0, 1, 0])  # obj_a=2, obj_b=0, obj_c=1, obj_d=0

        def scalar_side_effect(stmt):
            return next(kpi_counts)

        svc.db.scalars.side_effect = scalars_side_effect
        svc.db.scalar.side_effect = scalar_side_effect

        report = svc.get_alignment_report(ORG_ID, CYCLE_ID)

        assert report["total_objectives"] == 4
        assert report["aligned_count"] == 2  # obj_a, obj_c
        assert report["gap_count"] == 2  # obj_b, obj_d
        assert report["alignment_percentage"] == 50.0
