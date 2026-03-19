from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from fastapi.responses import StreamingResponse

from app.models.people.payroll.payroll_entry import PayrollEntryStatus
from app.services.people.payroll.paye_export import PAYEExportResult
from app.services.people.payroll.web.run_web import RunWebService


def _make_auth(org_id):
    return SimpleNamespace(organization_id=str(org_id))


def _make_entry(org_id):
    return SimpleNamespace(
        organization_id=org_id,
        status=PayrollEntryStatus.POSTED,
        payroll_year=2026,
        payroll_month=11,
        start_date=date(2026, 11, 1),
    )


def test_export_paye_response_uses_requested_format(monkeypatch):
    org_id = uuid4()
    entry_id = uuid4()
    calls: dict[str, object] = {}

    class FakePAYEExportService:
        def __init__(self, db):
            self.db = db

        def generate_export(
            self,
            organization_id,
            year,
            month,
            paye_format="lirs",
            entry_id=None,
        ):
            calls["organization_id"] = organization_id
            calls["year"] = year
            calls["month"] = month
            calls["paye_format"] = paye_format
            calls["entry_id"] = entry_id
            return PAYEExportResult(
                content=b"tax",
                filename="FCTIRS_PAYE_2026_11.csv",
                content_type="text/csv",
                employee_count=1,
                total_tax=0,
                errors=[],
            )

    monkeypatch.setattr(
        "app.services.people.payroll.paye_export.PAYEExportService",
        FakePAYEExportService,
    )

    db = SimpleNamespace(get=lambda _model, _id: _make_entry(org_id))

    response = RunWebService().export_paye_response(
        _make_auth(org_id),
        db,
        str(entry_id),
        "fctirs",
    )

    assert isinstance(response, StreamingResponse)
    assert calls["organization_id"] == org_id
    assert calls["year"] == 2026
    assert calls["month"] == 11
    assert calls["paye_format"] == "fctirs"
    assert calls["entry_id"] == entry_id
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="FCTIRS_PAYE_2026_11.csv"'
    )
