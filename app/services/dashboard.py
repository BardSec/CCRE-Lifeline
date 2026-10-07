from __future__ import annotations

from datetime import datetime, timedelta

from app.extensions import db
from app.models import Evaluation, EvaluationStatus, Evidence, Task, TaskStatus, Tenant, User


def summary(user: User) -> dict:
    """Counts and lists for the dashboard, scoped to the user's tenant."""
    tenant: Tenant = user.tenant
    tid = tenant.id
    now = datetime.utcnow()
    q = db.session.query

    open_tasks = q(Task).filter(Task.tenant_id == tid, Task.status != TaskStatus.done)

    return {
        "total_evals": q(Evaluation).filter(Evaluation.tenant_id == tid).count(),
        "draft_evals": q(Evaluation).filter(
            Evaluation.tenant_id == tid, Evaluation.status == EvaluationStatus.draft,
        ).count(),
        "open_tasks": open_tasks.count(),
        "overdue_tasks": open_tasks.filter(Task.due_date.isnot(None), Task.due_date < now).count(),
        # Uses the tenant's configured threshold, same as the weekly job.
        "stale_evidence": q(Evidence).filter(
            Evidence.tenant_id == tid,
            Evidence.uploaded_at < now - timedelta(days=tenant.stale_evidence_days or 90),
        ).count(),
        "expiring_evidence": q(Evidence).filter(
            Evidence.tenant_id == tid,
            Evidence.expiry_date.isnot(None),
            Evidence.expiry_date >= now,
            Evidence.expiry_date <= now + timedelta(days=30),
        ).count(),
        "recent_evals": q(Evaluation).filter(Evaluation.tenant_id == tid)
            .order_by(Evaluation.created_at.desc()).limit(5).all(),
        "my_tasks": open_tasks.filter(Task.owner_user_id == user.id)
            .order_by(Task.due_date.asc().nullslast()).limit(10).all(),
    }
