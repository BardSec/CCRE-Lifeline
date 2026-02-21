"""
Smoke tests for RubricOps.

These tests run against the live app (requires DB + MinIO to be up).
Run: docker compose exec web pytest tests/ -v

For unit testing without dependencies, mock the database session.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import get_db
from app.models import Base, Tenant, User, UserRole
from app.auth.security import hash_password, verify_password, create_access_token, decode_token
from app.config import get_settings

settings = get_settings()


# ── Security unit tests (no DB required) ──────────────────────────────────────

class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "TestPassword123!"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed)

    def test_wrong_password_rejected(self):
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)

    def test_bcrypt_prefix(self):
        hashed = hash_password("any")
        assert hashed.startswith("$2b$")


class TestJWT:
    def test_create_and_decode(self):
        token = create_access_token({"sub": "user-123", "role": "admin"})
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["role"] == "admin"

    def test_invalid_token_returns_none(self):
        result = decode_token("not.a.valid.token")
        assert result is None

    def test_tampered_token_returns_none(self):
        token = create_access_token({"sub": "abc"})
        tampered = token[:-5] + "XXXXX"
        assert decode_token(tampered) is None


# ── HTTP smoke tests (requires running DB) ────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """TestClient using in-memory SQLite for isolation."""
    SQLITEURL = "sqlite:///./test_rubricops.db"
    test_engine = create_engine(SQLITEURL, connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    # Seed minimal data
    db = TestSession()
    tenant = Tenant(name="Test District")
    db.add(tenant)
    db.flush()
    admin = User(
        tenant_id=tenant.id,
        email="admin@test.local",
        password_hash=hash_password("Admin123!"),
        name="Test Admin",
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.close()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)

    import os
    if os.path.exists("test_rubricops.db"):
        os.remove("test_rubricops.db")


class TestAuthRoutes:
    def test_login_page_returns_200(self, client):
        r = client.get("/login", follow_redirects=False)
        assert r.status_code == 200
        assert "RubricOps" in r.text

    def test_login_wrong_password_returns_401(self, client):
        r = client.post("/login", data={"email": "admin@test.local", "password": "wrong"})
        assert r.status_code == 401

    def test_login_success_redirects(self, client):
        r = client.post(
            "/login",
            data={"email": "admin@test.local", "password": "Admin123!"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert r.headers["location"] == "/"

    def test_healthz_ok(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestProtectedRoutes:
    def test_dashboard_unauthenticated_redirects(self, client):
        r = client.get("/", follow_redirects=False)
        # Should redirect to /login (via 401 handler or cookie check)
        assert r.status_code in (302, 401)

    def test_evaluations_unauthenticated_redirects(self, client):
        r = client.get("/evaluations", follow_redirects=False)
        assert r.status_code in (302, 401)


class TestModelEnums:
    def test_user_role_values(self):
        assert UserRole.admin.value == "admin"
        assert UserRole.viewer.value == "viewer"

    def test_valid_roles(self):
        roles = {r.value for r in UserRole}
        assert roles == {"admin", "evaluator", "contributor", "viewer"}
