"""
Smoke tests for RubricOps.

These tests verify the Flask app can be created and the healthz endpoint responds.
Run: docker compose exec web pytest tests/ -v
"""
from __future__ import annotations

import pytest

from app import create_app


@pytest.fixture
def app():
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_login_redirect(client):
    """Unauthenticated requests to / should redirect to login."""
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 401)
