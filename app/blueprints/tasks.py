from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.helpers import audit, require_contributor_or_above
from app.database import get_db
from app.models import Evaluation, RubricItem, Task, TaskStatus, User

tasks_bp = Blueprint("tasks", __name__, url_prefix="/tasks")


@tasks_bp.route("")
@login_required
def list_tasks():
    db = get_db()
    status_filter = request.args.get("status_filter")
    q = db.query(Task).filter(Task.tenant_id == current_user.tenant_id)
    if status_filter:
        q = q.filter(Task.status == status_filter)
    tasks = q.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc()).all()
    users = db.query(User).filter(
        User.tenant_id == current_user.tenant_id, User.is_active == True
    ).all()
    return render_template(
        "tasks/list.html",
        tasks=tasks,
        users=users,
        TaskStatus=TaskStatus,
        status_filter=status_filter,
    )


@tasks_bp.route("/create", methods=["POST"])
@login_required
@require_contributor_or_above
def create_task():
    db = get_db()
    evaluation_id_str: Optional[str] = request.form.get("evaluation_id")
    rubric_item_id_str: Optional[str] = request.form.get("rubric_item_id")
    owner_id_str: Optional[str] = request.form.get("owner_user_id")
    due_date_str: Optional[str] = request.form.get("due_date")

    task = Task(
        tenant_id=current_user.tenant_id,
        title=request.form["title"],
        description=request.form.get("description"),
        evaluation_id=uuid.UUID(evaluation_id_str) if evaluation_id_str else None,
        rubric_item_id=uuid.UUID(rubric_item_id_str) if rubric_item_id_str else None,
        owner_user_id=uuid.UUID(owner_id_str) if owner_id_str else None,
        due_date=datetime.fromisoformat(due_date_str) if due_date_str else None,
        status=TaskStatus.open,
    )
    db.add(task)
    audit(db, actor=current_user, action="create_task", entity_type="task",
          detail={"title": task.title})
    db.commit()
    return redirect(url_for("tasks.list_tasks"))


@tasks_bp.route("/<uuid:task_id>/update", methods=["POST"])
@login_required
@require_contributor_or_above
def update_task(task_id: uuid.UUID):
    db = get_db()
    task = db.query(Task).filter(
        Task.id == task_id, Task.tenant_id == current_user.tenant_id
    ).first()
    if not task:
        abort(404)

    new_status = request.form["new_status"]
    owner_id_str: Optional[str] = request.form.get("owner_user_id")
    due_date_str: Optional[str] = request.form.get("due_date")

    task.status = TaskStatus(new_status)
    task.owner_user_id = uuid.UUID(owner_id_str) if owner_id_str else None
    task.due_date = datetime.fromisoformat(due_date_str) if due_date_str else None

    audit(db, actor=current_user, action="update_task", entity_type="task",
          entity_id=str(task_id), detail={"status": new_status})
    db.commit()
    return redirect(url_for("tasks.list_tasks"))
