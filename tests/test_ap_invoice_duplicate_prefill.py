from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.templates import templates
from app.services.finance.ap.web.invoice_web import InvoiceWebService


def test_duplicate_invoice_context_preserves_raw_multiline_text() -> None:
    db = MagicMock()
    org_id = uuid4()
    invoice_id = uuid4()
    supplier_id = uuid4()

    invoice = SimpleNamespace(
        invoice_id=invoice_id,
        organization_id=org_id,
        invoice_number="SINV202604-0087",
        supplier_id=supplier_id,
        currency_code="NGN",
        supplier_invoice_number="0187",
        purpose="Line 1\nLine 2 with O'Brien",
        comments="Internal comment",
        exchange_rate=1,
    )
    line = SimpleNamespace(
        item_id=None,
        expense_account_id=None,
        description="Legal services for O'Brien\nSecond line",
        quantity=1,
        unit_price=500000,
        tax_code_id=None,
        tax_amount=0,
        line_number=1,
    )
    scalars_result = MagicMock()
    scalars_result.all.return_value = [line]

    db.get.return_value = invoice
    db.scalars.return_value = scalars_result

    context = InvoiceWebService._duplicate_invoice_context(
        db,
        str(org_id),
        str(invoice_id),
    )

    assert context is not None
    assert context["supplier_invoice_number"] == "0187"
    assert context["purpose"] == "Line 1\nLine 2 with O'Brien"
    assert (
        context["lines"][0]["description"] == "Legal services for O'Brien\nSecond line"
    )


def test_ap_invoice_form_uses_json_safe_duplicate_source_prefill() -> None:
    template = Path("templates/finance/ap/invoice_form.html").read_text()

    assert (
        "const duplicateSource = {{ duplicate_source | tojson | safe if duplicate_source else 'null' }};"
        in template
    )
    assert (
        "this.form.invoice_number = duplicateSource.supplier_invoice_number || '';"
        in template
    )
    assert (
        "this.form.purpose = '{{ duplicate_source.purpose if duplicate_source.purpose else \"\" }}';"
        not in template
    )
    assert "{% if duplicate_source and duplicate_source.lines %}" not in template


def test_ap_invoice_edit_form_does_not_nest_comment_form() -> None:
    template = Path("templates/finance/ap/invoice_form.html").read_text()

    invoice_form_start = template.index('<form id="ap-invoice-form"')
    invoice_form_end = template.index("{% if invoice %}", invoice_form_start)
    comment_form_start = template.index(
        '<form action="/finance/ap/invoices/{{ invoice.invoice_id }}/comments"'
    )

    assert invoice_form_end < comment_form_start
    assert template.count('<form id="ap-invoice-form"') == 1
    assert '<button type="button" @click="submitForm" class="btn-primary"' in template


def test_duplicate_invoice_context_renders_with_tojson() -> None:
    db = MagicMock()
    org_id = uuid4()
    invoice_id = uuid4()
    supplier_id = uuid4()

    invoice = SimpleNamespace(
        invoice_id=invoice_id,
        organization_id=org_id,
        invoice_number="SINV202604-0087",
        supplier_id=supplier_id,
        currency_code="NGN",
        supplier_invoice_number="0187",
        purpose="Line 1\nLine 2 with O'Brien",
        comments="",
        exchange_rate=Decimal("1.00"),
    )
    line = SimpleNamespace(
        item_id=None,
        expense_account_id=None,
        description="Legal services for O'Brien\nSecond line",
        quantity=Decimal("1.00"),
        unit_price=Decimal("500000.00"),
        tax_code_id=None,
        tax_amount=Decimal("0.00"),
        line_number=1,
    )
    scalars_result = MagicMock()
    scalars_result.all.return_value = [line]

    db.get.return_value = invoice
    db.scalars.return_value = scalars_result

    duplicate_source = InvoiceWebService._duplicate_invoice_context(
        db,
        str(org_id),
        str(invoice_id),
    )

    rendered = templates.env.from_string(
        "{{ duplicate_source | tojson | safe if duplicate_source else 'null' }}"
    ).render(duplicate_source=duplicate_source)

    assert "SINV202604-0087" in rendered
    assert "500000.0" in rendered
    assert "\\n" in rendered
