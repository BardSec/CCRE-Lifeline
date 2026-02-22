from __future__ import annotations

import io
import uuid
from datetime import datetime
from typing import Optional

from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app.blueprints.helpers import audit, require_contributor_or_above, require_evaluator_or_above
from app.database import get_db
from app.models import (
    Confidence, Evaluation, EvaluationStatus, Rubric, RubricDomain,
    RubricItem, Score, Task, TaskStatus, User,
)
from app.services import csv_export, pdf_export

evaluations_bp = Blueprint("evaluations", __name__, url_prefix="/evaluations")


@evaluations_bp.route("")
@login_required
def list_evaluations():
    db = get_db()
    evals = (
        db.query(Evaluation)
        .filter(Evaluation.tenant_id == current_user.tenant_id)
        .order_by(Evaluation.created_at.desc())
        .all()
    )
    rubrics = db.query(Rubric).all()
    return render_template("evaluations/list.html", evaluations=evals, rubrics=rubrics)


@evaluations_bp.route("", methods=["POST"])
@login_required
@require_evaluator_or_above
def create_evaluation():
    db = get_db()
    rubric_id = request.form["rubric_id"]
    rubric = db.query(Rubric).filter(Rubric.id == rubric_id).first()
    if not rubric:
        abort(404)

    eval_obj = Evaluation(
        tenant_id=current_user.tenant_id,
        rubric_id=rubric.id,
        title=request.form["title"],
        period_start=datetime.fromisoformat(request.form["period_start"]),
        period_end=datetime.fromisoformat(request.form["period_end"]),
        created_by=current_user.id,
    )
    db.add(eval_obj)
    db.flush()

    all_items = (
        db.query(RubricItem)
        .join(RubricDomain)
        .filter(RubricDomain.rubric_id == rubric.id)
        .all()
    )
    for item in all_items:
        db.add(Score(evaluation_id=eval_obj.id, rubric_item_id=item.id))

    audit(db, actor=current_user, action="create_evaluation", entity_type="evaluation",
          entity_id=str(eval_obj.id), detail={"title": eval_obj.title})
    db.commit()
    return redirect(url_for("evaluations.evaluation_detail", eval_id=eval_obj.id))


@evaluations_bp.route("/<uuid:eval_id>")
@login_required
def evaluation_detail(eval_id: uuid.UUID):
    db = get_db()
    eval_obj = _get_eval(db, eval_id)

    scores = (
        db.query(Score)
        .join(RubricItem)
        .join(RubricDomain)
        .filter(Score.evaluation_id == eval_obj.id)
        .options(joinedload(Score.rubric_item).joinedload(RubricItem.domain))
        .order_by(RubricDomain.sort_order, RubricItem.sort_order)
        .all()
    )

    domains: dict = {}
    for score in scores:
        domain = score.rubric_item.domain
        domains.setdefault(domain.id, {"domain": domain, "scores": []})
        domains[domain.id]["scores"].append(score)

    domain_averages = {}
    for d_id, data in domains.items():
        scored = [s.maturity_level for s in data["scores"] if s.maturity_level > 0]
        domain_averages[d_id] = round(sum(scored) / len(scored), 1) if scored else None

    users = db.query(User).filter(
        User.tenant_id == current_user.tenant_id, User.is_active == True
    ).all()

    return render_template(
        "evaluations/detail.html",
        eval=eval_obj,
        domains=list(domains.values()),
        domain_averages=domain_averages,
        users=users,
        Confidence=Confidence,
    )


