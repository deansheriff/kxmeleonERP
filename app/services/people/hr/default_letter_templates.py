"""
Default HR Letter Templates.

Professional Nigerian business letter templates with Jinja2 placeholders.
Used by ``seed_hr_letter_templates()`` and ``HRLetterService._ensure_default_templates()``
to create initial ``DocumentTemplate`` records.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance.automation.document_template import (
    DocumentTemplate,
    TemplateType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template display names
# ---------------------------------------------------------------------------


def _template_display_name(tt: TemplateType) -> str:
    return f"Default {tt.value.replace('_', ' ').title()}"


# ---------------------------------------------------------------------------
# Shared letter wrapper — keeps individual bodies DRY
# ---------------------------------------------------------------------------

_LETTER_HEAD = """\
<div style="text-align:center; margin-bottom:24px;">
  <h2 style="margin:0;">{{ organization_name }}</h2>
  {% if organization_address %}<p style="margin:4px 0; font-size:13px;">{{ organization_address }}</p>{% endif %}
</div>
<hr style="border:none; border-top:2px solid #0d9488; margin-bottom:24px;">
<p style="text-align:right; font-size:13px;">Date: {{ letter_date | format_date }}</p>
"""

_EMPLOYEE_ADDRESS = """\
<p>
  <strong>{{ employee_name }}</strong><br>
  Employee Code: {{ employee_code }}<br>
  {% if department_name %}Department: {{ department_name }}<br>{% endif %}
  {% if employee_address %}{{ employee_address }}{% endif %}
</p>
"""

_SIGNATURE_BLOCK = """\
<div style="margin-top:48px;">
  <p>Yours faithfully,</p>
  <br><br>
  <p>
    <strong>{{ signatory_name }}</strong><br>
    {{ signatory_title }}
  </p>
</div>
"""

# ---------------------------------------------------------------------------
# Individual letter bodies
# ---------------------------------------------------------------------------

_CONFIRMATION_BODY = """\
<p><strong>Subject: Confirmation of Appointment</strong></p>

<p>Dear {{ employee_name }},</p>

<p>
  We are pleased to confirm your appointment with <strong>{{ organization_name }}</strong>
  following the successful completion of your probation period, which ended on
  {{ probation_end_date | format_date }}.
</p>

<p>Your confirmation is effective from <strong>{{ confirmation_date | format_date }}</strong>.</p>

{% if new_salary %}
<p>
  In line with this confirmation, your revised annual compensation is
  <strong>{{ new_salary | format_currency }}</strong>, effective
  {{ salary_effective_date | format_date }}.
</p>
{% endif %}

<p>
  We appreciate your commitment and look forward to your continued contributions
  to the organisation.
</p>

<p>
  Please sign and return a copy of this letter as acknowledgement.
</p>
"""

_PROMOTION_BODY = """\
<p><strong>Subject: Promotion Letter</strong></p>

<p>Dear {{ employee_name }},</p>

<p>
  We are delighted to inform you that, in recognition of your outstanding performance
  and dedication, you have been promoted from <strong>{{ previous_job_title }}</strong>
  to <strong>{{ new_job_title }}</strong>, effective {{ effective_date | format_date }}.
</p>

{% if new_department %}
<p>You will be reporting to the <strong>{{ new_department }}</strong> department.</p>
{% endif %}

<p>
  Your revised annual compensation is <strong>{{ new_salary | format_currency }}</strong>,
  an increment of {{ salary_increment | format_currency }}
  ({{ salary_increment_percentage }}%).
</p>

{% if promotion_reason %}
<p>Reason: {{ promotion_reason }}</p>
{% endif %}

<p>
  We are confident you will continue to excel in your new role and wish you
  continued success.
</p>

<p>
  Please sign and return a copy of this letter as acknowledgement.
</p>
"""

_TRANSFER_BODY = """\
<p><strong>Subject: Transfer Letter</strong></p>

<p>Dear {{ employee_name }},</p>

