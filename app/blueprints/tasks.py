from __future__ import annotations

import uuid

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.helpers import require_contributor_or_above
from app.models import TaskStatus
from app.services import evaluations, tasks

tasks_bp = Blueprint("tasks", __name__, url_prefix="/tasks")


@tasks_bp.route("")
@login_required
def list_tasks():
    status_filter = request.args.get("status_filter")
    return render_template(
        "tasks/list.html",
        tasks=tasks.list_for_tenant(current_user.tenant_id, status_filter),
        users=evaluations.active_users(current_user.tenant_id),
        TaskStatus=TaskStatus,
        status_filter=status_filter,
    )


@tasks_bp.route("/create", methods=["POST"])
@login_required
@require_contributor_or_above
def create_task():
    tasks.create(current_user, request.form)
    return redirect(url_for("tasks.list_tasks"))


@tasks_bp.route("/<uuid:task_id>/update", methods=["POST"])
@login_required
@require_contributor_or_above
def update_task(task_id: uuid.UUID):
    task = tasks.get_for_tenant(current_user.tenant_id, task_id)
    tasks.update(current_user, task, request.form)
    return redirect(url_for("tasks.list_tasks"))
