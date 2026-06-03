"""Configurable employee access invite email copy."""

from __future__ import annotations

import html
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain_settings import (
    DomainSetting,
    SettingDomain,
    SettingScope,
    SettingValueType,
)

EMPLOYEE_INVITE_EMAIL_TEMPLATE_KEY = "hr_employee_invite_email_template"
EMPLOYEE_INVITE_NEXT_URL = "/people/self/tax-info"
DEFAULT_EMPLOYEE_INVITE_SUBJECT = "Reset your password"
DEFAULT_EMPLOYEE_INVITE_BODY_HTML = (
    "<p>Hi {name},</p>"
    "<p>Use the link below to reset your password:</p>"
    '<p><a href="{reset_link}">Reset password</a></p>'
)
DEFAULT_EMPLOYEE_INVITE_BODY_TEXT = (
    "Hi {name}, use this link to reset your password: {reset_link}"
)


def default_employee_invite_email_template() -> dict[str, str]:
    return {
        "subject": DEFAULT_EMPLOYEE_INVITE_SUBJECT,
        "body_html": DEFAULT_EMPLOYEE_INVITE_BODY_HTML,
        "body_text": DEFAULT_EMPLOYEE_INVITE_BODY_TEXT,
    }


def _clean_template_text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def get_employee_invite_email_template(
    db: Session,
    organization_id: uuid.UUID,
) -> dict[str, str]:
    defaults = default_employee_invite_email_template()
    setting = db.scalar(
        select(DomainSetting).where(
            DomainSetting.domain == SettingDomain.settings,
            DomainSetting.key == EMPLOYEE_INVITE_EMAIL_TEMPLATE_KEY,
            DomainSetting.organization_id == organization_id,
            DomainSetting.is_active.is_(True),
        )
    )
    if not setting or not isinstance(setting.value_json, dict):
        return defaults

    return {
        "subject": _clean_template_text(
            setting.value_json.get("subject"),
            defaults["subject"],
        ),
        "body_html": _clean_template_text(
            setting.value_json.get("body_html"),
            defaults["body_html"],
        ),
        "body_text": _clean_template_text(
            setting.value_json.get("body_text"),
            defaults["body_text"],
        ),
    }


def set_employee_invite_email_template(
    db: Session,
    organization_id: uuid.UUID,
    *,
    subject: str,
    body_html: str,
    body_text: str,
) -> None:
    defaults = default_employee_invite_email_template()
    metadata = {
        "subject": _clean_template_text(subject, defaults["subject"]),
        "body_html": _clean_template_text(body_html, defaults["body_html"]),
        "body_text": _clean_template_text(body_text, defaults["body_text"]),
    }
    setting = db.scalar(
        select(DomainSetting).where(
            DomainSetting.domain == SettingDomain.settings,
            DomainSetting.key == EMPLOYEE_INVITE_EMAIL_TEMPLATE_KEY,
            DomainSetting.organization_id == organization_id,
        )
    )
    if setting:
        setting.value_type = SettingValueType.json
        setting.value_text = None
        setting.value_json = metadata
        setting.is_active = True
    else:
        db.add(
            DomainSetting(
                domain=SettingDomain.settings,
                key=EMPLOYEE_INVITE_EMAIL_TEMPLATE_KEY,
                organization_id=organization_id,
                scope=SettingScope.ORG_SPECIFIC,
                value_type=SettingValueType.json,
                value_json=metadata,
                is_active=True,
            )
        )
    db.flush()


def render_employee_invite_email_template(
    template: dict[str, str],
    *,
    name: str,
    reset_link: str,
) -> dict[str, str]:
    html_values = {
        "{name}": html.escape(name),
        "{reset_link}": html.escape(reset_link, quote=True),
    }
    text_values = {
        "{name}": name,
        "{reset_link}": reset_link,
    }
    rendered: dict[str, str] = {}
    for key, fallback in default_employee_invite_email_template().items():
        text = _clean_template_text(template.get(key), fallback)
        values = html_values if key == "body_html" else text_values
        for token, value in values.items():
            text = text.replace(token, value)
        rendered[key] = text
    return rendered