@evaluations_bp.route("/<uuid:eval_id>/scores/<uuid:score_id>", methods=["POST"])
@login_required
@require_contributor_or_above
def update_score(eval_id: uuid.UUID, score_id: uuid.UUID):
    db = get_db()
    eval_obj = _get_eval(db, eval_id)
    if eval_obj.status == EvaluationStatus.final:
        abort(400)

    score = db.query(Score).filter(
        Score.id == score_id, Score.evaluation_id == eval_obj.id
    ).first()
    if not score:
        abort(404)

    maturity_level = int(request.form["maturity_level"])
    if not (0 <= maturity_level <= 5):
        abort(400)

    confidence_val = request.form.get("confidence")
    owner_id_str = request.form.get("owner_user_id")

    score.maturity_level = maturity_level
    score.confidence = Confidence(confidence_val) if confidence_val else None
    score.rationale = request.form.get("rationale")
    score.compensating_controls = request.form.get("compensating_controls")
    score.owner_user_id = uuid.UUID(owner_id_str) if owner_id_str else None
    score.updated_at = datetime.utcnow()

    audit(db, actor=current_user, action="update_score", entity_type="score",
          entity_id=str(score_id), detail={"maturity_level": maturity_level})
    db.commit()
    return redirect(url_for("evaluations.evaluation_detail", eval_id=eval_id))


@evaluations_bp.route("/<uuid:eval_id>/finalize", methods=["POST"])
@login_required
@require_evaluator_or_above
def finalize_evaluation(eval_id: uuid.UUID):
    db = get_db()
    eval_obj = _get_eval(db, eval_id)
    eval_obj.status = EvaluationStatus.final
    audit(db, actor=current_user, action="finalize_evaluation", entity_type="evaluation",
          entity_id=str(eval_id))
    db.commit()
    return redirect(url_for("evaluations.evaluation_detail", eval_id=eval_id))


@evaluations_bp.route("/<uuid:eval_id>/suggest-tasks", methods=["POST"])
@login_required
@require_evaluator_or_above
def suggest_tasks(eval_id: uuid.UUID):
    db = get_db()
    eval_obj = _get_eval(db, eval_id)
    target_level = int(request.form.get("target_level", 3))

    scores = (
        db.query(Score)
        .options(joinedload(Score.rubric_item))
        .filter(Score.evaluation_id == eval_obj.id, Score.maturity_level < target_level)
        .all()
    )

    created = 0
    for score in scores:
        existing = db.query(Task).filter(
            Task.evaluation_id == eval_obj.id,
            Task.rubric_item_id == score.rubric_item_id,
        ).first()
        if not existing:
            db.add(Task(
                tenant_id=current_user.tenant_id,
                evaluation_id=eval_obj.id,
                rubric_item_id=score.rubric_item_id,
                title=f"Improve: {score.rubric_item.code} – {score.rubric_item.title}",
                description=(
                    f"Current maturity: {score.maturity_level}. Target: {target_level}.\n"
                    f"Guidance: {score.rubric_item.guidance or ''}"
                ),
                status=TaskStatus.open,
            ))
            created += 1

    audit(db, actor=current_user, action="suggest_tasks", entity_type="evaluation",
          entity_id=str(eval_id), detail={"tasks_created": created})
    db.commit()
    return redirect(url_for("evaluations.evaluation_detail", eval_id=eval_id) + "#tasks")


@evaluations_bp.route("/<uuid:eval_id>/export/pdf")
@login_required
def export_pdf(eval_id: uuid.UUID):
    from flask import send_file
    db = get_db()
    eval_obj = _get_eval(db, eval_id)
    buf = pdf_export.generate_evaluation_pdf(db, eval_obj, current_user)
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"evaluation_{eval_id}.pdf",
    )


@evaluations_bp.route("/<uuid:eval_id>/export/csv")
@login_required
def export_csv(eval_id: uuid.UUID):
    from flask import Response
    db = get_db()
    eval_obj = _get_eval(db, eval_id)
    buf = csv_export.generate_evaluation_csv(db, eval_obj)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="evaluation_{eval_id}.csv"'},
    )


def _get_eval(db, eval_id: uuid.UUID) -> Evaluation:
    obj = db.query(Evaluation).filter(
        Evaluation.id == eval_id,
        Evaluation.tenant_id == current_user.tenant_id,
    ).first()
    if not obj:
        abort(404)
    return obj
