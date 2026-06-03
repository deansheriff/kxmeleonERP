"""Tests for GL journal web view helpers."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.models.finance.gl.journal_entry import JournalStatus, JournalType
from app.services.finance.gl.web.base import journal_entry_view


def test_journal_entry_view_includes_source_document_fields():
    source_document_id = uuid4()
    entry = SimpleNamespace(
        journal_entry_id=uuid4(),
        journal_number="JE-202604-0001",
        journal_type=JournalType.ADJUSTMENT,
        entry_date=date(2026, 4, 30),
        posting_date=date(2026, 4, 30),
        description="Draft FA GL reconciliation correction",
        reference="FA-GL-RECON:package",
        status=JournalStatus.DRAFT,
        source_module="FA",
        source_document_type="FA_GL_RECONCILIATION",
        source_document_id=source_document_id,
        total_debit=Decimal("50.00"),
        total_credit=Decimal("50.00"),
        currency_code="NGN",
        created_at=None,
    )

    result = journal_entry_view(entry)

    assert result["source_module"] == "FA"
    assert result["source_document_type"] == "FA_GL_RECONCILIATION"
    assert result["source_document_id"] == str(source_document_id)
