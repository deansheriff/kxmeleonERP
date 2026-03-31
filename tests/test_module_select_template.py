from types import SimpleNamespace

from app.templates import templates


def test_module_select_does_not_render_self_service_tile():
    html = templates.env.get_template("module_select.html").render(
        title="Dotmac | Select Module",
        brand={"name": "Dotmac"},
        user=SimpleNamespace(is_admin=False),
        accessible_modules=["people", "self_service"],
        csrf_token="test-csrf-token",
    )

    assert 'href="/people/self"' not in html
    assert "Open Self Service" not in html
    assert "Open People" in html
