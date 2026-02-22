from __future__ import annotations

import uuid
from typing import Optional

from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.helpers import audit, require_admin
from app.database import get_db
from app.models import AuditLog, Tenant, User, UserRole

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/users")
@login_required
@require_admin
def list_users():
    db = get_db()
    users = (
        db.query(User)
        .filter(User.tenant_id == current_user.tenant_id)
        .order_by(User.name)
        .all()
    )
    return render_template("admin/users.html", users=users, UserRole=UserRole)


@admin_bp.route("/users/<uuid:user_id>/update", methods=["POST"])
@login_required
@require_admin
def update_user(user_id: uuid.UUID):
    db = get_db()
    user = db.query(User).filter(
        User.id == user_id, User.tenant_id == current_user.tenant_id
    ).first()
    if not user:
        abort(404)
    if user.id == current_user.id:
        abort(400)

    role: Optional[str] = request.form.get("role")
    is_active_str: Optional[str] = request.form.get("is_active")

    if role:
        user.role = UserRole(role)
    if is_active_str is not None:
        user.is_active = is_active_str == "true"

    audit(db, actor=current_user, action="update_user", entity_type="user",
          entity_id=str(user_id), detail={"role": role, "is_active": is_active_str})
    db.commit()
    return redirect(url_for("admin.list_users"))


@admin_bp.route("/tenant")
@login_required
@require_admin
def tenant_settings():
    db = get_db()
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    return render_template("admin/tenant.html", tenant=tenant)


@admin_bp.route("/tenant", methods=["POST"])
@login_required
@require_admin
def update_tenant():
    db = get_db()
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    tenant.name = request.form["name"]
    tenant.timezone = request.form.get("timezone", "America/Chicago")
    tenant.stale_evidence_days = int(request.form.get("stale_evidence_days", 90))
    tenant.stale_policy_days = int(request.form.get("stale_policy_days", 365))
    audit(db, actor=current_user, action="update_tenant", entity_type="tenant",
          entity_id=str(tenant.id))
    db.commit()
    return redirect(url_for("admin.tenant_settings"))


@admin_bp.route("/audit-log")
@login_required
@require_admin
def audit_log():
    db = get_db()
    page = int(request.args.get("page", 1))
    per_page = 50
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.tenant_id == current_user.tenant_id)
        .order_by(AuditLog.timestamp.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    total = db.query(AuditLog).filter(
        AuditLog.tenant_id == current_user.tenant_id
    ).count()
    return render_template(
        "admin/audit_log.html",
        logs=logs,
        page=page,
        total=total,
        per_page=per_page,
    )
