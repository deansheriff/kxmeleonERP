"""
Test suite for PerformanceContract model.

Verifies model instantiation, default values, field definitions,
table configuration, and relationship declarations.
"""

import uuid

from app.models.people.perf.performance_contract import PerformanceContract
from app.models.people.perf.pms_enums import ContractStatus, ContractType


class TestPerformanceContractInstantiation:
    """Tests for model instantiation with required fields."""

    def test_instantiate_with_required_fields(self):
        """Model can be instantiated with all required fields."""
        org_id = uuid.uuid4()
        cycle_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        supervisor_id = uuid.uuid4()

        contract = PerformanceContract(
            organization_id=org_id,
            cycle_id=cycle_id,
            employee_id=employee_id,
            supervisor_id=supervisor_id,
            contract_code="PC-2026-001",
            contract_type=ContractType.INDIVIDUAL,
            objectives=[{"kra": "Revenue growth", "weight": 40}],
        )

        assert contract.organization_id == org_id
        assert contract.cycle_id == cycle_id
        assert contract.employee_id == employee_id
        assert contract.supervisor_id == supervisor_id
        assert contract.contract_code == "PC-2026-001"
        assert contract.contract_type == ContractType.INDIVIDUAL
        assert contract.objectives == [{"kra": "Revenue growth", "weight": 40}]

    def test_repr(self):
        """Model has a meaningful __repr__."""
        contract = PerformanceContract(contract_code="PC-2026-001")
        assert "PC-2026-001" in repr(contract)


class TestPerformanceContractDefaults:
    """Tests for default field values."""

    def test_default_status_is_draft(self):
        """Status column has DRAFT as its Python-level default."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(PerformanceContract)
        col = mapper.columns["status"]
        # The column default is set to ContractStatus.DRAFT
        assert col.default is not None
        assert col.default.arg == ContractStatus.DRAFT

    def test_contract_id_column_has_uuid_default(self):
        """contract_id column has a callable default (uuid generator)."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(PerformanceContract)
        col = mapper.columns["contract_id"]
        assert col.default is not None
        # The default is a callable (uuid.uuid4 or similar)
        assert callable(col.default.arg)
        assert col.default.arg.__name__ == "uuid4"

    def test_nullable_fields_default_to_none(self):
        """All nullable fields default to None."""
        contract = PerformanceContract()
        assert contract.competency_ids is None
        assert contract.development_plan is None
        assert contract.employee_signed_date is None
        assert contract.supervisor_signed_date is None
        assert contract.countersigner_id is None
        assert contract.countersigner_date is None
        assert contract.amended_from_id is None
        assert contract.amendment_reason is None
        assert contract.updated_at is None

    def test_objectives_can_be_empty_list(self):
        """Objectives can be set as an empty list."""
        contract = PerformanceContract(objectives=[])
        assert contract.objectives == []


class TestPerformanceContractTableConfig:
    """Tests for SQLAlchemy table configuration."""

    def test_table_name(self):
        """Table name is 'performance_contract'."""
        assert PerformanceContract.__tablename__ == "performance_contract"

    def test_schema(self):
        """Table is in the 'perf' schema."""
        table_args = PerformanceContract.__table_args__
        # Last element of tuple is the dict with schema
        schema_dict = table_args[-1]
        assert isinstance(schema_dict, dict)
        assert schema_dict.get("schema") == "perf"

    def test_unique_constraint_exists(self):
        """UniqueConstraint on organization_id + contract_code exists."""
        table_args = PerformanceContract.__table_args__
        from sqlalchemy import UniqueConstraint

        constraints = [a for a in table_args if isinstance(a, UniqueConstraint)]
        assert len(constraints) == 1
        uc = constraints[0]
        assert uc.name == "uq_perf_contract_code"

    def test_indexes_exist(self):
        """All required indexes are declared."""
        table_args = PerformanceContract.__table_args__
        from sqlalchemy import Index

        indexes = [a for a in table_args if isinstance(a, Index)]
        index_names = {idx.name for idx in indexes}
        assert "idx_contract_employee" in index_names
        assert "idx_contract_cycle" in index_names
        assert "idx_contract_org_status" in index_names


class TestPerformanceContractFields:
    """Tests for individual field properties."""

    def test_contract_type_accepts_all_enum_values(self):
        """contract_type accepts all ContractType enum values."""
        for ct in ContractType:
            contract = PerformanceContract(contract_type=ct)
            assert contract.contract_type == ct

    def test_status_accepts_all_enum_values(self):
        """status accepts all ContractStatus enum values."""
        for cs in ContractStatus:
            contract = PerformanceContract(status=cs)
            assert contract.status == cs

    def test_competency_ids_accepts_list(self):
        """competency_ids accepts a list of UUIDs (as strings)."""
        ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        contract = PerformanceContract(competency_ids=ids)
        assert contract.competency_ids == ids

    def test_development_plan_accepts_text(self):
        """development_plan accepts multiline text."""
        plan = "Step 1: Do X\nStep 2: Do Y"
        contract = PerformanceContract(development_plan=plan)
        assert contract.development_plan == plan

    def test_amendment_reason_accepts_text(self):
        """amendment_reason accepts text."""
        contract = PerformanceContract(amendment_reason="Scope changed")
        assert contract.amendment_reason == "Scope changed"

    def test_amended_from_id_accepts_uuid(self):
        """amended_from_id accepts a UUID (self-reference)."""
        parent_id = uuid.uuid4()
        contract = PerformanceContract(amended_from_id=parent_id)
        assert contract.amended_from_id == parent_id

    def test_countersigner_id_accepts_uuid(self):
        """countersigner_id accepts a UUID."""
        counter_id = uuid.uuid4()
        contract = PerformanceContract(countersigner_id=counter_id)
        assert contract.countersigner_id == counter_id


class TestPerformanceContractRelationships:
    """Tests for relationship declarations on the model."""

    def test_employee_relationship_declared(self):
        """'employee' relationship is declared."""
        assert hasattr(PerformanceContract, "employee")

    def test_supervisor_relationship_declared(self):
        """'supervisor' relationship is declared."""
        assert hasattr(PerformanceContract, "supervisor")

    def test_countersigner_relationship_declared(self):
        """'countersigner' relationship is declared."""
        assert hasattr(PerformanceContract, "countersigner")

    def test_cycle_relationship_declared(self):
        """'cycle' relationship is declared."""
        assert hasattr(PerformanceContract, "cycle")

    def test_amended_from_relationship_declared(self):
        """'amended_from' self-referential relationship is declared."""
        assert hasattr(PerformanceContract, "amended_from")

    def test_amendments_relationship_declared(self):
        """'amendments' back-reference relationship is declared."""
        assert hasattr(PerformanceContract, "amendments")


class TestPerformanceContractInheritance:
    """Tests for proper base class inheritance."""

    def test_inherits_audit_mixin(self):
        """PerformanceContract inherits from AuditMixin."""
        from app.models.people.base import AuditMixin

        assert isinstance(PerformanceContract(), AuditMixin)

    def test_audit_mixin_fields_present(self):
        """AuditMixin fields (created_by_id, updated_by_id) are present."""
        contract = PerformanceContract()
        assert hasattr(contract, "created_by_id")
        assert hasattr(contract, "updated_by_id")
