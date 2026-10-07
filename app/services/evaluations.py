from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import joinedload
from werkzeug.exceptions import BadRequest, NotFound

from app.extensions import db
from app.models import (
    Confidence, Evaluation, EvaluationStatus, Rubric, RubricDomain, RubricItem,
    Score, Task, TaskStatus, User,
)
from app.services import audit
from app.services.validation import (
    enum_value, int_in_range, optional_uuid, required, required_date,
)


def list_for_tenant(tenant_id: uuid.UUID) -> list[Evaluation]:
    return (
        db.session.query(Evaluation)
        .filter(Evaluation.tenant_id == tenant_id)
        .order_by(Evaluation.created_at.desc())
        .all()
    )


def list_rubrics() -> list[Rubric]:
    # Rubrics are shared reference data, not tenant-owned.
    return db.session.query(Rubric).order_by(Rubric.name).all()


def get_for_tenant(tenant_id: uuid.UUID, eval_id: uuid.UUID) -> Evaluation:
    obj = db.session.query(Evaluation).filter(
        Evaluation.id == eval_id, Evaluation.tenant_id == tenant_id,
    ).first()
    if obj is None:
        raise NotFound()
    return obj


def active_users(tenant_id: uuid.UUID) -> list[User]:
    return (
        db.session.query(User)
        .filter(User.tenant_id == tenant_id, User.is_active.is_(True))
        .order_by(User.name)
        .all()
    )


def _require_tenant_user(tenant_id: uuid.UUID, user_id: uuid.UUID | None) -> None:
    if user_id is None:
        return
    exists = db.session.query(User.id).filter(
        User.id == user_id, User.tenant_id == tenant_id,
    ).first()
    if not exists:
        raise BadRequest("Owner is not a user in this organization.")


def create(actor: User, form) -> Evaluation:
    """Create an evaluation with one unscored Score row per rubric item."""
    rubric_id = optional_uuid(form.get("rubric_id"), "Rubric")
    rubric = db.session.get(Rubric, rubric_id) if rubric_id else None
    if rubric is None:
        raise BadRequest("Choose a rubric.")

    period_start = required_date(form.get("period_start"), "Period start")
    period_end = required_date(form.get("period_end"), "Period end")
    if period_end < period_start:
        raise BadRequest("Period end must be on or after period start.")

    evaluation = Evaluation(
        tenant_id=actor.tenant_id,
        rubric_id=rubric.id,
        title=required(form.get("title"), "Title"),
        period_start=period_start,
        period_end=period_end,
        created_by=actor.id,
    )
    db.session.add(evaluation)
    db.session.flush()

    items = (
        db.session.query(RubricItem)
        .join(RubricDomain)
        .filter(RubricDomain.rubric_id == rubric.id)
        .all()
    )
    for item in items:
        db.session.add(Score(evaluation_id=evaluation.id, rubric_item_id=item.id))

    audit.record(actor, "create_evaluation", "evaluation", evaluation.id, {"title": evaluation.title})
    db.session.commit()
    return evaluation


def detail(evaluation: Evaluation) -> tuple[list[dict], dict]:
    """Scores grouped by domain (in rubric order) and each domain's average.

    Unscored items (maturity 0) are left out of the averages.
    """
    scores = (
        db.session.query(Score)
        .join(RubricItem)
        .join(RubricDomain)
        .filter(Score.evaluation_id == evaluation.id)
        .options(joinedload(Score.rubric_item).joinedload(RubricItem.domain))
        .order_by(RubricDomain.sort_order, RubricItem.sort_order)
        .all()
    )

    domains: dict = {}
    for score in scores:
        domain = score.rubric_item.domain
        domains.setdefault(domain.id, {"domain": domain, "scores": []})
        domains[domain.id]["scores"].append(score)

    averages = {}
    for domain_id, data in domains.items():
        scored = [s.maturity_level for s in data["scores"] if s.maturity_level > 0]
        averages[domain_id] = round(sum(scored) / len(scored), 1) if scored else None

    return list(domains.values()), averages


def update_score(actor: User, evaluation: Evaluation, score_id: uuid.UUID, form) -> Score:
    if evaluation.status == EvaluationStatus.final:
        raise BadRequest("This evaluation is finalized; scores are read-only.")

    score = db.session.query(Score).filter(
        Score.id == score_id, Score.evaluation_id == evaluation.id,
    ).first()
    if score is None:
        raise NotFound()

    owner_id = optional_uuid(form.get("owner_user_id"), "Owner")
    _require_tenant_user(actor.tenant_id, owner_id)

    score.maturity_level = int_in_range(form.get("maturity_level"), "Maturity level", 0, 5)
    confidence = form.get("confidence")
    score.confidence = enum_value(Confidence, confidence, "Confidence") if confidence else None
    score.rationale = form.get("rationale")
    score.compensating_controls = form.get("compensating_controls")
    score.owner_user_id = owner_id
    score.updated_at = datetime.utcnow()

    audit.record(actor, "update_score", "score", score.id, {"maturity_level": score.maturity_level})
    db.session.commit()
    return score


def finalize(actor: User, evaluation: Evaluation) -> None:
    evaluation.status = EvaluationStatus.final
    audit.record(actor, "finalize_evaluation", "evaluation", evaluation.id)
    db.session.commit()


def suggest_tasks(actor: User, evaluation: Evaluation, target_level: int) -> int:
    """Create one improvement task per item scoring below *target_level*.

    Items that already have a task on this evaluation are skipped, so running
    this again doesn't create duplicates. Returns the number created.
    """
    scores = (
        db.session.query(Score)
        .options(joinedload(Score.rubric_item))
        .filter(Score.evaluation_id == evaluation.id, Score.maturity_level < target_level)
        .all()
    )
    existing = {
        row.rubric_item_id
        for row in db.session.query(Task.rubric_item_id).filter(Task.evaluation_id == evaluation.id)
    }

    created = 0
    for score in scores:
        if score.rubric_item_id in existing:
            continue
        item = score.rubric_item
        db.session.add(Task(
            tenant_id=evaluation.tenant_id,
            evaluation_id=evaluation.id,
            rubric_item_id=item.id,
            title=f"Improve: {item.code} – {item.title}",
            description=(
                f"Current maturity: {score.maturity_level}. Target: {target_level}.\n"
                f"Guidance: {item.guidance or ''}"
            ),
            status=TaskStatus.open,
        ))
        created += 1

    audit.record(actor, "suggest_tasks", "evaluation", evaluation.id, {"tasks_created": created})
    db.session.commit()
    return created
