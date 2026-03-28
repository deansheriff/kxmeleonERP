"""
Tests for PerformanceContractService — validation logic.

Tests focus on validation methods and public API contracts
using MagicMock for the DB session.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.services.people.perf.contract_service import (
    ContractNotFoundError,
    ContractServiceError,
    ContractStatusError,
    ContractValidationError,
    PerformanceContractService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_OBJECTIVES = [
    {"title": "Obj A", "weight": 20},
    {"title": "Obj B", "weight": 20},
    {"title": "Obj C", "weight": 30},
]  # 3 objectives, total weight = 70


def make_objectives(count: int, *, total_weight: int = 70) -> list[dict]:
    """Create `count` objectives with weights distributed to sum to total_weight."""
    per = total_weight // count
    remainder = total_weight - per * count
    objs = [{"title": f"Obj {i}", "weight": per} for i in range(count)]
    if objs:
        objs[0]["weight"] += remainder
    return objs


def make_competencies(
    total: int = 5,
    *,
    dev_focus_count: int = 3,
) -> list[dict]:
    """Create competencies with `dev_focus_count` marked as development focus."""
    comps = []
    for i in range(total):
        comps.append(
            {
                "competency_id": str(uuid.uuid4()),
                "is_development_focus": i < dev_focus_count,
            }
        )
    return comps


def make_service() -> PerformanceContractService:
    db = MagicMock()
    return PerformanceContractService(db)


# ---------------------------------------------------------------------------
# Error class hierarchy
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    def test_contract_not_found_is_contract_service_error(self) -> None:
        err = ContractNotFoundError(uuid.uuid4())
        assert isinstance(err, ContractServiceError)

    def test_contract_validation_is_contract_service_error(self) -> None:
        err = ContractValidationError("bad input")
        assert isinstance(err, ContractServiceError)

    def test_contract_status_is_contract_service_error(self) -> None:
        err = ContractStatusError("DRAFT", "ACTIVE")
        assert isinstance(err, ContractServiceError)

    def test_not_found_message_contains_id(self) -> None:
        cid = uuid.uuid4()
        err = ContractNotFoundError(cid)
        assert str(cid) in str(err)

    def test_status_error_message_contains_states(self) -> None:
        err = ContractStatusError("DRAFT", "COMPLETED")
        msg = str(err)
        assert "DRAFT" in msg
        assert "COMPLETED" in msg


# ---------------------------------------------------------------------------
# _validate_objectives
# ---------------------------------------------------------------------------


class TestValidateObjectives:
    """Unit tests for _validate_objectives (private method tested directly)."""

    def setup_method(self) -> None:
        self.service = make_service()

    def test_accepts_valid_objectives(self) -> None:
        """Exactly 3 objectives with weights summing to 70 should not raise."""
        self.service._validate_objectives(VALID_OBJECTIVES)

    def test_accepts_7_objectives(self) -> None:
        objs = make_objectives(7)
        self.service._validate_objectives(objs)

    def test_rejects_fewer_than_3(self) -> None:
        objs = make_objectives(2)
        with pytest.raises(ContractValidationError, match="3"):
            self.service._validate_objectives(objs)

    def test_rejects_empty_list(self) -> None:
        with pytest.raises(ContractValidationError):
            self.service._validate_objectives([])

    def test_rejects_more_than_7(self) -> None:
        objs = make_objectives(8)
        with pytest.raises(ContractValidationError, match="7"):
            self.service._validate_objectives(objs)

    def test_rejects_weights_not_summing_to_70(self) -> None:
        objs = [
            {"title": "A", "weight": 30},
            {"title": "B", "weight": 30},
            {"title": "C", "weight": 30},  # total = 90, not 70
        ]
        with pytest.raises(ContractValidationError, match="70"):
            self.service._validate_objectives(objs)

    def test_rejects_weights_summing_to_less_than_70(self) -> None:
        objs = [
            {"title": "A", "weight": 20},
            {"title": "B", "weight": 20},
            {"title": "C", "weight": 20},  # total = 60
        ]
        with pytest.raises(ContractValidationError, match="70"):
            self.service._validate_objectives(objs)

    def test_boundary_3_objectives_accepted(self) -> None:
        self.service._validate_objectives(make_objectives(3))

    def test_boundary_7_objectives_accepted(self) -> None:
        self.service._validate_objectives(make_objectives(7))


# ---------------------------------------------------------------------------
# _validate_competency_selections
# ---------------------------------------------------------------------------


class TestValidateCompetencies:
    """Unit tests for _validate_competency_selections."""

    def setup_method(self) -> None:
        self.service = make_service()

    def test_accepts_3_development_focus(self) -> None:
        comps = make_competencies(5, dev_focus_count=3)
        self.service._validate_competency_selections(comps)

    def test_accepts_exactly_3_when_all_marked(self) -> None:
        comps = make_competencies(3, dev_focus_count=3)
        self.service._validate_competency_selections(comps)

    def test_rejects_not_exactly_3_development_focus_too_few(self) -> None:
        comps = make_competencies(5, dev_focus_count=2)
        with pytest.raises(ContractValidationError, match="3"):
            self.service._validate_competency_selections(comps)

    def test_rejects_not_exactly_3_development_focus_too_many(self) -> None:
        comps = make_competencies(5, dev_focus_count=4)
        with pytest.raises(ContractValidationError, match="3"):
            self.service._validate_competency_selections(comps)

    def test_rejects_zero_development_focus(self) -> None:
        comps = make_competencies(5, dev_focus_count=0)
        with pytest.raises(ContractValidationError, match="3"):
            self.service._validate_competency_selections(comps)

    def test_rejects_empty_competency_list(self) -> None:
        with pytest.raises(ContractValidationError, match="3"):
            self.service._validate_competency_selections([])


# ---------------------------------------------------------------------------
# get_contract
# ---------------------------------------------------------------------------


class TestGetContract:
    def setup_method(self) -> None:
        self.db = MagicMock()
        self.service = PerformanceContractService(self.db)

    def test_returns_contract_when_found(self) -> None:
        from app.models.people.perf.performance_contract import PerformanceContract

        org_id = uuid.uuid4()
        contract_id = uuid.uuid4()

        mock_contract = MagicMock(spec=PerformanceContract)
        mock_contract.organization_id = org_id
        mock_contract.contract_id = contract_id

        self.db.scalar.return_value = mock_contract

        result = self.service.get_contract(org_id, contract_id)
        assert result is mock_contract

    def test_raises_not_found_when_missing(self) -> None:
        self.db.scalar.return_value = None
        with pytest.raises(ContractNotFoundError):
            self.service.get_contract(uuid.uuid4(), uuid.uuid4())


# ---------------------------------------------------------------------------
# sign_employee / sign_supervisor — status transitions
# ---------------------------------------------------------------------------


class TestSignEmployee:
    def _make_contract(
        self,
        *,
        employee_signed: bool = False,
        supervisor_signed: bool = False,
    ):
        from app.models.people.perf.performance_contract import PerformanceContract
        from app.models.people.perf.pms_enums import ContractStatus

        c = MagicMock(spec=PerformanceContract)
        c.employee_signed_date = date.today() if employee_signed else None
        c.supervisor_signed_date = date.today() if supervisor_signed else None
        c.status = ContractStatus.PENDING_SIGNATURE
        c.organization_id = uuid.uuid4()
        c.contract_id = uuid.uuid4()
        return c

    def test_sets_employee_signed_date(self) -> None:

        db = MagicMock()
        service = PerformanceContractService(db)
        contract = self._make_contract()
        db.scalar.return_value = contract

        service.sign_employee(contract.organization_id, contract.contract_id)

        assert contract.employee_signed_date == date.today()

    def test_both_signed_sets_active(self) -> None:
        from app.models.people.perf.pms_enums import ContractStatus

        db = MagicMock()
        service = PerformanceContractService(db)
        # supervisor already signed
        contract = self._make_contract(supervisor_signed=True)
        db.scalar.return_value = contract

        service.sign_employee(contract.organization_id, contract.contract_id)

        assert contract.status == ContractStatus.ACTIVE

    def test_only_employee_signed_remains_pending(self) -> None:
        from app.models.people.perf.pms_enums import ContractStatus

        db = MagicMock()
        service = PerformanceContractService(db)
        contract = self._make_contract(supervisor_signed=False)
        db.scalar.return_value = contract

        service.sign_employee(contract.organization_id, contract.contract_id)

        assert contract.status == ContractStatus.PENDING_SIGNATURE


class TestSignSupervisor:
    def _make_contract(
        self,
        *,
        employee_signed: bool = False,
        supervisor_signed: bool = False,
    ):
        from app.models.people.perf.performance_contract import PerformanceContract
        from app.models.people.perf.pms_enums import ContractStatus

        c = MagicMock(spec=PerformanceContract)
        c.employee_signed_date = date.today() if employee_signed else None
        c.supervisor_signed_date = date.today() if supervisor_signed else None
        c.status = ContractStatus.PENDING_SIGNATURE
        c.organization_id = uuid.uuid4()
        c.contract_id = uuid.uuid4()
        return c

    def test_sets_supervisor_signed_date(self) -> None:
        db = MagicMock()
        service = PerformanceContractService(db)
        contract = self._make_contract()
        db.scalar.return_value = contract

        service.sign_supervisor(contract.organization_id, contract.contract_id)

        assert contract.supervisor_signed_date == date.today()

    def test_both_signed_sets_active(self) -> None:
        from app.models.people.perf.pms_enums import ContractStatus

        db = MagicMock()
        service = PerformanceContractService(db)
        contract = self._make_contract(employee_signed=True)
        db.scalar.return_value = contract

        service.sign_supervisor(contract.organization_id, contract.contract_id)

        assert contract.status == ContractStatus.ACTIVE

    def test_only_supervisor_signed_remains_pending(self) -> None:
        from app.models.people.perf.pms_enums import ContractStatus

        db = MagicMock()
        service = PerformanceContractService(db)
        contract = self._make_contract(employee_signed=False)
        db.scalar.return_value = contract

        service.sign_supervisor(contract.organization_id, contract.contract_id)

        assert contract.status == ContractStatus.PENDING_SIGNATURE


# ---------------------------------------------------------------------------
# countersign
# ---------------------------------------------------------------------------


class TestCountersign:
    def _make_contract(self, *, employee_signed: bool = True):
        from app.models.people.perf.performance_contract import PerformanceContract
        from app.models.people.perf.pms_enums import ContractStatus

        c = MagicMock(spec=PerformanceContract)
        c.employee_signed_date = date.today() if employee_signed else None
        c.countersigner_id = None
        c.countersigner_date = None
        c.status = ContractStatus.PENDING_SIGNATURE
        c.organization_id = uuid.uuid4()
        c.contract_id = uuid.uuid4()
        return c

    def test_sets_countersigner_id_and_date(self) -> None:
        db = MagicMock()
        service = PerformanceContractService(db)
        contract = self._make_contract()
        db.scalar.return_value = contract
        countersigner_id = uuid.uuid4()

        service.countersign(
            contract.organization_id, contract.contract_id, countersigner_id
        )

        assert contract.countersigner_id == countersigner_id
        assert contract.countersigner_date == date.today()

    def test_countersign_makes_contract_active(self) -> None:
        from app.models.people.perf.pms_enums import ContractStatus

        db = MagicMock()
        service = PerformanceContractService(db)
        contract = self._make_contract(employee_signed=False)
        db.scalar.return_value = contract

        service.countersign(
            contract.organization_id, contract.contract_id, uuid.uuid4()
        )

        assert contract.status == ContractStatus.ACTIVE


# ---------------------------------------------------------------------------
# amend_contract
# ---------------------------------------------------------------------------


class TestAmendContract:
    def _make_active_contract(self) -> MagicMock:
        from app.models.people.perf.performance_contract import PerformanceContract
        from app.models.people.perf.pms_enums import ContractStatus

        c = MagicMock(spec=PerformanceContract)
        c.contract_id = uuid.uuid4()
        c.organization_id = uuid.uuid4()
        c.status = ContractStatus.ACTIVE
        c.contract_code = "PC-2026-001"
        c.cycle_id = uuid.uuid4()
        c.employee_id = uuid.uuid4()
        c.supervisor_id = uuid.uuid4()
        c.contract_type = "INDIVIDUAL"
        c.competency_ids = []
        c.development_plan = None
        return c

    def test_original_contract_marked_as_amended(self) -> None:
        from app.models.people.perf.pms_enums import ContractStatus

        db = MagicMock()
        service = PerformanceContractService(db)
        original = self._make_active_contract()
        db.scalar.return_value = original

        new_objs = make_objectives(3)

        # Mock the db.add so we can inspect the new contract
        added = []
        db.add.side_effect = lambda obj: added.append(obj)

        service.amend_contract(
            original.organization_id,
            original.contract_id,
            new_objectives=new_objs,
            amendment_reason="Restructured targets",
        )

        assert original.status == ContractStatus.AMENDED

    def test_amended_code_has_suffix(self) -> None:
        db = MagicMock()
        service = PerformanceContractService(db)
        original = self._make_active_contract()
        db.scalar.return_value = original

        added = []
        db.add.side_effect = lambda obj: added.append(obj)

        service.amend_contract(
            original.organization_id,
            original.contract_id,
            new_objectives=make_objectives(3),
            amendment_reason="Test",
        )

        assert len(added) == 1
        new_contract = added[0]
        assert new_contract.contract_code.endswith("-A")

    def test_new_contract_references_original(self) -> None:
        db = MagicMock()
        service = PerformanceContractService(db)
        original = self._make_active_contract()
        db.scalar.return_value = original

        added = []
        db.add.side_effect = lambda obj: added.append(obj)

        service.amend_contract(
            original.organization_id,
            original.contract_id,
            new_objectives=make_objectives(3),
            amendment_reason="Restructured",
        )

        new_contract = added[0]
        assert new_contract.amended_from_id == original.contract_id

    def test_amend_validates_new_objectives(self) -> None:
        db = MagicMock()
        service = PerformanceContractService(db)
        original = self._make_active_contract()
        db.scalar.return_value = original

        bad_objectives = make_objectives(2)  # less than 3
        with pytest.raises(ContractValidationError):
            service.amend_contract(
                original.organization_id,
                original.contract_id,
                new_objectives=bad_objectives,
                amendment_reason="Bad",
            )
