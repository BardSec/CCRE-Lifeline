from app.models import Rubric, RubricItem, Tenant, User, UserRole
from app.services.seed import seed
from tests.conftest import VIEWER


def test_seed_is_idempotent(db):
    seed("Lakeside School District")
    assert db.session.query(Rubric).count() == 1
    assert db.session.query(RubricItem).count() == 15
    assert db.session.query(Tenant).count() == 1


def test_seed_does_not_duplicate_renamed_tenant(db):
    db.session.query(Tenant).one().name = "Renamed District"
    db.session.commit()
    seed("Lakeside School District")
    assert db.session.query(Tenant).count() == 1


def test_admin_pages_require_admin(client, login):
    login(VIEWER)
    for url in ("/admin/users", "/admin/tenant", "/admin/audit-log"):
        assert client.get(url).status_code == 403


def test_admin_updates_user_but_not_self(client, login, db):
    admin = login()
    client.post("/logout")
    viewer = login(VIEWER)
    client.post("/logout")
    login()
    assert client.post(f"/admin/users/{viewer.id}/update", data={"role": "evaluator"}).status_code == 302
    db.session.refresh(viewer)
    assert viewer.role == UserRole.evaluator
    assert client.post(f"/admin/users/{admin.id}/update", data={"role": "viewer"}).status_code == 400
    assert client.post(f"/admin/users/{viewer.id}/update", data={"role": "superuser"}).status_code == 400


def test_tenant_settings_validation(client, login, db):
    login()
    assert client.post("/admin/tenant", data={"name": "Maryville", "stale_evidence_days": "120"}).status_code == 302
    assert db.session.query(Tenant).one().stale_evidence_days == 120
    assert client.post("/admin/tenant", data={"name": "M", "stale_evidence_days": "abc"}).status_code == 400
    assert client.get("/admin/audit-log?page=0").status_code == 400
    assert client.get("/admin/audit-log").status_code == 200


def test_dashboard_renders(client, login):
    login()
    assert client.get("/").status_code == 200
