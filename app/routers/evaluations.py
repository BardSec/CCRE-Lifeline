from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import (
    audit,
    get_current_user,
    require_contributor_or_above,
    require_evaluator_or_above,
)
from app.database import get_db
from app.models import (
    Confidence,
    Evaluation,
    EvaluationStatus,
    Rubric,
    RubricDomain,
    RubricItem,
    Score,
    Task,
    TaskStatus,
    User,
    UserRole,
)
from app.services import csv_export, pdf_export

router = APIRouter(prefix="/evaluations", tags=["evaluations"])
templates = Jinja2Templates(directory="app/templates")


# ── List ───────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def list_evaluations(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    evals = (
        db.query(Evaluation)
        .filter(Evaluation.tenant_id == current_user.tenant_id)
        .order_by(Evaluation.created_at.desc())
        .all()
    )
    rubrics = db.query(Rubric).all()
    return templates.TemplateResponse(
        "evaluations/list.html",
        {"request": request, "current_user": current_user, "evaluations": evals, "rubrics": rubrics},
    )


# ── Create ─────────────────────────────────────────────────────────────────────

@router.post("", response_class=HTMLResponse)
async def create_evaluation(
    request: Request,
    title: str = Form(...),
    rubric_id: str = Form(...),
    period_start: str = Form(...),
    period_end: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_evaluator_or_above),
):
    rubric = db.query(Rubric).filter(Rubric.id == rubric_id).first()
    if not rubric:
        raise HTTPException(status_code=404, detail="Rubric not found")

    eval_obj = Evaluation(
        tenant_id=current_user.tenant_id,
        rubric_id=rubric.id,
        title=title,
        period_start=datetime.fromisoformat(period_start),
        period_end=datetime.fromisoformat(period_end),
        created_by=current_user.id,
    )
    db.add(eval_obj)
    db.flush()  # get eval_obj.id

    # Auto-populate Score rows for every rubric item (workflow A)
    all_items = (
        db.query(RubricItem)
        .join(RubricDomain)
        .filter(RubricDomain.rubric_id == rubric.id)
        .all()
    )
    for item in all_items:
        db.add(Score(evaluation_id=eval_obj.id, rubric_item_id=item.id))

    audit(db, actor=current_user, action="create_evaluation", entity_type="evaluation",
          entity_id=str(eval_obj.id), detail={"title": title})
    db.commit()

    return RedirectResponse(url=f"/evaluations/{eval_obj.id}", status_code=status.HTTP_302_FOUND)


# ── Detail ─────────────────────────────────────────────────────────────────────

