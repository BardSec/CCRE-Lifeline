from __future__ import annotations

import uuid

from werkzeug.exceptions import BadRequest, NotFound

from app.extensions import db
from app.models import AuditLog, Tenant, User, UserRole
from app.services import audit
from app.services.validation import enum_value, int_in_range, required

AUDIT_PAGE_SIZE = 50


def list_users(tenant_id: uuid.UUID) -> list[User]:
    return db.session.query(User).filter(User.tenant_id == tenant_id).order_by(User.name).all()


def update_user(actor: User, user_id: uuid.UUID, form) -> User:
    user = db.session.query(User).filter(User.id == user_id, User.tenant_id == actor.tenant_id).first()
    if user is None:
        raise NotFound()
    if user.id == actor.id:
        # Prevents an admin from demoting or deactivating themselves and
        # leaving the organization with no admin.
        raise BadRequest("You can't change your own role or status.")

    role = form.get("role")
    is_active = form.get("is_active")
    if role:
        user.role = enum_value(UserRole, role, "Role")
    if is_active is not None:
        user.is_active = is_active == "true"

    audit.record(actor, "update_user", "user", user.id, {"role": role, "is_active": is_active})
    db.session.commit()
    return user


def get_tenant(actor: User) -> Tenant:
    return db.session.get(Tenant, actor.tenant_id)


def update_tenant(actor: User, form) -> Tenant:
    tenant = get_tenant(actor)
    tenant.name = required(form.get("name"), "District name")
    tenant.timezone = form.get("timezone") or "America/Chicago"
    tenant.stale_evidence_days = int_in_range(
        form.get("stale_evidence_days"), "Stale evidence days", 1, 3650, default=90)
    tenant.stale_policy_days = int_in_range(
        form.get("stale_policy_days"), "Stale policy days", 1, 3650, default=365)
    audit.record(actor, "update_tenant", "tenant", tenant.id)
    db.session.commit()
    return tenant


def audit_page(tenant_id: uuid.UUID, page: int) -> tuple[list[AuditLog], int]:
    q = db.session.query(AuditLog).filter(AuditLog.tenant_id == tenant_id)
    logs = (
        q.order_by(AuditLog.timestamp.desc())
        .offset((page - 1) * AUDIT_PAGE_SIZE)
        .limit(AUDIT_PAGE_SIZE)
        .all()
    )
    return logs, q.count()