<p>
  This is to inform you that you are being transferred from your current role as
  <strong>{{ current_job_title }}</strong>
  {% if current_department %}in the {{ current_department }} department{% endif %}
  to the position of <strong>{{ new_job_title }}</strong>
  {% if new_department %}in the {{ new_department }} department{% endif %},
  effective {{ effective_date | format_date }}.
</p>

{% if new_location %}
<p>Your new work location will be <strong>{{ new_location }}</strong>.</p>
{% endif %}

{% if new_reporting_to %}
<p>You will report to <strong>{{ new_reporting_to }}</strong>.</p>
{% endif %}

{% if transfer_reason %}
<p>Reason for transfer: {{ transfer_reason }}</p>
{% endif %}

<p>
  All other terms and conditions of your employment remain unchanged.
  We wish you all the best in your new role.
</p>
"""

_TERMINATION_BODY = """\
<p><strong>Subject: Termination of Employment</strong></p>

<p>Dear {{ employee_name }},</p>

<p>
  We regret to inform you that your employment with <strong>{{ organization_name }}</strong>
  as <strong>{{ job_title }}</strong> is hereby terminated, effective
  {{ termination_date | format_date }}.
</p>

<p>Reason: {{ termination_reason }}</p>

<p>Your last working day will be <strong>{{ last_working_date | format_date }}</strong>.</p>

{% if notice_period_served %}
<p>You have duly served the required notice period of {{ notice_period_days }} days.</p>
{% else %}
<p>
  Payment in lieu of the {{ notice_period_days }}-day notice period
  {% if payment_in_lieu_of_notice %}of {{ payment_in_lieu_of_notice | format_currency }}{% endif %}
  will be included in your final settlement.
</p>
{% endif %}

{% if total_settlement %}
<p>
  Your total settlement amount is <strong>{{ total_settlement | format_currency }}</strong>.
  Details will be communicated separately.
</p>
{% endif %}

<p>
  Please ensure all company property is returned and the exit process is completed
  before your last working day.
</p>

<p>We wish you the very best in your future endeavours.</p>
"""

_SALARY_REVISION_BODY = """\
<p><strong>Subject: Salary Revision</strong></p>

<p>Dear {{ employee_name }},</p>

<p>
  We are pleased to inform you that your compensation has been revised with effect
  from <strong>{{ effective_date | format_date }}</strong>.
</p>

<table style="border-collapse:collapse; margin:16px 0; width:100%;">
  <tr>
    <td style="padding:8px; border:1px solid #e2e8f0;">Current Annual Salary</td>
    <td style="padding:8px; border:1px solid #e2e8f0; text-align:right; font-family:monospace;">
      {{ current_salary | format_currency }}
    </td>
  </tr>
  <tr>
    <td style="padding:8px; border:1px solid #e2e8f0;">Revised Annual Salary</td>
    <td style="padding:8px; border:1px solid #e2e8f0; text-align:right; font-family:monospace;">
      {{ new_salary | format_currency }}
    </td>
  </tr>
  <tr>
    <td style="padding:8px; border:1px solid #e2e8f0;">Increment</td>
    <td style="padding:8px; border:1px solid #e2e8f0; text-align:right; font-family:monospace;">
      {{ increment_amount | format_currency }} ({{ increment_percentage }}%)
    </td>
  </tr>
</table>

<p>Reason: {{ revision_reason }}</p>

<p>
  All other terms and conditions of your employment remain unchanged.
  Please sign and return a copy of this letter as acknowledgement.
</p>
"""

_EXPERIENCE_BODY = """\
<p style="text-align:center;"><strong>TO WHOM IT MAY CONCERN</strong></p>

<p><strong>Subject: Experience / Service Certificate</strong></p>

<p>
  This is to certify that <strong>{{ employee_name }}</strong> (Employee Code: {{ employee_code }})
  was employed with <strong>{{ organization_name }}</strong>
  {% if organization_legal_name and organization_legal_name != organization_name %}
    ({{ organization_legal_name }})
  {% endif %}
  from {{ date_of_joining | format_date }} to {{ date_of_leaving | format_date }}.
</p>

