"""
Skill Requirement Model — maps required skills to designations.

Used by the skills matrix for gap analysis: compare what a role
requires vs what the employee actually has.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ProficiencyLevel(int, enum.Enum):
    """Proficiency levels for skill requirements and assessments."""

    BASIC = 1
    INTERMEDIATE = 2
    ADVANCED = 3
    EXPERT = 4
    MASTER = 5


class SkillRequirement(Base):
    """Skill required for a designation (job role).

    Links a Skill to a Designation with a minimum required proficiency
    level.  The skills matrix compares these requirements against
    EmployeeSkill records to identify gaps.
    """

    __tablename__ = "skill_requirement"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "designation_id",
            "skill_id",
            name="uq_skill_requirement",
        ),
        Index("idx_skill_req_designation", "organization_id", "designation_id"),
        Index("idx_skill_req_skill", "organization_id", "skill_id"),
        {"schema": "hr"},
    )

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core_org.organization.organization_id"),
        nullable=False,
    )
    designation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.designation.designation_id"),
        nullable=False,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.skill.skill_id"),
        nullable=False,
    )
    required_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=ProficiencyLevel.INTERMEDIATE,
        comment="Minimum proficiency level required (1-5)",
    )
    is_mandatory: Mapped[bool] = mapped_column(
        default=True,
        comment="If true, this skill is required; if false, nice-to-have",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
