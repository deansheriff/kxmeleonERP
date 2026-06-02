"""Default attachment support for employee access invite emails."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain_settings import DomainSetting, SettingDomain, SettingScope
from app.models.domain_settings import SettingValueType
from app.services.storage import get_storage

DEFAULT_INVITE_ATTACHMENT_KEY = "hr_default_employee_invite_attachment"


def get_default_invite_attachment_metadata(
    db: Session,
    organization_id: uuid.UUID,
) -> dict[str, Any] | None:
    setting = db.scalar(
        select(DomainSetting).where(
            DomainSetting.domain == SettingDomain.settings,
            DomainSetting.key == DEFAULT_INVITE_ATTACHMENT_KEY,
            DomainSetting.organization_id == organization_id,
            DomainSetting.is_active.is_(True),
        )
    )
    metadata = setting.value_json if setting else None
    return metadata if isinstance(metadata, dict) else None


def set_default_invite_attachment_metadata(
    db: Session,
    organization_id: uuid.UUID,
    metadata: dict[str, Any],
) -> None:
    setting = db.scalar(
        select(DomainSetting).where(
            DomainSetting.domain == SettingDomain.settings,
            DomainSetting.key == DEFAULT_INVITE_ATTACHMENT_KEY,
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
                key=DEFAULT_INVITE_ATTACHMENT_KEY,
                organization_id=organization_id,
                scope=SettingScope.ORG_SPECIFIC,
                value_type=SettingValueType.json,
                value_json=metadata,
                is_active=True,
            )
        )
    db.flush()


def clear_default_invite_attachment_metadata(
    db: Session,
    organization_id: uuid.UUID,
) -> dict[str, Any] | None:
    setting = db.scalar(
        select(DomainSetting).where(
            DomainSetting.domain == SettingDomain.settings,
            DomainSetting.key == DEFAULT_INVITE_ATTACHMENT_KEY,
            DomainSetting.organization_id == organization_id,
            DomainSetting.is_active.is_(True),
        )
    )
    if not setting:
        return None
    previous = setting.value_json if isinstance(setting.value_json, dict) else None
    setting.is_active = False
    db.flush()
    return previous


def load_default_invite_attachment(
    db: Session,
    organization_id: uuid.UUID,
) -> tuple[str, bytes, str] | None:
    metadata = get_default_invite_attachment_metadata(db, organization_id)
    if not metadata:
        return None

    s3_key = str(metadata.get("s3_key") or "")
    filename = str(metadata.get("filename") or "")
    content_type = str(metadata.get("content_type") or "application/octet-stream")
    if not s3_key or not filename:
        return None

    return (filename, get_storage().download(s3_key), content_type)
