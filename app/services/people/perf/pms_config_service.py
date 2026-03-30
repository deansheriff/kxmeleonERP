"""
PMS Config Service — first-time activation for OHCSF Performance Management.

Seeds the OHCSF competency framework (18 competencies across 5 clusters) and
institutional criteria weight templates (8 criteria × 6 institution types)
when `pms_ohcsf_enabled` is toggled on for an organisation.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Seed data constants
# ---------------------------------------------------------------------------

# Maps cluster name -> list of (competency_code, competency_name)
OHCSF_COMPETENCIES: dict[str, list[tuple[str, str]]] = {
    "ETHICS_AND_VALUES": [
        ("OHCSF-COMMITMENT", "Commitment"),
        ("OHCSF-INTEGRITY", "Integrity"),
        ("OHCSF-INCLUSIVENESS", "Inclusiveness"),
        ("OHCSF-COURAGE", "Courage"),
    ],
    "PEOPLE": [
        ("OHCSF-COLLABORATING", "Collaborating & Partnering"),
        ("OHCSF-COMMUNICATION", "Effective Communication"),
        ("OHCSF-MNG-PEOPLE", "Managing & Developing People"),
    ],
    "EXECUTION": [
        ("OHCSF-DRIVE-RESULTS", "Drive for Results"),
        ("OHCSF-TRANSPARENCY", "Transparency and Accountability"),
        ("OHCSF-VALUE-MONEY", "Value for Money"),
    ],
    "VISION": [
        ("OHCSF-DECISION", "Effective Decision Making"),
        ("OHCSF-STRAT-THINK", "Strategic Thinking"),
        ("OHCSF-CHANGE-MGMT", "Embracing and Managing Change"),
    ],
    "EXPERTISE": [
        ("OHCSF-POLICY-MGMT", "Policy Management"),
        ("OHCSF-CITIZEN-FOCUS", "Citizen Focus"),
        ("OHCSF-INFO-RECORDS", "Information and Records Management"),
        ("OHCSF-TECHNOLOGY", "Adoption and Use of Technology"),
        ("OHCSF-SPECIALIST", "Specialist Competencies"),
    ],
}

# Maps institution type -> list of (criteria_name, default_weight)
# Each list sums to exactly 100.
OHCSF_INSTITUTIONAL_WEIGHTS: dict[str, list[tuple[str, int]]] = {
    "MINISTRY": [
        ("Government prioritized objectives", 25),
        ("MDA Operational Objectives", 25),
        ("Stakeholder Engagement", 10),
        ("Service Innovation and Improvement", 10),
        ("Automated Service Delivery", 10),
        ("Capacity Building & Talent Management", 5),
        ("Support for Service Delivery", 10),
        ("Staff Welfare", 5),
    ],
    "REGULATORY": [
        ("Government prioritized objectives", 25),
        ("MDA Operational Objectives", 25),
        ("Stakeholder Engagement", 10),
        ("Service Innovation and Improvement", 10),
        ("Automated Service Delivery", 10),
        ("Capacity Building & Talent Management", 5),
        ("Support for Service Delivery", 10),
        ("Staff Welfare", 5),
    ],
    "GENERAL_SERVICES": [
        ("Government prioritized objectives", 20),
        ("MDA Operational Objectives", 20),
        ("Stakeholder Engagement", 5),
        ("Service Innovation and Improvement", 20),
        ("Automated Service Delivery", 15),
        ("Capacity Building & Talent Management", 5),
        ("Support for Service Delivery", 10),
        ("Staff Welfare", 5),
    ],
    "INFRASTRUCTURE": [
        ("Government prioritized objectives", 25),
        ("MDA Operational Objectives", 20),
        ("Stakeholder Engagement", 5),
        ("Service Innovation and Improvement", 15),
        ("Automated Service Delivery", 15),
        ("Capacity Building & Talent Management", 5),
        ("Support for Service Delivery", 10),
        ("Staff Welfare", 5),
    ],
    "SECURITY": [
        ("Government prioritized objectives", 20),
        ("MDA Operational Objectives", 25),
        ("Stakeholder Engagement", 5),
        ("Service Innovation and Improvement", 10),
        ("Automated Service Delivery", 5),
        ("Capacity Building & Talent Management", 10),
        ("Support for Service Delivery", 20),
        ("Staff Welfare", 5),
    ],
    "GOVT_COMPANY": [
        ("Government prioritized objectives", 25),
        ("MDA Operational Objectives", 25),
        ("Stakeholder Engagement", 5),
        ("Service Innovation and Improvement", 10),
        ("Automated Service Delivery", 15),
        ("Capacity Building & Talent Management", 5),
        ("Support for Service Delivery", 10),
        ("Staff Welfare", 5),
    ],
}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PMSConfigService:
    """Service for OHCSF PMS first-time configuration and seed data."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def activate_ohcsf_pms(self, org_id: UUID) -> dict[str, int]:
        """
        Activate the OHCSF PMS for an organisation.

        Seeds competencies and institutional criteria templates if they have
        not already been created.  Safe to call multiple times — existing
        records are skipped.

        Returns:
            dict with keys ``competencies_created`` and ``templates_created``.
        """
        competencies_created = self._seed_competencies(org_id)
        templates_created = self._seed_criteria_templates(org_id)

        logger.info(
            "OHCSF PMS activated for org %s: %d competencies, %d templates seeded",
            org_id,
            competencies_created,
            templates_created,
        )
        return {
            "competencies_created": competencies_created,
            "templates_created": templates_created,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _seed_competencies(self, org_id: UUID) -> int:
        """
        Seed OHCSF competencies for the organisation.

        Checks existing competency codes before inserting to ensure
        idempotency.  Returns the number of newly created records.
        """
        # Import inside method to avoid circular imports
        from app.models.people.hr.job_description import Competency, CompetencyCategory

        # Fetch all existing codes for this org in one query
        existing_stmt = select(Competency.competency_code).where(
            Competency.organization_id == org_id,
            Competency.deleted_at.is_(None),
        )
        existing_codes: set[str] = set(self.db.scalars(existing_stmt).all())

        created = 0
        for _cluster_name, competencies in OHCSF_COMPETENCIES.items():
            for code, name in competencies:
                if code in existing_codes:
                    continue

                competency = Competency(
                    organization_id=org_id,
                    competency_code=code,
                    competency_name=name,
                    category=CompetencyCategory.CORE,
                    is_active=True,
                )
                self.db.add(competency)
                existing_codes.add(code)
                created += 1

        if created:
            self.db.flush()
            logger.info("Seeded %d OHCSF competencies for org %s", created, org_id)

        return created

    def _seed_criteria_templates(self, org_id: UUID) -> int:
        """
        Seed institutional criteria weight templates for the organisation.

        Checks existing (org_id, institution_type) pairs before inserting to
        ensure idempotency.  Returns the number of newly created records.
        """
        from app.models.people.perf.institutional_performance import (
            InstitutionalCriteriaTemplate,
        )
        from app.models.people.perf.pms_enums import InstitutionType

        # Fetch existing (institution_type) values already seeded for this org
        existing_stmt = select(InstitutionalCriteriaTemplate.institution_type).where(
            InstitutionalCriteriaTemplate.organization_id == org_id,
        )
        existing_types: set[str] = {
            str(t) for t in self.db.scalars(existing_stmt).all()
        }

        created = 0
        for inst_type_str, criteria in OHCSF_INSTITUTIONAL_WEIGHTS.items():
            if inst_type_str in existing_types:
                continue

            inst_type = InstitutionType(inst_type_str)
            for sequence, (criteria_name, weight) in enumerate(criteria, start=1):
                template = InstitutionalCriteriaTemplate(
                    organization_id=org_id,
                    institution_type=inst_type,
                    criteria_name=criteria_name,
                    default_weight=weight,
                    sequence=sequence,
                    is_active=True,
                )
                self.db.add(template)
                created += 1

            existing_types.add(inst_type_str)

        if created:
            self.db.flush()
            logger.info(
                "Seeded %d institutional criteria templates for org %s",
                created,
                org_id,
            )

        return created
