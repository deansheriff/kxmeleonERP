from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

import app.main as main_module


@pytest.mark.asyncio
async def test_lifespan_registers_payroll_handlers(monkeypatch):
    mock_db = MagicMock()

    monkeypatch.setattr(main_module, "SessionLocal", lambda: mock_db)
    monkeypatch.setattr(main_module, "validate_startup", lambda db, **_: True)
    monkeypatch.setattr(main_module, "seed_all_settings", lambda db: None)

    with patch(
        "app.services.people.payroll.event_handlers.register_payroll_handlers"
    ) as mock_register:
        async with main_module.lifespan(main_module.app):
            pass

    mock_register.assert_called_once_with()
    mock_db.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_lifespan_seeds_settings_with_cross_org_context(monkeypatch):
    mock_db = MagicMock()
    events = []

    @contextmanager
    def fake_allow_cross_org(db):
        events.append(("enter", db))
        yield
        events.append(("exit", db))

    def fake_seed_all_settings(db):
        events.append(("seed", db))

    monkeypatch.setattr(main_module, "SessionLocal", lambda: mock_db)
    monkeypatch.setattr(main_module, "validate_startup", lambda db, **_: True)
    monkeypatch.setattr(main_module, "allow_cross_org", fake_allow_cross_org)
    monkeypatch.setattr(main_module, "seed_all_settings", fake_seed_all_settings)
    monkeypatch.setattr(main_module, "_get_cached_openapi_schema", lambda: {})

    with patch("app.services.people.payroll.event_handlers.register_payroll_handlers"):
        async with main_module.lifespan(main_module.app):
            pass

    assert events == [
        ("enter", mock_db),
        ("seed", mock_db),
        ("exit", mock_db),
    ]
