from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.templates import templates


def test_department_detail_renders_employee_table_rows() -> None:
    employee = SimpleNamespace(
        employee_id=uuid4(),
        employee_code="EMP-001",
        full_name="Ada Lovelace",
        person=SimpleNamespace(email="ada@example.com"),
        designation=SimpleNamespace(designation_name="Engineer"),
        employment_type=SimpleNamespace(type_name="Full Time"),
        date_of_joining=date(2026, 1, 2),
        status=SimpleNamespace(value="ACTIVE"),
    )
    department = SimpleNamespace(
        department_id=uuid4(),
        department_name="Engineering",
        department_code="ENG",
        description="",
        is_active=True,
        head=None,
    )
    headcount = SimpleNamespace(
        total_employees=1,
        active_employees=1,
        on_leave=0,
        terminated=0,
    )

    html = templates.env.get_template("people/hr/department_detail.html").render(
        request=SimpleNamespace(state=SimpleNamespace()),
        department=department,
        headcount=headcount,
        employees=[employee],
        page=1,
        total_pages=1,
        total=1,
        has_prev=False,
        has_next=False,
        active_module="departments",
        accessible_modules=["people"],
        user=SimpleNamespace(),
        current_user=SimpleNamespace(),
        organization=SimpleNamespace(),
        performance_private_enabled=False,
        performance_government_enabled=False,
    )

    assert "Employee" in html
    assert "Ada Lovelace" in html
    assert "EMP-001" in html
    assert "Engineer" in html
    assert "Full Time" in html
