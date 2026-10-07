from __future__ import annotations

import io
import uuid

from flask import Blueprint, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app.blueprints.helpers import require_contributor_or_above
from app.models import Sensitivity
from app.services import evidence

evidence_bp = Blueprint("evidence", __name__, url_prefix="/evidence")


@evidence_bp.route("")
@login_required
def list_evidence():
    return render_template(
        "evidence/list.html",
        evidence_list=evidence.list_for_tenant(current_user.tenant_id),
    )


@evidence_bp.route("/upload")
@login_required
@require_contributor_or_above
def upload_form():
    items, evals = evidence.upload_choices(current_user.tenant_id)
    return render_template(
        "evidence/upload.html",
        rubric_items=items,
        evaluations=evals,
        selected_item_id=request.args.get("rubric_item_id"),
        selected_eval_id=request.args.get("evaluation_id"),
        Sensitivity=Sensitivity,
    )


@evidence_bp.route("/upload", methods=["POST"])
@login_required
@require_contributor_or_above
def upload_evidence():
    evidence.upload(current_user, request.files.get("file"), request.form)
    return redirect(url_for("evidence.list_evidence"))


@evidence_bp.route("/<uuid:evidence_id>/download")
@login_required
def download_evidence(evidence_id: uuid.UUID):
    ev = evidence.get_for_tenant(current_user.tenant_id, evidence_id)
    data = evidence.read(current_user, ev)
    return send_file(
        io.BytesIO(data),
        mimetype=ev.content_type,
        as_attachment=True,
        download_name=ev.filename,
    )


@evidence_bp.route("/<uuid:evidence_id>/delete", methods=["POST"])
@login_required
@require_contributor_or_above
def delete_evidence(evidence_id: uuid.UUID):
    ev = evidence.get_for_tenant(current_user.tenant_id, evidence_id)
    evidence.delete(current_user, ev)
    return redirect(url_for("evidence.list_evidence"))
