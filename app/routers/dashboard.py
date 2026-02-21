from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import (
    Evaluation, EvaluationStatus, Evidence, Score, Task, TaskStatus, User
)

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tid = current_user.tenant_id

    # Counts
    total_evals = db.query(Evaluation).filter(Evaluation.tenant_id == tid).count()
    draft_evals = (
        db.query(Evaluation)
        .filter(Evaluation.tenant_id == tid, Evaluation.status == EvaluationStatus.draft)
        .count()
    )
    open_tasks = (
        db.query(Task)
        .filter(Task.tenant_id == tid, Task.status != TaskStatus.done)
        .count()
    )
    overdue_tasks = (
        db.query(Task)
        .filter(
            Task.tenant_id == tid,
            Task.status != TaskStatus.done,
            Task.due_date < datetime.utcnow(),
            Task.due_date.isnot(None),
        )
        .count()
    )

    stale_cutoff = datetime.utcnow() - timedelta(days=90)
    stale_evidence = (
        db.query(Evidence)
        .filter(Evidence.tenant_id == tid, Evidence.uploaded_at < stale_cutoff)
        .count()
    )

    expiring_cutoff = datetime.utcnow() + timedelta(days=30)
    expiring_evidence = (
        db.query(Evidence)
        .filter(
            Evidence.tenant_id == tid,
            Evidence.expiry_date.isnot(None),
            Evidence.expiry_date <= expiring_cutoff,
            Evidence.expiry_date >= datetime.utcnow(),
        )
        .count()
    )

    # Recent evaluations
    recent_evals = (
        db.query(Evaluation)
        .filter(Evaluation.tenant_id == tid)
        .order_by(Evaluation.created_at.desc())
        .limit(5)
        .all()
    )

    # My open tasks
    my_tasks = (
        db.query(Task)
        .filter(
            Task.tenant_id == tid,
            Task.owner_user_id == current_user.id,
            Task.status != TaskStatus.done,
        )
        .order_by(Task.due_date.asc().nullslast())
        .limit(10)
        .all()
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "total_evals": total_evals,
            "draft_evals": draft_evals,
            "open_tasks": open_tasks,
            "overdue_tasks": overdue_tasks,
            "stale_evidence": stale_evidence,
            "expiring_evidence": expiring_evidence,
            "recent_evals": recent_evals,
            "my_tasks": my_tasks,
        },
    )