@router.get("/{eval_id}", response_class=HTMLResponse)
async def evaluation_detail(
    eval_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    eval_obj = _get_eval(db, eval_id, current_user.tenant_id)

    # Load scores with items and domains
    scores = (
        db.query(Score)
        .join(RubricItem)
        .join(RubricDomain)
        .filter(Score.evaluation_id == eval_obj.id)
        .options(joinedload(Score.rubric_item).joinedload(RubricItem.domain))
        .order_by(RubricDomain.sort_order, RubricItem.sort_order)
        .all()
    )

    # Group scores by domain
    domains: dict = {}
    for score in scores:
        domain = score.rubric_item.domain
        domains.setdefault(domain.id, {"domain": domain, "scores": []})
        domains[domain.id]["scores"].append(score)

    # Compute per-domain averages
    domain_averages = {}
    for d_id, data in domains.items():
        scored = [s.maturity_level for s in data["scores"] if s.maturity_level > 0]
        domain_averages[d_id] = round(sum(scored) / len(scored), 1) if scored else None

    # Users for owner assignment
    users = db.query(User).filter(User.tenant_id == current_user.tenant_id, User.is_active == True).all()

    return templates.TemplateResponse(
        "evaluations/detail.html",
        {
            "request": request,
            "current_user": current_user,
            "eval": eval_obj,
            "domains": list(domains.values()),
            "domain_averages": domain_averages,
            "users": users,
            "Confidence": Confidence,
        },
    )


# ── Update score ───────────────────────────────────────────────────────────────

@router.post("/{eval_id}/scores/{score_id}", response_class=HTMLResponse)
async def update_score(
    eval_id: uuid.UUID,
    score_id: uuid.UUID,
    request: Request,
    maturity_level: int = Form(...),
    confidence: Optional[str] = Form(None),
    rationale: Optional[str] = Form(None),
    compensating_controls: Optional[str] = Form(None),
    owner_user_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_contributor_or_above),
):
    eval_obj = _get_eval(db, eval_id, current_user.tenant_id)
    if eval_obj.status == EvaluationStatus.final:
        raise HTTPException(status_code=400, detail="Cannot edit a finalized evaluation")

    score = db.query(Score).filter(
        Score.id == score_id, Score.evaluation_id == eval_obj.id
    ).first()
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")

    if not (0 <= maturity_level <= 5):
        raise HTTPException(status_code=400, detail="Maturity level must be 0–5")

    score.maturity_level = maturity_level
    score.confidence = Confidence(confidence) if confidence else None
    score.rationale = rationale
    score.compensating_controls = compensating_controls
    score.owner_user_id = uuid.UUID(owner_user_id) if owner_user_id else None
    score.updated_at = datetime.utcnow()

    audit(db, actor=current_user, action="update_score", entity_type="score",
          entity_id=str(score_id), detail={"maturity_level": maturity_level})
    db.commit()

    return RedirectResponse(url=f"/evaluations/{eval_id}", status_code=status.HTTP_302_FOUND)


# ── Finalize ───────────────────────────────────────────────────────────────────

@router.post("/{eval_id}/finalize")
async def finalize_evaluation(
    eval_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_evaluator_or_above),
):
    eval_obj = _get_eval(db, eval_id, current_user.tenant_id)
    eval_obj.status = EvaluationStatus.final
    audit(db, actor=current_user, action="finalize_evaluation", entity_type="evaluation",
          entity_id=str(eval_id))
    db.commit()
    return RedirectResponse(url=f"/evaluations/{eval_id}", status_code=status.HTTP_302_FOUND)


# ── Suggest & create tasks ─────────────────────────────────────────────────────

@router.post("/{eval_id}/suggest-tasks")
async def suggest_tasks(
    eval_id: uuid.UUID,
    target_level: int = Form(3),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_evaluator_or_above),
):
    eval_obj = _get_eval(db, eval_id, current_user.tenant_id)

    scores = (
        db.query(Score)
        .options(joinedload(Score.rubric_item))
        .filter(Score.evaluation_id == eval_obj.id, Score.maturity_level < target_level)
        .all()
    )

    created = 0
    for score in scores:
        # Avoid duplicate tasks
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
    return RedirectResponse(url=f"/evaluations/{eval_id}#tasks", status_code=status.HTTP_302_FOUND)


# ── Export PDF ─────────────────────────────────────────────────────────────────

@router.get("/{eval_id}/export/pdf")
async def export_pdf(
    eval_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    eval_obj = _get_eval(db, eval_id, current_user.tenant_id)
    buf = pdf_export.generate_evaluation_pdf(db, eval_obj, current_user)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="evaluation_{eval_id}.pdf"'},
    )


# ── Export CSV ─────────────────────────────────────────────────────────────────

@router.get("/{eval_id}/export/csv")
async def export_csv(
    eval_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    eval_obj = _get_eval(db, eval_id, current_user.tenant_id)
    buf = csv_export.generate_evaluation_csv(db, eval_obj)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="evaluation_{eval_id}.csv"'},
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_eval(db: Session, eval_id: uuid.UUID, tenant_id) -> Evaluation:
    obj = (
        db.query(Evaluation)
        .filter(Evaluation.id == eval_id, Evaluation.tenant_id == tenant_id)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return obj
