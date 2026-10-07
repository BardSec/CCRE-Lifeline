from __future__ import annotations

import uuid

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import BadRequest, NotFound, RequestEntityTooLarge, UnsupportedMediaType

from app.extensions import db
from app.models import Evaluation, Evidence, RubricItem, Sensitivity, User
from app.services import audit, evaluations
from app.services.storage import get_storage, safe_extension
from app.services.validation import enum_value, optional_date, optional_uuid, required


def list_for_tenant(tenant_id: uuid.UUID) -> list[Evidence]:
    return (
        db.session.query(Evidence)
        .filter(Evidence.tenant_id == tenant_id)
        .order_by(Evidence.uploaded_at.desc())
        .all()
    )


def get_for_tenant(tenant_id: uuid.UUID, evidence_id: uuid.UUID) -> Evidence:
    ev = db.session.query(Evidence).filter(
        Evidence.id == evidence_id, Evidence.tenant_id == tenant_id,
    ).first()
    if ev is None:
        raise NotFound()
    return ev


def upload_choices(tenant_id: uuid.UUID) -> tuple[list[RubricItem], list[Evaluation]]:
    items = db.session.query(RubricItem).order_by(RubricItem.code).all()
    evals = (
        db.session.query(Evaluation)
        .filter(Evaluation.tenant_id == tenant_id)
        .order_by(Evaluation.created_at.desc())
        .all()
    )
    return items, evals


def upload(actor: User, file: FileStorage | None, form) -> Evidence:
    if file is None or not file.filename:
        raise BadRequest("Choose a file to upload.")
    if file.content_type not in current_app.config["ALLOWED_CONTENT_TYPES"]:
        raise UnsupportedMediaType()

    data = file.read()
    if len(data) > current_app.config["MAX_UPLOAD_BYTES"]:
        raise RequestEntityTooLarge()

    item_id = optional_uuid(form.get("rubric_item_id"), "Rubric item")
    item = db.session.get(RubricItem, item_id) if item_id else None
    if item is None:
        raise BadRequest("Choose the rubric item this evidence supports.")

    evaluation_id = optional_uuid(form.get("evaluation_id"), "Evaluation")
    if evaluation_id is not None:
        # Raises NotFound for another tenant's evaluation.
        evaluations.get_for_tenant(actor.tenant_id, evaluation_id)

    sensitivity = enum_value(Sensitivity, form.get("sensitivity") or "internal", "Sensitivity")
    evidence_type = required(form.get("evidence_type"), "Evidence type")
    expiry = optional_date(form.get("expiry_date"), "Expiry date")

    key = get_storage().save(str(actor.tenant_id), data, safe_extension(file.filename))
    ev = Evidence(
        tenant_id=actor.tenant_id,
        rubric_item_id=item.id,
        evaluation_id=evaluation_id,
        object_key=key,
        filename=file.filename[:255],
        content_type=file.content_type,
        size_bytes=len(data),
        uploaded_by=actor.id,
        evidence_type=evidence_type,
        sensitivity=sensitivity,
        expiry_date=expiry,
        notes=form.get("notes"),
    )
    db.session.add(ev)
    db.session.flush()
    audit.record(actor, "upload_evidence", "evidence", ev.id,
                 {"filename": ev.filename, "size_bytes": len(data)})
    db.session.commit()
    return ev


def read(actor: User, ev: Evidence) -> bytes:
    try:
        data = get_storage().read(ev.object_key)
    except FileNotFoundError:
        raise NotFound("The file for this evidence record is missing from storage.")
    audit.record(actor, "download_evidence", "evidence", ev.id)
    db.session.commit()
    return data


def delete(actor: User, ev: Evidence) -> None:
    get_storage().delete(ev.object_key)
    audit.record(actor, "delete_evidence", "evidence", ev.id, {"filename": ev.filename})
    db.session.delete(ev)
    db.session.commit()
