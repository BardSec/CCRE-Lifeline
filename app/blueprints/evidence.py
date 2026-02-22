from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from flask import Blueprint, abort, current_app, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app.blueprints.helpers import audit, require_contributor_or_above
from app.database import get_db
from app.models import Evaluation, Evidence, RubricItem, Sensitivity
from app.services import storage

evidence_bp = Blueprint("evidence", __name__, url_prefix="/evidence")


@evidence_bp.route("")
@login_required
def list_evidence():
    db = get_db()
    ev_list = (
        db.query(Evidence)
        .filter(Evidence.tenant_id == current_user.tenant_id)
        .order_by(Evidence.uploaded_at.desc())
        .all()
    )
    return render_template("evidence/list.html", evidence_list=ev_list)


@evidence_bp.route("/upload")
@login_required
@require_contributor_or_above
def upload_form():
    db = get_db()
    items = db.query(RubricItem).all()
    evals = db.query(Evaluation).filter(
        Evaluation.tenant_id == current_user.tenant_id
    ).all()
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
    db = get_db()
    file = request.files.get("file")
    if not file:
        abort(400)

    allowed_types: list[str] = current_app.config["ALLOWED_CONTENT_TYPES"]
    if file.content_type not in allowed_types:
        abort(415)

    data = file.read()
    max_bytes: int = current_app.config["MAX_UPLOAD_BYTES"]
    if len(data) > max_bytes:
        abort(413)

    rubric_item_id = request.form["rubric_item_id"]
    item = db.query(RubricItem).filter(RubricItem.id == rubric_item_id).first()
    if not item:
        abort(404)

    evaluation_id_str: Optional[str] = request.form.get("evaluation_id")
    eval_id_uuid = None
    if evaluation_id_str:
        eval_obj = db.query(Evaluation).filter(
            Evaluation.id == evaluation_id_str,
            Evaluation.tenant_id == current_user.tenant_id,
        ).first()
        if not eval_obj:
            abort(404)
        eval_id_uuid = eval_obj.id

    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "bin"
    object_key = storage.save_file(str(current_user.tenant_id), data, ext)

    expiry_date_str: Optional[str] = request.form.get("expiry_date")
    expiry = datetime.fromisoformat(expiry_date_str) if expiry_date_str else None

    ev = Evidence(
        tenant_id=current_user.tenant_id,
        rubric_item_id=item.id,
        evaluation_id=eval_id_uuid,
        object_key=object_key,
        filename=file.filename,
        content_type=file.content_type,
        size_bytes=len(data),
        uploaded_by=current_user.id,
        evidence_type=request.form["evidence_type"],
        sensitivity=Sensitivity(request.form.get("sensitivity", "internal")),
        expiry_date=expiry,
        notes=request.form.get("notes"),
    )
    db.add(ev)
    audit(db, actor=current_user, action="upload_evidence", entity_type="evidence",
          entity_id=object_key, detail={"filename": file.filename, "size_bytes": len(data)})
    db.commit()
    return redirect(url_for("evidence.list_evidence"))


@evidence_bp.route("/<uuid:evidence_id>/download")
@login_required
def download_evidence(evidence_id: uuid.UUID):
    db = get_db()
    ev = db.query(Evidence).filter(
        Evidence.id == evidence_id,
        Evidence.tenant_id == current_user.tenant_id,
    ).first()
    if not ev:
        abort(404)

    try:
        data = storage.read_file(ev.object_key)
    except FileNotFoundError:
        abort(404)

    import io
    audit(db, actor=current_user, action="download_evidence", entity_type="evidence",
          entity_id=str(evidence_id))
    db.commit()

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
    db = get_db()
    ev = db.query(Evidence).filter(
        Evidence.id == evidence_id,
        Evidence.tenant_id == current_user.tenant_id,
    ).first()
    if not ev:
        abort(404)

    storage.delete_file(ev.object_key)
    audit(db, actor=current_user, action="delete_evidence", entity_type="evidence",
          entity_id=str(evidence_id), detail={"filename": ev.filename})
    db.delete(ev)
    db.commit()
    return redirect(url_for("evidence.list_evidence"))
