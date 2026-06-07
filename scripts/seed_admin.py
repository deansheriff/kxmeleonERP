"""
Seed Admin User Script

Creates or repairs an admin user with full system permissions in one step:
1. Creates or updates the Person record
2. Creates or updates the local UserCredential
3. Seeds all permissions and roles
4. Assigns every permission to the admin role
5. Assigns the admin role to the user

Usage:
    python scripts/seed_admin.py

    python scripts/seed_admin.py --email admin@example.com \
      --first-name Admin --last-name User \
      --username admin --password secure-password
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from sqlalchemy import select

from app.db import SessionLocal
from app.models.auth import AuthProvider, UserCredential
from app.models.person import Person, PersonStatus
from app.models.rbac import Permission, PersonRole, Role, RolePermission
from app.services.auth_flow import hash_password
from scripts.seed_rbac import DEFAULT_PERMISSIONS, DEFAULT_ROLES

DEFAULT_ORGANIZATION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _env_value(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed or repair an admin user with full permissions."
    )
    parser.add_argument(
        "--email",
        default=_env_value(
            "BOOTSTRAP_ADMIN_EMAIL", "ADMIN_EMAIL", default="admin@example.com"
        ),
        help="Admin email address",
    )
    parser.add_argument(
        "--first-name",
        default=_env_value(
            "BOOTSTRAP_ADMIN_FIRST_NAME", "ADMIN_FIRST_NAME", default="Admin"
        ),
        help="First name",
    )
    parser.add_argument(
        "--last-name",
        default=_env_value(
            "BOOTSTRAP_ADMIN_LAST_NAME", "ADMIN_LAST_NAME", default="User"
        ),
        help="Last name",
    )
    parser.add_argument(
        "--username",
        default=_env_value(
            "BOOTSTRAP_ADMIN_USERNAME", "ADMIN_USERNAME", default="admin"
        ),
        help="Login username",
    )
    parser.add_argument(
        "--password",
        default=_env_value(
            "BOOTSTRAP_ADMIN_PASSWORD", "ADMIN_PASSWORD", default="admin123"
        ),
        help="Login password",
    )
    parser.add_argument(
        "--organization-id",
        default=_env_value(
            "BOOTSTRAP_ADMIN_ORGANIZATION_ID",
            "DEFAULT_ORGANIZATION_ID",
            default=str(DEFAULT_ORGANIZATION_ID),
        ),
        help="Organization UUID for the admin person",
    )
    parser.add_argument(
        "--force-reset",
        action="store_true",
        default=_env_bool("BOOTSTRAP_ADMIN_FORCE_RESET", False),
        help="Require password change on first login",
    )
    parser.add_argument(
        "--skip-rbac",
        action="store_true",
        help="Skip RBAC setup and only create or repair the user credential",
    )
    parser.add_argument(
        "--preserve-existing-password",
        action="store_true",
        default=_env_bool("BOOTSTRAP_ADMIN_PRESERVE_PASSWORD", False),
        help="Do not reset the password if the admin credential already exists",
    )
    return parser.parse_args(argv)


def ensure_permission(db, key: str, description: str) -> Permission:
    """Create or update a permission."""
    permission = db.scalar(select(Permission).where(Permission.key == key))
    if not permission:
        permission = Permission(key=key, description=description, is_active=True)
        db.add(permission)
    else:
        permission.description = description
        permission.is_active = True
    return permission


def ensure_role(db, name: str, description: str) -> Role:
    """Create or update a role."""
    role = db.scalar(select(Role).where(Role.name == name))
    if not role:
        role = Role(name=name, description=description, is_active=True)
        db.add(role)
    else:
        role.description = description
        role.is_active = True
    return role


def ensure_role_permission(db, role_id, permission_id):
    """Link a permission to a role."""
    link = db.scalar(
        select(RolePermission)
        .where(RolePermission.role_id == role_id)
        .where(RolePermission.permission_id == permission_id)
    )
    if not link:
        link = RolePermission(role_id=role_id, permission_id=permission_id)
        db.add(link)
    return link


def ensure_person_role(db, person_id, role_id):
    """Assign a role to a person."""
    link = db.scalar(
        select(PersonRole)
        .where(PersonRole.person_id == person_id)
        .where(PersonRole.role_id == role_id)
    )
    if not link:
        link = PersonRole(person_id=person_id, role_id=role_id)
        db.add(link)
    return link


def setup_rbac(db) -> Role:
    """Seed all permissions and roles, return the admin role."""
    print("Setting up RBAC...")

    for key, description in DEFAULT_PERMISSIONS:
        ensure_permission(db, key, description)
    db.flush()
    print(f"  Permissions: {len(DEFAULT_PERMISSIONS)}")

    for name, description in DEFAULT_ROLES:
        ensure_role(db, name, description)
    db.flush()
    print(f"  Roles: {len(DEFAULT_ROLES)}")

    admin_role = db.scalar(select(Role).where(Role.name == "admin"))
    all_permissions = db.scalars(select(Permission)).all()

    for permission in all_permissions:
        ensure_role_permission(db, admin_role.id, permission.id)
    db.flush()
    print(f"  Admin role: {len(all_permissions)} permissions")

    return admin_role


def main(
    argv: list[str] | None = None,
    session_factory=None,
) -> None:
    load_dotenv()
    args = parse_args(argv)
    organization_id = uuid.UUID(args.organization_id)
    db = (session_factory or SessionLocal)()

    try:
        # Prime the session with the target org so the multi-tenant listener
        # allows queries against org-scoped models (e.g. Person).
        db.info["organization_id"] = organization_id

        credential = db.scalar(
            select(UserCredential)
            .where(UserCredential.provider == AuthProvider.local)
            .where(UserCredential.username == args.username)
        )
        person = db.get(Person, credential.person_id) if credential else None
        if person is None:
            person = db.scalar(select(Person).where(Person.email == args.email))

        if not person:
            person = Person(
                organization_id=organization_id,
                first_name=args.first_name,
                last_name=args.last_name,
                email=args.email,
                email_verified=True,
                is_active=True,
                status=PersonStatus.active,
            )
            db.add(person)
            db.flush()
            print(f"Created person: {person.email}")
        else:
            person.organization_id = person.organization_id or organization_id
            person.first_name = args.first_name
            person.last_name = args.last_name
            person.email = args.email
            person.email_verified = True
            person.is_active = True
            person.status = PersonStatus.active
            print(f"Person ready: {person.email}")

        credential = db.scalar(
            select(UserCredential)
            .where(UserCredential.person_id == person.id)
            .where(UserCredential.provider == AuthProvider.local)
        )
        if not credential:
            credential = UserCredential(
                person_id=person.id,
                provider=AuthProvider.local,
                username=args.username,
                password_hash=hash_password(args.password),
                must_change_password=args.force_reset,
                password_updated_at=datetime.now(timezone.utc),
                failed_login_attempts=0,
                locked_until=None,
                is_active=True,
            )
            db.add(credential)
            db.flush()
            print(f"Created credential: {args.username}")
        else:
            credential.username = args.username
            if not args.preserve_existing_password:
                credential.password_hash = hash_password(args.password)
                credential.password_updated_at = datetime.now(timezone.utc)
                print(f"Reset password for credential: {args.username}")
            credential.must_change_password = args.force_reset
            credential.failed_login_attempts = 0
            credential.locked_until = None
            credential.is_active = True
            print(f"Credential ready: {credential.username}")

        if not args.skip_rbac:
            admin_role = setup_rbac(db)
            ensure_person_role(db, person.id, admin_role.id)
            print(f"Assigned admin role to: {person.email}")

        db.commit()
        print("\nAdmin user ready with full permissions")
        print(f"  Username: {args.username}")
        print(f"  Email: {args.email}")

    except Exception as exc:
        db.rollback()
        print(f"Error: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()