<p>
  During this period, {{ employee_name }} held the position of
  <strong>{{ job_title }}</strong>
  {% if department_name %}in the {{ department_name }} department{% endif %}.
</p>

{% if role_summary %}
<p>Role summary: {{ role_summary }}</p>
{% endif %}

{% if achievements %}
<p>Key achievements:</p>
<ul>
  {% for item in achievements %}
  <li>{{ item }}</li>
  {% endfor %}
</ul>
{% endif %}

{% if conduct_rating %}
<p>
  {{ employee_name }}'s conduct and performance during employment were
  rated as <strong>{{ conduct_rating }}</strong>.
</p>
{% endif %}

<p>
  We wish {{ employee_name }} all the best in future endeavours.
</p>
"""

_RELIEVING_BODY = """\
<p><strong>Subject: Relieving Letter</strong></p>

<p>Dear {{ employee_name }},</p>

<p>
  This is to confirm that you have been relieved of your duties at
  <strong>{{ organization_name }}</strong>
  {% if organization_legal_name and organization_legal_name != organization_name %}
    ({{ organization_legal_name }})
  {% endif %}
  as of <strong>{{ last_working_day | format_date }}</strong>.
</p>

<p>
  You were employed as <strong>{{ job_title }}</strong>
  {% if department_name %}in the {{ department_name }} department{% endif %}
  from {{ date_of_joining | format_date }} to {{ last_working_day | format_date }}.
</p>

{% if clearance_completed %}
<p>We confirm that you have completed all clearance formalities.</p>
{% else %}
<p>Please ensure all clearance formalities are completed at the earliest.</p>
{% endif %}

{% if final_settlement_completed %}
<p>Your final settlement has been processed.</p>
{% else %}
<p>Your final settlement will be processed and communicated separately.</p>
{% endif %}

<p>
  We thank you for your contributions to the organisation and wish you all the
  best in your future career.
</p>
"""

_APPOINTMENT_BODY = """\
<p><strong>Subject: Letter of Appointment</strong></p>

<p>Dear {{ employee_name }},</p>

<p>
  Further to your acceptance of our offer, we are pleased to formally appoint you
  to the position of <strong>{{ job_title }}</strong>
  {% if department_name %}in the {{ department_name }} department{% endif %}
  at <strong>{{ organization_name }}</strong>.
</p>

<p>Your appointment is effective from <strong>{{ start_date | format_date }}</strong>.</p>

<p>
  Your annual compensation will be <strong>{{ base_salary | format_currency }}</strong>,
  payable {{ pay_frequency | lower }}.
</p>

{% if probation_months %}
<p>
  You will undergo a probation period of {{ probation_months }} months commencing
  from your date of joining.
</p>
{% endif %}

{% if reporting_to %}
<p>You will report to <strong>{{ reporting_to }}</strong>.</p>
{% endif %}

{% if work_days %}
<p>Working days: {{ work_days }}.</p>
{% endif %}

<p>
  Please sign and return a copy of this letter as acceptance of the terms herein.
</p>
"""

_RESIGNATION_ACCEPTANCE_BODY = """\
<p><strong>Subject: Acceptance of Resignation</strong></p>

<p>Dear {{ employee_name }},</p>

<p>
  We acknowledge receipt of your resignation letter dated
  {{ resignation_date | format_date }} from your position as
  <strong>{{ job_title }}</strong>
  {% if department_name %}in the {{ department_name }} department{% endif %}.
</p>

<p>
  Your resignation has been accepted and your last working day will be
  <strong>{{ last_working_day | format_date }}</strong>,
  in accordance with the {{ notice_period_days }}-day notice period.
</p>

{% if handover_instructions %}
<p>Handover instructions: {{ handover_instructions }}</p>
{% endif %}

{% if exit_interview_date %}
<p>
  An exit interview has been scheduled for {{ exit_interview_date | format_date }}.
  Please confirm your availability.
</p>
{% endif %}

