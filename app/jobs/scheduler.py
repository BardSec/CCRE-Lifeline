"""
Background job scheduler using APScheduler.

APScheduler is chosen over Celery for the MVP because:
- Single-instance deployment (Docker Compose, one web container).
- No additional broker service (Redis) required, reducing infrastructure complexity.
- Weekly notification cadence is trivially handled in-process.
- If horizontal scaling or more complex queuing is needed in the future,
  migrate to Celery + Redis by replacing this module.

Jobs run inside the same process as the web app. Each Gunicorn worker starts
its own scheduler, so with 2 workers every warning is logged twice. Harmless
while the jobs only log; fix before they send notifications.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from functools import wraps

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask

from app.extensions import db
from app.models import Evidence, Task, TaskStatus, Tenant

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_app: Flask | None = None


# ── Job implementations ────────────────────────────────────────────────────────

def check_stale_evidence() -> None:
    """
    Flag evidence older than tenant.stale_evidence_days (default 90) or
    policies older than tenant.stale_policy_days (default 365).
    For MVP: log warnings. Future: send email/in-app notifications.
    """
    try:
        tenants = db.session.query(Tenant).all()
        for tenant in tenants:
            stale_cutoff = datetime.utcnow() - timedelta(days=tenant.stale_evidence_days)
            policy_cutoff = datetime.utcnow() - timedelta(days=tenant.stale_policy_days)

            stale = (
                db.session.query(Evidence)
                .filter(
                    Evidence.tenant_id == tenant.id,
                    Evidence.uploaded_at < stale_cutoff,
                )
                .count()
            )
            stale_policies = (
                db.session.query(Evidence)
                .filter(
                    Evidence.tenant_id == tenant.id,
                    Evidence.evidence_type == "policy",
                    Evidence.uploaded_at < policy_cutoff,
                )
                .count()
            )

            if stale:
                logger.warning(
                    "[STALE EVIDENCE] Tenant=%s | %d evidence file(s) older than %d days",
                    tenant.name, stale, tenant.stale_evidence_days,
                )
            if stale_policies:
                logger.warning(
                    "[STALE POLICY] Tenant=%s | %d policy file(s) older than %d days",
                    tenant.name, stale_policies, tenant.stale_policy_days,
                )
    except Exception:
        logger.exception("check_stale_evidence failed")


def check_expiring_evidence() -> None:
    """
    Warn about evidence expiring within the next 30 days.
    For MVP: log warnings. Future: send email/in-app notifications.
    """
    try:
        now = datetime.utcnow()
        window = now + timedelta(days=30)
        expiring = (
            db.session.query(Evidence)
            .filter(
                Evidence.expiry_date.isnot(None),
                Evidence.expiry_date >= now,
                Evidence.expiry_date <= window,
            )
            .all()
        )
        for ev in expiring:
            days_left = (ev.expiry_date - now).days
            logger.warning(
                "[EXPIRING EVIDENCE] id=%s filename=%s expires_in=%d days tenant=%s",
                ev.id, ev.filename, days_left, ev.tenant_id,
            )
    except Exception:
        logger.exception("check_expiring_evidence failed")


def check_overdue_tasks() -> None:
    """
    Warn about tasks that are past their due date.
    For MVP: log warnings. Future: send email/in-app notifications.
    """
    try:
        overdue = (
            db.session.query(Task)
            .filter(
                Task.status != TaskStatus.done,
                Task.due_date < datetime.utcnow(),
                Task.due_date.isnot(None),
            )
            .all()
        )
        for task in overdue:
            logger.warning(
                "[OVERDUE TASK] id=%s title=%r due=%s tenant=%s",
                task.id, task.title, task.due_date.date(), task.tenant_id,
            )
    except Exception:
        logger.exception("check_overdue_tasks failed")


# ── Lifecycle ──────────────────────────────────────────────────────────────────

def _in_app_context(job):
    @wraps(job)
    def run():
        with _app.app_context():
            job()
    return run


def start_scheduler(app: Flask) -> None:
    global _scheduler, _app
    _app = app
    if _scheduler and _scheduler.running:
        return  # Already started (e.g. Flask reloader double-imports)
    _scheduler = BackgroundScheduler(timezone="UTC")

    # Run every Monday at 07:00 UTC
    _scheduler.add_job(
        _in_app_context(check_stale_evidence),
        CronTrigger(day_of_week="mon", hour=7, minute=0),
        id="check_stale_evidence",
        replace_existing=True,
    )
    _scheduler.add_job(
        _in_app_context(check_expiring_evidence),
        CronTrigger(day_of_week="mon", hour=7, minute=5),
        id="check_expiring_evidence",
        replace_existing=True,
    )
    _scheduler.add_job(
        _in_app_context(check_overdue_tasks),
        CronTrigger(day_of_week="mon", hour=7, minute=10),
        id="check_overdue_tasks",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("APScheduler started — weekly evidence/task checks scheduled.")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")
