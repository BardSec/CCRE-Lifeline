from __future__ import annotations

import uuid

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.helpers import require_admin
from app.models import UserRole
from app.services import admin
from app.services.validation import int_in_range

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/users")
@login_required
@require_admin
def list_users():
    return render_template("admin/users.html", users=admin.list_users(current_user.tenant_id),
                           UserRole=UserRole)


@admin_bp.route("/users/<uuid:user_id>/update", methods=["POST"])
@login_required
@require_admin
def update_user(user_id: uuid.UUID):
    admin.update_user(current_user, user_id, request.form)
    return redirect(url_for("admin.list_users"))


@admin_bp.route("/tenant")
@login_required
@require_admin
def tenant_settings():
    return render_template("admin/tenant.html", tenant=admin.get_tenant(current_user))


@admin_bp.route("/tenant", methods=["POST"])
@login_required
@require_admin
def update_tenant():
    admin.update_tenant(current_user, request.form)
    return redirect(url_for("admin.tenant_settings"))


@admin_bp.route("/audit-log")
@login_required
@require_admin
def audit_log():
    page = int_in_range(request.args.get("page"), "Page", 1, 100_000, default=1)
    logs, total = admin.audit_page(current_user.tenant_id, page)
    return render_template("admin/audit_log.html", logs=logs, page=page, total=total,
                           per_page=admin.AUDIT_PAGE_SIZE)
