from __future__ import annotations

import io
import uuid
from datetime import datetime
from typing import Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
)
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import audit, get_current_user, require_contributor_or_above
from app.config import get_settings
from app.database import get_db
from app.models import (
    Evaluation, Evidence, RubricItem, Sensitivity, User
)
from app.services.minio_client import get_minio_client

settings = get_settings()
router = APIRouter(prefix="/evidence", tags=["evidence"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def list_evidence(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ev_list = (
        db.query(Evidence)
        .filter(Evidence.tenant_id == current_user.tenant_id)
        .order_by(Evidence.uploaded_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "evidence/list.html",
        {"request": request, "current_user": current_user, "evidence_list": ev_list},
    )


@router.get("/upload", response_class=HTMLResponse)
async def upload_form(
    request: Request,
    rubric_item_id: Optional[str] = None,
    evaluation_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_contributor_or_above),
):
    items = db.query(RubricItem).all()
    evals = (
        db.query(Evaluation)
        .filter(Evaluation.tenant_id == current_user.tenant_id)
        .all()
    )
    return templates.TemplateResponse(
        "evidence/upload.html",
        {
            "request": request,
            "current_user": current_user,
            "rubric_items": items,
            "evaluations": evals,
            "selected_item_id": rubric_item_id,
            "selected_eval_id": evaluation_id,
            "Sensitivity": Sensitivity,
        },
    )


@router.post("/upload")
async def upload_evidence(
    request: Request,
    file: UploadFile = File(...),
    rubric_item_id: str = Form(...),
    evaluation_id: Optional[str] = Form(None),
    evidence_type: str = Form(...),
    sensitivity: str = Form("internal"),
    expiry_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_contributor_or_above),
):
    # Validate content type
    if file.content_type not in settings.ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{file.content_type}' is not allowed",
        )

    # Read and size-check
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.MAX_UPLOAD_BYTES // 1_048_576} MB limit",
        )

    # Validate rubric item exists
    item = db.query(RubricItem).filter(RubricItem.id == rubric_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Rubric item not found")

    # Validate evaluation belongs to tenant
    eval_id_uuid = None
    if evaluation_id:
        eval_obj = (
            db.query(Evaluation)
            .filter(Evaluation.id == evaluation_id, Evaluation.tenant_id == current_user.tenant_id)
            .first()
        )
        if not eval_obj:
            raise HTTPException(status_code=404, detail="Evaluation not found")
        eval_id_uuid = eval_obj.id

    # Build tenant-prefixed object key
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "bin"
    object_key = f"{current_user.tenant_id}/evidence/{uuid.uuid4()}.{ext}"

    # Upload to MinIO
    client = get_minio_client()
    client.put_object(
        settings.MINIO_BUCKET,
        object_key,
        io.BytesIO(data),
        length=len(data),
        content_type=file.content_type,
    )

    # Parse expiry
    expiry = datetime.fromisoformat(expiry_date) if expiry_date else None

    ev = Evidence(
        tenant_id=current_user.tenant_id,
        rubric_item_id=item.id,
        evaluation_id=eval_id_uuid,
        object_key=object_key,
        filename=file.filename,
        content_type=file.content_type,
        size_bytes=len(data),
        uploaded_by=current_user.id,
        evidence_type=evidence_type,
        sensitivity=Sensitivity(sensitivity),
        expiry_date=expiry,
        notes=notes,
    )
    db.add(ev)
    audit(db, actor=current_user, action="upload_evidence", entity_type="evidence",
          entity_id=object_key, detail={"filename": file.filename, "size_bytes": len(data)})
    db.commit()

    return RedirectResponse(url="/evidence", status_code=status.HTTP_302_FOUND)


@router.get("/{evidence_id}/download")
async def download_evidence(
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ev = (
        db.query(Evidence)
        .filter(Evidence.id == evidence_id, Evidence.tenant_id == current_user.tenant_id)
        .first()
    )
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")

    client = get_minio_client()
    try:
        response = client.get_object(settings.MINIO_BUCKET, ev.object_key)
        data = response.read()
    except Exception:
        raise HTTPException(status_code=404, detail="File not found in storage")

    audit(db, actor=current_user, action="download_evidence", entity_type="evidence",
          entity_id=str(evidence_id))
    db.commit()

    return StreamingResponse(
        io.BytesIO(data),
        media_type=ev.content_type,
        headers={"Content-Disposition": f'attachment; filename="{ev.filename}"'},
    )


@router.post("/{evidence_id}/delete")
async def delete_evidence(
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_contributor_or_above),
):
    ev = (
        db.query(Evidence)
        .filter(Evidence.id == evidence_id, Evidence.tenant_id == current_user.tenant_id)
        .first()
    )
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")

    # Remove from MinIO
    try:
        client = get_minio_client()
        client.remove_object(settings.MINIO_BUCKET, ev.object_key)
    except Exception:
        pass  # Log but don't block DB deletion

    audit(db, actor=current_user, action="delete_evidence", entity_type="evidence",
          entity_id=str(evidence_id), detail={"filename": ev.filename})
    db.delete(ev)
    db.commit()

    return RedirectResponse(url="/evidence", status_code=status.HTTP_302_FOUND)
