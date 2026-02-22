from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.database import get_db
from app.models import Evaluation, EvaluationStatus, Evidence, Task, TaskStatus

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    db = get_db()
    tid = current_user.tenant_id

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

    recent_evals = (
        db.query(Evaluation)
        .filter(Evaluation.tenant_id == tid)
        .order_by(Evaluation.created_at.desc())
        .limit(5)
        .all()
    )

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

    return render_template(
        "dashboard.html",
        total_evals=total_evals,
        draft_evals=draft_evals,
        open_tasks=open_tasks,
        overdue_tasks=overdue_tasks,
        stale_evidence=stale_evidence,
        expiring_evidence=expiring_evidence,
        recent_evals=recent_evals,
        my_tasks=my_tasks,
    )
