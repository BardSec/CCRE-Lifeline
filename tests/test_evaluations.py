from app.models import (
    AuditLog, Evaluation, EvaluationStatus, Rubric, Score, Task, UserRole,
)
from tests.conftest import EVALUATOR, VIEWER, login_as


def _create(client, db, **overrides):
    rubric = db.session.query(Rubric).one()
    data = {"rubric_id": str(rubric.id), "title": "FY26 Review",
            "period_start": "2026-07-01", "period_end": "2027-06-30"}
    data.update(overrides)
    return client.post("/evaluations", data=data)


def test_viewer_cannot_create(client, login, db):
    login(VIEWER)
    assert _create(client, db).status_code == 403


def test_create_adds_a_score_per_item(client, login, db):
    login(EVALUATOR, role=UserRole.evaluator)
    resp = _create(client, db)
    assert resp.status_code == 302
    evaluation = db.session.query(Evaluation).one()
    assert db.session.query(Score).filter_by(evaluation_id=evaluation.id).count() == 15
    assert db.session.query(AuditLog).filter_by(action="create_evaluation").count() == 1
    assert client.get(f"/evaluations/{evaluation.id}").status_code == 200


def test_create_validates_input(client, login, db):
    login()
    assert _create(client, db, title="").status_code == 400
    assert _create(client, db, period_start="not-a-date").status_code == 400
    assert _create(client, db, period_end="2020-01-01").status_code == 400
    assert _create(client, db, rubric_id="nope").status_code == 400
    assert db.session.query(Evaluation).count() == 0


def _evaluation_with_score(client, login, db):
    user = login()
    _create(client, db)
    evaluation = db.session.query(Evaluation).one()
    score = db.session.query(Score).filter_by(evaluation_id=evaluation.id).first()
    return user, evaluation, score


def test_update_score(client, login, db):
    user, evaluation, score = _evaluation_with_score(client, login, db)
    resp = client.post(f"/evaluations/{evaluation.id}/scores/{score.id}",
                       data={"maturity_level": "4", "confidence": "high",
                             "owner_user_id": str(user.id), "rationale": "MFA everywhere"})
    assert resp.status_code == 302
    db.session.refresh(score)
    assert (score.maturity_level, score.confidence.value, score.owner_user_id) == (4, "high", user.id)


def test_update_score_rejects_bad_input(client, login, db):
    _, evaluation, score = _evaluation_with_score(client, login, db)
    url = f"/evaluations/{evaluation.id}/scores/{score.id}"
    assert client.post(url, data={"maturity_level": "9"}).status_code == 400
    assert client.post(url, data={"maturity_level": "x"}).status_code == 400
    assert client.post(url, data={"maturity_level": "2", "confidence": "bogus"}).status_code == 400


def test_score_owner_must_be_in_tenant(client, login, db, other_tenant_user):
    _, evaluation, score = _evaluation_with_score(client, login, db)
    resp = client.post(f"/evaluations/{evaluation.id}/scores/{score.id}",
                       data={"maturity_level": "2", "owner_user_id": str(other_tenant_user.id)})
    assert resp.status_code == 400


def test_finalized_scores_are_read_only(client, login, db):
    _, evaluation, score = _evaluation_with_score(client, login, db)
    client.post(f"/evaluations/{evaluation.id}/finalize")
    db.session.refresh(evaluation)
    assert evaluation.status == EvaluationStatus.final
    resp = client.post(f"/evaluations/{evaluation.id}/scores/{score.id}", data={"maturity_level": "3"})
    assert resp.status_code == 400


def test_suggest_tasks_is_idempotent(client, login, db):
    _, evaluation, score = _evaluation_with_score(client, login, db)
    client.post(f"/evaluations/{evaluation.id}/scores/{score.id}", data={"maturity_level": "4"})
    client.post(f"/evaluations/{evaluation.id}/suggest-tasks", data={"target_level": "3"})
    assert db.session.query(Task).count() == 14  # every item except the one at level 4
    client.post(f"/evaluations/{evaluation.id}/suggest-tasks", data={"target_level": "3"})
    assert db.session.query(Task).count() == 14


def test_other_tenant_cannot_see_evaluation(app, client, login, db, other_tenant_user):
    _, evaluation, _ = _evaluation_with_score(client, login, db)
    other = app.test_client()
    login_as(other, other_tenant_user)
    assert other.get(f"/evaluations/{evaluation.id}").status_code == 404
    assert other.get(f"/evaluations/{evaluation.id}/export/csv").status_code == 404
    assert "FY26 Review" not in other.get("/evaluations").get_data(as_text=True)


def test_exports(client, login, db):
    _, evaluation, score = _evaluation_with_score(client, login, db)
    client.post(f"/evaluations/{evaluation.id}/scores/{score.id}",
                data={"maturity_level": "2", "rationale": "=HYPERLINK(\"http://x\")"})
    csv = client.get(f"/evaluations/{evaluation.id}/export/csv").get_data(as_text=True)
    assert "'=HYPERLINK" in csv
    pdf = client.get(f"/evaluations/{evaluation.id}/export/pdf")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
