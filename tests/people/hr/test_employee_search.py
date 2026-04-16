from __future__ import annotations

import uuid
from datetime import date

from app.models.people.hr.employee import Employee, EmployeeStatus
from app.models.person import Person
from app.services.common import PaginationParams
from app.services.people.hr.employee_types import EmployeeFilters
from app.services.people.hr.employees import EmployeeService


def _ensure_employee_table(engine) -> None:
    for column in Employee.__table__.columns:
        default = column.server_default
        if default is None:
            continue
        default_text = str(getattr(default, "arg", default)).lower()
        if "gen_random_uuid" in default_text or "uuid_generate" in default_text:
            column.server_default = None
    Employee.__table__.create(engine, checkfirst=True)


def _add_employee(
    db_session,
    *,
    organization_id: uuid.UUID,
    first_name: str,
    last_name: str,
    display_name: str | None = None,
) -> Employee:
    person = Person(
        id=uuid.uuid4(),
        organization_id=organization_id,
        first_name=first_name,
        last_name=last_name,
        display_name=display_name,
        email=f"{uuid.uuid4().hex}@example.com",
    )
    employee = Employee(
        employee_id=uuid.uuid4(),
        organization_id=organization_id,
        person_id=person.id,
        employee_code=f"EMP-{uuid.uuid4().hex[:8]}",
        date_of_joining=date(2026, 1, 1),
        status=EmployeeStatus.DRAFT,
    )
    db_session.add_all([person, employee])
    db_session.flush()
    return employee


def test_list_employees_search_matches_full_name(db_session):
    _ensure_employee_table(db_session.bind)
    org_id = uuid.uuid4()
    employee = _add_employee(
        db_session,
        organization_id=org_id,
        first_name="Aisha",
        last_name="Ibrahim",
    )
    _add_employee(
        db_session,
        organization_id=org_id,
        first_name="Aisha",
        last_name="Musa",
    )

    service = EmployeeService(db_session, org_id)
    result = service.list_employees(
        EmployeeFilters(search="Aisha Ibrahim"),
        PaginationParams(limit=10),
    )

    assert [item.employee_id for item in result.items] == [employee.employee_id]


def test_search_employees_autocomplete_matches_full_name(db_session):
    _ensure_employee_table(db_session.bind)
    org_id = uuid.uuid4()
    employee = _add_employee(
        db_session,
        organization_id=org_id,
        first_name="Aisha",
        last_name="Ibrahim",
    )

    service = EmployeeService(db_session, org_id)
    results = service.search_employees("Aisha Ibrahim")

    assert [item.id for item in results] == [employee.employee_id]


def test_list_employees_search_matches_display_name(db_session):
    _ensure_employee_table(db_session.bind)
    org_id = uuid.uuid4()
    employee = _add_employee(
        db_session,
        organization_id=org_id,
        first_name="Ibrahim",
        last_name="A.",
        display_name="Aisha Ibrahim",
    )

    service = EmployeeService(db_session, org_id)
    result = service.list_employees(
        EmployeeFilters(search="Aisha Ibrahim"),
        PaginationParams(limit=10),
    )

    assert [item.employee_id for item in result.items] == [employee.employee_id]
