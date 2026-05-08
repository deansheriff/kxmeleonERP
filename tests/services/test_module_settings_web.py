"""Tests for module settings web helpers."""

from app.models.domain_settings import SettingDomain
from app.services.module_settings_web import ModuleSettingsWebService


class TestModuleSettingsWebService:
    """Tests for module settings key/domain resolution."""

    def test_fa_settings_keys_use_automation_domain(self) -> None:
        """Fixed-assets module settings should persist to automation settings."""
        domain = ModuleSettingsWebService._domain_for_key(
            "fa_depreciation_auto_run_enabled"
        )

        assert domain == SettingDomain.automation
