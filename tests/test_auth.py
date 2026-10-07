import re

import pytest

from app import create_app
from app.config import TestConfig
from app.models import AuditLog, User, UserRole
from tests.conftest import ADMIN, VIEWER


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_anonymous_redirected_to_login(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_page_shows_dev_login_without_sso(client):
    body = client.get("/login").get_data(as_text=True)
    assert "Development login" in body
    assert "Sign in with Microsoft" not in body


def test_dev_login_provisions_default_role(client, login, db):
    user = login(VIEWER)
    assert user.role == UserRole.viewer
    assert client.get("/").status_code == 200
    assert db.session.query(AuditLog).filter_by(action="login").count() == 1


def test_admin_email_gets_admin(login):
    assert login(ADMIN).role == UserRole.admin


def test_existing_user_promoted_when_added_to_admin_emails(app, login, db):
    user = login(VIEWER)
    app.config["ADMIN_EMAILS"] = [VIEWER]
    login(VIEWER)
    db.session.refresh(user)
    assert user.role == UserRole.admin


def test_domain_not_allowed(client, db):
    resp = client.post("/login/dev", data={"email": "someone@gmail.com"})
    assert resp.status_code == 403
    assert db.session.query(User).count() == 0


def test_deactivated_user_cannot_sign_in(client, login, db):
    user = login(VIEWER)
    user.is_active = False
    db.session.commit()
    assert client.get("/").status_code == 302  # existing session ends
    assert client.post("/login/dev", data={"email": VIEWER}).status_code == 403


def test_logout_requires_post(client, login):
    login()
    assert client.get("/logout").status_code == 405
    assert client.post("/logout").status_code == 302
    assert client.get("/").status_code == 302


def test_dev_login_disabled_when_sso_configured(app, client):
    class SSO(TestConfig):
        AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET = "t", "c", "s"
    original = app.config_class
    app.config_class = SSO
    try:
        assert client.post("/login/dev", data={"email": ADMIN}).status_code == 404
    finally:
        app.config_class = original


def test_refuses_to_start_behind_proxy_without_sso():
    class Deployed(TestConfig):
        BEHIND_PROXY = True
    with pytest.raises(RuntimeError, match="dev login"):
        create_app(Deployed)


def test_refuses_partial_sso_config():
    class Partial(TestConfig):
        AZURE_CLIENT_ID = "abc"
    with pytest.raises(RuntimeError, match="partially configured"):
        create_app(Partial)


def test_refuses_weak_secret_key():
    class Weak(TestConfig):
        SECRET_KEY = "short"
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(Weak)


def test_csrf_enforced(app, client, login):
    login()
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post("/tasks/create", data={"title": "x"}).status_code == 400

    page = client.get("/tasks").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    resp = client.post("/tasks/create", data={"title": "x", "csrf_token": token})
    assert resp.status_code == 302
