"""
Skills Matrix Service — gap analysis and training alignment.

Compares designation skill requirements against employee skill
assessments to identify gaps, recommend training, and produce
matrix reports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.people.hr.employee import Employee
from app.models.people.hr.employee_extended import EmployeeSkill, Skill
from app.models.people.hr.skill_requirement import ProficiencyLevel, SkillRequirement

logger = logging.getLogger(__name__)


@dataclass
class SkillGap:
    """A single skill gap for an employee."""

    skill_id: UUID
    skill_name: str
    required_level: int
    current_level: int | None  # None = employee doesn't have this skill
    gap: int  # positive = deficit, 0 = met, negative = exceeds
    is_mandatory: bool


@dataclass
class EmployeeGapReport:
    """Gap analysis for one employee."""

    employee_id: UUID
    employee_name: str
    designation_name: str
    total_required: int
    met: int
    gaps: list[SkillGap]
    gap_percentage: Decimal  # 0-100


@dataclass
class DesignationMatrixRow:
    """One row in the skills matrix (designation × skills)."""

    designation_id: UUID
    designation_name: str
    requirements: list[dict]  # [{skill_name, required_level, employee_count_meeting}]


@dataclass
class SkillRequirementInput:
    """Input for creating a skill requirement."""

    designation_id: UUID
    skill_id: UUID
    required_level: int = ProficiencyLevel.INTERMEDIATE
    is_mandatory: bool = True
    notes: str | None = None


class SkillsMatrixService:
    """Service for skills gap analysis and matrix reporting."""

    def __init__(self, db: Session, organization_id: UUID) -> None:
        self.db = db
        self.organization_id = organization_id

    # ── Requirements CRUD ──────────────────────────────────────────

    def add_requirement(self, input: SkillRequirementInput) -> SkillRequirement:
        """Add a skill requirement to a designation."""
        req = SkillRequirement(
            organization_id=self.organization_id,
            designation_id=input.designation_id,
            skill_id=input.skill_id,
            required_level=input.required_level,
            is_mandatory=input.is_mandatory,
            notes=input.notes,
        )
        self.db.add(req)
        self.db.flush()
        logger.info(
            "Added skill requirement: designation=%s skill=%s level=%d",
            input.designation_id,
            input.skill_id,
            input.required_level,
        )
        return req

    def remove_requirement(self, requirement_id: UUID) -> None:
        """Remove a skill requirement."""
        req = self.db.get(SkillRequirement, requirement_id)
        if req and req.organization_id == self.organization_id:
            self.db.delete(req)
            self.db.flush()

    def list_requirements(
        self,
        designation_id: UUID | None = None,
    ) -> list[SkillRequirement]:
        """List skill requirements, optionally filtered by designation."""
        stmt = select(SkillRequirement).where(
            SkillRequirement.organization_id == self.organization_id,
        )
        if designation_id:
            stmt = stmt.where(SkillRequirement.designation_id == designation_id)
        return list(self.db.scalars(stmt).all())

    # ── Gap Analysis ───────────────────────────────────────────────

    def analyze_employee_gaps(self, employee_id: UUID) -> EmployeeGapReport:
        """Analyze skill gaps for a single employee against their designation."""
        employee = self.db.get(Employee, employee_id)
        if not employee:
            raise ValueError(f"Employee {employee_id} not found")

        designation_id = employee.designation_id
        if not designation_id:
            return EmployeeGapReport(
                employee_id=employee_id,
                employee_name=f"{employee.first_name} {employee.last_name}",
                designation_name="(no designation)",
                total_required=0,
                met=0,
                gaps=[],
                gap_percentage=Decimal("0"),
            )

        # Get requirements for this designation
        requirements = self.db.scalars(
            select(SkillRequirement).where(
                SkillRequirement.organization_id == self.organization_id,
                SkillRequirement.designation_id == designation_id,
            )
        ).all()

        # Get employee's current skills
        employee_skills = self.db.scalars(
            select(EmployeeSkill).where(
                EmployeeSkill.organization_id == self.organization_id,
                EmployeeSkill.employee_id == employee_id,
            )
        ).all()
        skill_levels: dict[UUID, int] = {
            es.skill_id: es.proficiency_level or 0 for es in employee_skills
        }

        # Build skill name lookup
        skill_ids = [r.skill_id for r in requirements]
        skills = (
            self.db.scalars(select(Skill).where(Skill.skill_id.in_(skill_ids))).all()
            if skill_ids
            else []
        )
        skill_names: dict[UUID, str] = {s.skill_id: s.skill_name for s in skills}

        # Compare
        gaps: list[SkillGap] = []
        met = 0
        for req in requirements:
            current = skill_levels.get(req.skill_id)
            gap_value = req.required_level - (current or 0)
            if gap_value <= 0:
                met += 1
            gaps.append(
                SkillGap(
                    skill_id=req.skill_id,
                    skill_name=skill_names.get(req.skill_id, "Unknown"),
                    required_level=req.required_level,
                    current_level=current,
                    gap=max(0, gap_value),
                    is_mandatory=req.is_mandatory,
                )
            )

        total = len(requirements)
        gap_pct = (
            Decimal(str((total - met) * 100 / total)).quantize(Decimal("0.1"))
            if total > 0
            else Decimal("0")
        )

        return EmployeeGapReport(
            employee_id=employee_id,
            employee_name=f"{employee.first_name} {employee.last_name}",
            designation_name=(
                employee.designation.designation_name
                if employee.designation
                else "(unknown)"
            ),
            total_required=total,
            met=met,
            gaps=sorted(gaps, key=lambda g: (-g.gap, -g.is_mandatory)),
            gap_percentage=gap_pct,
        )

    def analyze_department_gaps(
        self,
        department_id: UUID,
    ) -> list[EmployeeGapReport]:
        """Analyze skill gaps for all employees in a department."""
        employees = self.db.scalars(
            select(Employee).where(
                Employee.organization_id == self.organization_id,
                Employee.department_id == department_id,
                Employee.status.in_(["ACTIVE", "ON_PROBATION"]),
            )
        ).all()

        reports: list[EmployeeGapReport] = []
        for emp in employees:
            try:
                reports.append(self.analyze_employee_gaps(emp.employee_id))
            except Exception:
                logger.exception("Gap analysis failed for employee %s", emp.employee_id)

        return sorted(reports, key=lambda r: -r.gap_percentage)

    def get_organization_summary(self) -> dict:
        """Get organization-wide skills summary."""
        # Total employees with designations
        total_employees = (
            self.db.scalar(
                select(func.count(Employee.employee_id)).where(
                    Employee.organization_id == self.organization_id,
                    Employee.status.in_(["ACTIVE", "ON_PROBATION"]),
                    Employee.designation_id.isnot(None),
                )
            )
            or 0
        )

        # Total skill requirements defined
        total_requirements = (
            self.db.scalar(
                select(func.count(SkillRequirement.requirement_id)).where(
                    SkillRequirement.organization_id == self.organization_id,
                )
            )
            or 0
        )

        # Designations with requirements
        designations_with_reqs = (
            self.db.scalar(
                select(
                    func.count(func.distinct(SkillRequirement.designation_id))
                ).where(
                    SkillRequirement.organization_id == self.organization_id,
                )
            )
            or 0
        )

        # Employees with at least one skill assessed
        employees_assessed = (
            self.db.scalar(
                select(func.count(func.distinct(EmployeeSkill.employee_id))).where(
                    EmployeeSkill.organization_id == self.organization_id,
                )
            )
            or 0
        )

        return {
            "total_employees": total_employees,
            "total_requirements": total_requirements,
            "designations_with_requirements": designations_with_reqs,
            "employees_assessed": employees_assessed,
            "assessment_coverage": (
                round(employees_assessed * 100 / total_employees, 1)
                if total_employees > 0
                else 0
            ),
        }
