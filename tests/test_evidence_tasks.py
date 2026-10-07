import io
from pathlib import Path

from app.models import Evidence, RubricItem, Task, UserRole
from app.services.storage import safe_extension
from tests.conftest import VIEWER, login_as


def _upload(client, db, filename="policy.pdf", content_type="application/pdf", data=b"%PDF-1.4 test"):
    item = db.session.query(RubricItem).first()
    return client.post("/evidence/upload", content_type="multipart/form-data", data={
        "file": (io.BytesIO(data), filename, content_type),
        "rubric_item_id": str(item.id),
        "evidence_type": "policy",
        "sensitivity": "internal",
    })


def test_upload_download_delete(app, client, login, db):
    login()
    assert _upload(client, db).status_code == 302
    ev = db.session.query(Evidence).one()
    path = Path(app.config["EVIDENCE_DIR"]) / ev.object_key
    assert path.exists()

    resp = client.get(f"/evidence/{ev.id}/download")
    assert resp.status_code == 200 and resp.data == b"%PDF-1.4 test"

    assert client.post(f"/evidence/{ev.id}/delete").status_code == 302
    assert not path.exists()
    assert db.session.query(Evidence).count() == 0


def test_upload_filename_cannot_escape_storage(app, client, login, db):
    login()
    assert _upload(client, db, filename="x./../../../../tmp/pwned").status_code == 302
    ev = db.session.query(Evidence).one()
    assert ev.object_key.endswith(".bin")
    root = Path(app.config["EVIDENCE_DIR"]).resolve()
    assert (root / ev.object_key).resolve().is_relative_to(root)


def test_safe_extension():
    assert safe_extension("Report.PDF") == "pdf"
    assert safe_extension("noext") == "bin"
    assert safe_extension("a./../../etc/passwd") == "bin"
    assert safe_extension("a.verylongextension") == "bin"


def test_upload_rejects_type_and_viewer(client, login, db):
    login()
    assert _upload(client, db, filename="x.exe", content_type="application/x-msdownload").status_code == 415
    client.post("/logout")
    login(VIEWER)
    assert _upload(client, db).status_code == 403
    assert db.session.query(Evidence).count() == 0


def test_other_tenant_cannot_download(app, client, login, db, other_tenant_user):
    login()
    _upload(client, db)
    ev = db.session.query(Evidence).one()
    other = app.test_client()
    login_as(other, other_tenant_user)
    assert other.get(f"/evidence/{ev.id}/download").status_code == 404
    assert other.post(f"/evidence/{ev.id}/delete").status_code == 404


def test_task_create_and_update(client, login, db):
    user = login()
    resp = client.post("/tasks/create", data={"title": "Roll out MFA", "owner_user_id": str(user.id),
                                              "due_date": "2026-12-01"})
    assert resp.status_code == 302
    task = db.session.query(Task).one()
    resp = client.post(f"/tasks/{task.id}/update", data={"new_status": "done"})
    assert resp.status_code == 302
    db.session.refresh(task)
    assert task.status.value == "done" and task.owner_user_id is None


def test_task_rejects_foreign_references(client, login, db, other_tenant_user):
    login()
    assert client.post("/tasks/create", data={"title": "x", "owner_user_id": str(other_tenant_user.id)}).status_code == 400
    assert client.post("/tasks/create", data={"title": ""}).status_code == 400
    assert client.post("/tasks/create", data={"title": "x", "due_date": "soon"}).status_code == 400
    assert db.session.query(Task).count() == 0


def test_contributor_can_update_task_viewer_cannot(client, login, db):
    login()
    client.post("/tasks/create", data={"title": "x"})
    task = db.session.query(Task).one()
    client.post("/logout")
    login(VIEWER)
    assert client.post(f"/tasks/{task.id}/update", data={"new_status": "done"}).status_code == 403
    client.post("/logout")
    login("contrib@district.edu", role=UserRole.contributor)
    assert client.post(f"/tasks/{task.id}/update", data={"new_status": "done"}).status_code == 302
