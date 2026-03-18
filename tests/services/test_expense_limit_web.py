from starlette.datastructures import FormData

from app.services.expense.limit_web import ExpenseLimitWebService


def test_get_approver_scope_id_prefers_employee_scope_id():
    form = FormData(
        [
            ("scope_type", "EMPLOYEE"),
            ("scope_id", "employee-uuid"),
            ("scope_id", ""),
        ]
    )

    scope_id = ExpenseLimitWebService._get_approver_scope_id(form, "EMPLOYEE")

    assert scope_id == "employee-uuid"


def test_get_approver_scope_id_uses_scope_option_id_for_non_employee():
    form = FormData(
        [
            ("scope_type", "GRADE"),
            ("scope_id", ""),
            ("scope_option_id", "grade-uuid"),
        ]
    )

    scope_id = ExpenseLimitWebService._get_approver_scope_id(form, "GRADE")

    assert scope_id == "grade-uuid"
