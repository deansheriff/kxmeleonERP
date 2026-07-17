"""Static regression tests for high-risk authorization boundaries."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _employee_permissions() -> set[str]:
    tree = ast.parse(_source("scripts/seed_rbac.py"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "ROLE_PERMISSIONS"
            for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Dict):
            break
        for key, value in zip(node.value.keys, node.value.values):
            if isinstance(key, ast.Constant) and key.value == "employee":
                assert isinstance(value, ast.List)
                return {
                    item.value
                    for item in value.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                }
    raise AssertionError("employee role permission mapping not found")


def _employee_runtime_scopes() -> set[str]:
    tree = ast.parse(_source("app/web/deps.py"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name)
            and target.id == "_EMPLOYEE_SELF_SERVICE_SCOPES"
            for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Call) or not node.value.args:
            break
        values = node.value.args[0]
        if not isinstance(values, ast.Set):
            break
        return {
            item.value
            for item in values.elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        }
    raise AssertionError("employee runtime scope baseline not found")


def _role_permissions(role_name: str) -> set[str]:
    tree = ast.parse(_source("scripts/seed_rbac.py"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "ROLE_PERMISSIONS"
            for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Dict):
            break
        for key, value in zip(node.value.keys, node.value.values):
            if isinstance(key, ast.Constant) and key.value == role_name:
                assert isinstance(value, ast.List)
                return {
                    item.value
                    for item in value.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                }
    raise AssertionError(f"{role_name} role permission mapping not found")


class EmployeeRoleBoundaryTests(unittest.TestCase):
    def test_employee_role_is_self_service_only(self) -> None:
        permissions = _employee_permissions()
        self.assertIn("self:access", permissions)
        self.assertNotIn("hr:access", permissions)
        self.assertNotIn("expense:access", permissions)
        self.assertNotIn("projects:access", permissions)
        self.assertNotIn("support:access", permissions)

    def test_startup_seed_reconciles_employee_role_exactly(self) -> None:
        source = _source("scripts/seed_admin.py")
        self.assertIn('ROLE_PERMISSIONS["employee"]', source)
        self.assertIn("RolePermission.permission_id.notin_", source)
        self.assertNotIn("legacy_employee_grants", source)

    def test_runtime_employee_scope_baseline_matches_seed(self) -> None:
        self.assertEqual(_employee_permissions(), _employee_runtime_scopes())

    def test_tighter_routes_keep_expected_manager_access(self) -> None:
        operations_permissions = _role_permissions("operations_manager")
        finance_permissions = _role_permissions("finance_manager")
        self.assertIn("inventory:items:read", operations_permissions)
        self.assertIn("inventory:transactions:adjust", operations_permissions)
        self.assertIn("gl:balances:read", finance_permissions)


class RouteBoundaryTests(unittest.TestCase):
    def assert_guard(self, path: str, function: str, guard: str) -> None:
        source = _source(path)
        start = source.index(f"def {function}(")
        end = source.find("\n\ndef ", start + 1)
        async_end = source.find("\n\nasync def ", start + 1)
        candidates = [value for value in (end, async_end) if value != -1]
        block = source[start : min(candidates) if candidates else len(source)]
        self.assertIn(f"Depends({guard})", block)

    def test_employee_management_routes_are_granular(self) -> None:
        source = _source("app/web/people/hr/employees.py")
        self.assertNotIn("require_hr_access", source)
        self.assert_guard(
            "app/web/people/hr/employees.py", "create_employee", "_employee_create"
        )
        self.assert_guard(
            "app/web/people/hr/employees.py",
            "resend_employee_invite",
            "_employee_credentials",
        )

    def test_broad_hr_gate_ignores_employee_role_grants(self) -> None:
        source = _source("app/web/deps.py")
        self.assertIn("def _has_non_employee_hr_access", source)
        self.assertIn('Role.name != "employee"', source)
        self.assertIn("not has_valid_hr_role", source)

    def test_employee_only_sessions_are_restricted_on_every_request(self) -> None:
        source = _source("app/web/deps.py")
        self.assertIn("def _restrict_employee_only_scopes", source)
        self.assertIn('normalized_roles != {"employee"}', source)
        self.assertIn(
            "scopes = _restrict_employee_only_scopes(roles, scopes)", source
        )

    def test_support_and_project_routes_do_not_use_module_wide_guards(self) -> None:
        self.assertNotIn("require_support_access", _source("app/web/support.py"))
        self.assertNotIn("require_projects_access", _source("app/web/projects.py"))

    def test_financial_workflow_actions_have_specific_guards(self) -> None:
        self.assert_guard("app/web/finance/gl.py", "post_journal", "_journals_post")
        self.assert_guard(
            "app/web/finance/ar.py", "approve_invoice", "_invoices_post"
        )
        self.assert_guard(
            "app/web/finance/banking.py",
            "reconciliation_approve",
            "_reconciliation_approve",
        )

    def test_finance_read_routes_do_not_use_module_wide_guards(self) -> None:
        for path in (
            "app/web/finance/gl.py",
            "app/web/finance/ar.py",
            "app/web/finance/banking.py",
        ):
            self.assertNotIn("require_finance_access", _source(path))

    def test_expense_records_apply_employee_scope(self) -> None:
        routes = _source("app/web/finance/exp.py")
        claims = _source("app/services/expense/web_claims.py")
        advances = _source("app/services/expense/web_advances.py")
        self.assertNotIn("require_expense_access", routes)
        self.assertIn("readable_employee_ids(", claims)
        self.assertIn("_can_read_claim", claims)
        self.assertIn("_owned_claim", claims)
        self.assertIn("can_read_employee_record(", advances)

    def test_inventory_and_fixed_asset_mutations_are_granular(self) -> None:
        self.assert_guard(
            "app/web/inventory.py",
            "create_transfer_transaction",
            "_transactions_transfer",
        )
        self.assert_guard(
            "app/web/fixed_assets.py", "dispose_asset", "_fa_assets_dispose"
        )
        self.assert_guard(
            "app/web/fixed_assets.py",
            "post_depreciation_run",
            "_fa_depreciation_post",
        )

    def test_inventory_and_fixed_asset_reads_are_granular(self) -> None:
        self.assert_guard("app/web/inventory.py", "list_items", "_items_read")
        self.assert_guard(
            "app/web/inventory.py",
            "inventory_valuation_report",
            "_valuation_read",
        )
        self.assertNotIn(
            "require_fixed_assets_access", _source("app/web/fixed_assets.py")
        )


if __name__ == "__main__":
    unittest.main()
