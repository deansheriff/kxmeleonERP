from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _template(name: str) -> str:
    return (ROOT / "templates" / name).read_text()


def test_login_preserves_username_for_required_password_reset():
    login_template = _template("login.html")
    admin_login_template = _template("admin_login.html")

    assert "passwordResetRequiredUsername" in login_template
    assert "passwordResetRequiredUsername" in admin_login_template
    assert "sessionStorage.setItem" in login_template
    assert "sessionStorage.setItem" in admin_login_template


def test_reset_required_form_prefills_and_validates_username():
    template = _template("reset_password_required.html")

    assert "sessionStorage.getItem('passwordResetRequiredUsername')" in template
    assert "this.username = this.username.trim();" in template
    assert "Email or username is required" in template
    assert "sessionStorage.removeItem('passwordResetRequiredUsername')" in template
