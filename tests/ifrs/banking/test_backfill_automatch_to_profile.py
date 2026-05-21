"""Tests for the DomainSettings → ReconciliationPolicyProfile backfill migration.

Only the value-parser is unit-testable in isolation.  The full upgrade()
runs against a live PG instance via Alembic and is exercised by
integration tests at deploy time.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "20260515_backfill_automatch_to_profile.py"
)


def _load_migration_module():
    if "alembic" not in sys.modules or not hasattr(sys.modules["alembic"], "op"):
        alembic_stub = types.ModuleType("alembic")
        alembic_stub.op = types.SimpleNamespace()
        sys.modules["alembic"] = alembic_stub

    spec = importlib.util.spec_from_file_location("backfill_automatch", _MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migration():
    return _load_migration_module()


class TestParseSettingValue:
    """``_parse_setting_value`` mirrors settings_spec.coerce_value semantics."""

    def test_boolean_from_true_string(self, migration) -> None:
        parsed = migration._parse_setting_value(
            "automatch_pass_bank_fees_enabled",
            "boolean",
            "true",
            None,
        )
        assert parsed is True

    def test_boolean_from_false_string(self, migration) -> None:
        parsed = migration._parse_setting_value(
            "automatch_pass_bank_fees_enabled",
            "boolean",
            "false",
            None,
        )
        assert parsed is False

    def test_boolean_from_aliases(self, migration) -> None:
        for value in ("1", "yes", "ON"):
            assert (
                migration._parse_setting_value(
                    "automatch_pass_bank_fees_enabled", "boolean", value, None
                )
                is True
            )
        for value in ("0", "no", "OFF"):
            assert (
                migration._parse_setting_value(
                    "automatch_pass_bank_fees_enabled", "boolean", value, None
                )
                is False
            )

    def test_boolean_from_json_bool(self, migration) -> None:
        parsed = migration._parse_setting_value(
            "automatch_pass_bank_fees_enabled",
            "boolean",
            None,
            True,
        )
        assert parsed is True

    def test_boolean_invalid_string_returns_none(self, migration) -> None:
        assert (
            migration._parse_setting_value(
                "automatch_pass_bank_fees_enabled", "boolean", "maybe", None
            )
            is None
        )

    def test_integer_from_string(self, migration) -> None:
        parsed = migration._parse_setting_value(
            "automatch_date_buffer_days",
            "integer",
            "14",
            None,
        )
        assert parsed == 14

    def test_integer_with_whitespace(self, migration) -> None:
        parsed = migration._parse_setting_value(
            "automatch_amount_tolerance_cents",
            "integer",
            "  3  ",
            None,
        )
        assert parsed == 3

    def test_integer_invalid_returns_none(self, migration) -> None:
        assert (
            migration._parse_setting_value(
                "automatch_date_buffer_days", "integer", "not-a-number", None
            )
            is None
        )

    def test_integer_rejects_bool_disguised_as_int(self, migration) -> None:
        # In Python ``True`` is an int subclass.  We must not let a bool
        # value sneak into an integer column — the spec's coerce_value would
        # also reject this.
        parsed = migration._parse_setting_value(
            "automatch_date_buffer_days", "integer", None, True
        )
        assert parsed is None

    def test_string_passes_through(self, migration) -> None:
        parsed = migration._parse_setting_value(
            "automatch_finance_cost_account_code",
            "string",
            "7200",
            None,
        )
        assert parsed == "7200"

    def test_string_strips_whitespace(self, migration) -> None:
        parsed = migration._parse_setting_value(
            "automatch_finance_cost_account_code",
            "string",
            "  6080  ",
            None,
        )
        assert parsed == "6080"

    def test_string_empty_returns_none(self, migration) -> None:
        # Empty/whitespace-only string would have no effect on the profile —
        # treat as "no value to backfill".
        assert (
            migration._parse_setting_value(
                "automatch_finance_cost_account_code", "string", "   ", None
            )
            is None
        )

    def test_both_value_columns_null_returns_none(self, migration) -> None:
        assert (
            migration._parse_setting_value(
                "automatch_finance_cost_account_code", "string", None, None
            )
            is None
        )


class TestKeyMapping:
    """All 11 banking.automatch_* keys map to a real profile column."""

    def test_every_key_maps_to_a_column(self, migration) -> None:
        # The 11 keys we expect — pulled from settings_spec.py at the time
        # the model was extended.  If a new automatch_* key is added in the
        # future, this test fails to remind us to add it to _KEY_TO_COLUMN.
        expected_keys = {
            "automatch_pass_payment_intents_enabled",
            "automatch_pass_splynx_by_ref_enabled",
            "automatch_pass_splynx_date_amount_enabled",
            "automatch_pass_ap_payments_enabled",
            "automatch_pass_ar_payments_enabled",
            "automatch_pass_bank_fees_enabled",
            "automatch_pass_settlements_enabled",
            "automatch_amount_tolerance_cents",
            "automatch_date_buffer_days",
            "automatch_settlement_date_window_days",
            "automatch_finance_cost_account_code",
        }
        assert set(migration._KEY_TO_COLUMN.keys()) == expected_keys

    def test_boolean_and_integer_keys_are_disjoint(self, migration) -> None:
        assert not (migration._BOOLEAN_KEYS & migration._INTEGER_KEYS)

    def test_typed_keys_are_subset_of_mapping(self, migration) -> None:
        all_typed = migration._BOOLEAN_KEYS | migration._INTEGER_KEYS
        assert all_typed.issubset(set(migration._KEY_TO_COLUMN.keys()))