{% if accrued_leave_days %}
<p>
  You have {{ accrued_leave_days }} accrued leave day(s)
  {% if leave_encashment_amount %}
    which will be encashed at {{ leave_encashment_amount | format_currency }}
  {% endif %}
  as part of your final settlement.
</p>
{% endif %}

<p>
  Please ensure all company property is returned and all pending tasks are handed
  over before your last working day.
</p>

<p>
  We thank you for your service and wish you every success in your future career.
</p>
"""

_BONUS_BODY = """\
<p><strong>Subject: Bonus Letter</strong></p>

<p>Dear {{ employee_name }},</p>

<p>
  We are pleased to inform you that, in recognition of your contributions,
  you have been awarded a bonus of
  <strong>{{ bonus_amount | format_currency }}</strong>.
</p>

<p>Reason: {{ bonus_reason }}</p>

{% if bonus_period %}
<p>Period: {{ bonus_period }}</p>
{% endif %}

{% if payment_date %}
<p>
  The bonus will be credited to your account on or before
  {{ payment_date | format_date }}.
</p>
{% endif %}

<p>
  We appreciate your hard work and dedication and look forward to your
  continued excellence.
</p>
"""

# ---------------------------------------------------------------------------
# Assembled full-letter templates
# ---------------------------------------------------------------------------


def _assemble(body: str) -> str:
    """Wrap a letter body with standard letterhead, address, and signature."""
    return f"{_LETTER_HEAD}\n{_EMPLOYEE_ADDRESS}\n{body}\n{_SIGNATURE_BLOCK}"


DEFAULT_LETTER_TEMPLATES: dict[TemplateType, str] = {
    TemplateType.CONFIRMATION_LETTER: _assemble(_CONFIRMATION_BODY),
    TemplateType.PROMOTION_LETTER: _assemble(_PROMOTION_BODY),
    TemplateType.TRANSFER_LETTER: _assemble(_TRANSFER_BODY),
    TemplateType.TERMINATION_LETTER: _assemble(_TERMINATION_BODY),
    TemplateType.SALARY_REVISION_LETTER: _assemble(_SALARY_REVISION_BODY),
    TemplateType.EXPERIENCE_LETTER: _assemble(_EXPERIENCE_BODY),
    TemplateType.RELIEVING_LETTER: _assemble(_RELIEVING_BODY),
    TemplateType.APPOINTMENT_LETTER: _assemble(_APPOINTMENT_BODY),
    TemplateType.RESIGNATION_ACCEPTANCE: _assemble(_RESIGNATION_ACCEPTANCE_BODY),
    TemplateType.BONUS_LETTER: _assemble(_BONUS_BODY),
}


# ---------------------------------------------------------------------------
# Seed function
# ---------------------------------------------------------------------------


def seed_hr_letter_templates(
    db: Session,
    org_id: UUID,
    created_by: UUID,
) -> dict[str, int]:
    """
    Create default ``DocumentTemplate`` records for HR letter types
    that do not already have a template for the given organisation.

    Returns:
        Dict with ``{"created": N, "skipped": N}``.
    """
    results: dict[str, int] = {"created": 0, "skipped": 0}

    for tt, content in DEFAULT_LETTER_TEMPLATES.items():
        # Check for existing template of this type
        existing = db.scalar(
            select(DocumentTemplate).where(
                DocumentTemplate.organization_id == org_id,
                DocumentTemplate.template_type == tt,
                DocumentTemplate.is_active == True,  # noqa: E712
            )
        )
        if existing:
            results["skipped"] += 1
            continue

        template = DocumentTemplate(
            organization_id=org_id,
            template_type=tt,
            template_name=_template_display_name(tt),
            description=f"System default {tt.value.replace('_', ' ').lower()} template",
            template_content=content,
            page_size="A4",
            page_orientation="portrait",
            is_default=True,
            is_active=True,
            version=1,
            created_by=created_by,
        )
        db.add(template)
        results["created"] += 1

    db.flush()
    logger.info(
        "Seeded HR letter templates for org %s: %d created, %d skipped",
        org_id,
        results["created"],
        results["skipped"],
    )
    return results
