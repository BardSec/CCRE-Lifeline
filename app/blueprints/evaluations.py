from __future__ import annotations

import uuid

from flask import Blueprint, Response, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app.blueprints.helpers import require_contributor_or_above, require_evaluator_or_above
from app.extensions import db
from app.models import Confidence
from app.services import csv_export, evaluations, pdf_export
from app.services.validation import int_in_range

evaluations_bp = Blueprint("evaluations", __name__, url_prefix="/evaluations")


@evaluations_bp.route("")
@login_required
def list_evaluations():
    return render_template(
        "evaluations/list.html",
        evaluations=evaluations.list_for_tenant(current_user.tenant_id),
        rubrics=evaluations.list_rubrics(),
    )


@evaluations_bp.route("", methods=["POST"])
@login_required
@require_evaluator_or_above
def create_evaluation():
    evaluation = evaluations.create(current_user, request.form)
    return redirect(url_for("evaluations.evaluation_detail", eval_id=evaluation.id))


@evaluations_bp.route("/<uuid:eval_id>")
@login_required
def evaluation_detail(eval_id: uuid.UUID):
    evaluation = evaluations.get_for_tenant(current_user.tenant_id, eval_id)
    domains, domain_averages = evaluations.detail(evaluation)
    return render_template(
        "evaluations/detail.html",
        eval=evaluation,
        domains=domains,
        domain_averages=domain_averages,
        users=evaluations.active_users(current_user.tenant_id),
        Confidence=Confidence,
    )


@evaluations_bp.route("/<uuid:eval_id>/scores/<uuid:score_id>", methods=["POST"])
@login_required
@require_contributor_or_above
def update_score(eval_id: uuid.UUID, score_id: uuid.UUID):
    evaluation = evaluations.get_for_tenant(current_user.tenant_id, eval_id)
    evaluations.update_score(current_user, evaluation, score_id, request.form)
    return redirect(url_for("evaluations.evaluation_detail", eval_id=eval_id))


@evaluations_bp.route("/<uuid:eval_id>/finalize", methods=["POST"])
@login_required
@require_evaluator_or_above
def finalize_evaluation(eval_id: uuid.UUID):
    evaluation = evaluations.get_for_tenant(current_user.tenant_id, eval_id)
    evaluations.finalize(current_user, evaluation)
    return redirect(url_for("evaluations.evaluation_detail", eval_id=eval_id))


@evaluations_bp.route("/<uuid:eval_id>/suggest-tasks", methods=["POST"])
@login_required
@require_evaluator_or_above
def suggest_tasks(eval_id: uuid.UUID):
    evaluation = evaluations.get_for_tenant(current_user.tenant_id, eval_id)
    target = int_in_range(request.form.get("target_level"), "Target level", 1, 5, default=3)
    evaluations.suggest_tasks(current_user, evaluation, target)
    return redirect(url_for("evaluations.evaluation_detail", eval_id=eval_id) + "#tasks")


@evaluations_bp.route("/<uuid:eval_id>/export/pdf")
@login_required
def export_pdf(eval_id: uuid.UUID):
    evaluation = evaluations.get_for_tenant(current_user.tenant_id, eval_id)
    buf = pdf_export.generate_evaluation_pdf(db.session, evaluation, current_user)
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"evaluation_{eval_id}.pdf",
    )


@evaluations_bp.route("/<uuid:eval_id>/export/csv")
@login_required
def export_csv(eval_id: uuid.UUID):
    evaluation = evaluations.get_for_tenant(current_user.tenant_id, eval_id)
    buf = csv_export.generate_evaluation_csv(db.session, evaluation)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="evaluation_{eval_id}.csv"'},
    )
