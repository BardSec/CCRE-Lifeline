from __future__ import annotations

import uuid

from werkzeug.exceptions import BadRequest, NotFound

from app.extensions import db
from app.models import RubricItem, Task, TaskStatus, User
from app.services import audit, evaluations
from app.services.validation import enum_value, optional_date, optional_uuid, required


def list_for_tenant(tenant_id: uuid.UUID, status: str | None = None) -> list[Task]:
    q = db.session.query(Task).filter(Task.tenant_id == tenant_id)
    if status:
        q = q.filter(Task.status == enum_value(TaskStatus, status, "Status"))
    return q.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc()).all()


def get_for_tenant(tenant_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    task = db.session.query(Task).filter(Task.id == task_id, Task.tenant_id == tenant_id).first()
    if task is None:
        raise NotFound()
    return task


def _owner(actor: User, form) -> uuid.UUID | None:
    owner_id = optional_uuid(form.get("owner_user_id"), "Owner")
    if owner_id is not None:
        exists = db.session.query(User.id).filter(
            User.id == owner_id, User.tenant_id == actor.tenant_id,
        ).first()
        if not exists:
            raise BadRequest("Owner is not a user in this organization.")
    return owner_id


def create(actor: User, form) -> Task:
    evaluation_id = optional_uuid(form.get("evaluation_id"), "Evaluation")
    if evaluation_id is not None:
        evaluations.get_for_tenant(actor.tenant_id, evaluation_id)

    rubric_item_id = optional_uuid(form.get("rubric_item_id"), "Rubric item")
    if rubric_item_id is not None and db.session.get(RubricItem, rubric_item_id) is None:
        raise BadRequest("Unknown rubric item.")

    task = Task(
        tenant_id=actor.tenant_id,
        title=required(form.get("title"), "Title"),
        description=form.get("description"),
        evaluation_id=evaluation_id,
        rubric_item_id=rubric_item_id,
        owner_user_id=_owner(actor, form),
        due_date=optional_date(form.get("due_date"), "Due date"),
        status=TaskStatus.open,
    )
    db.session.add(task)
    db.session.flush()
    audit.record(actor, "create_task", "task", task.id, {"title": task.title})
    db.session.commit()
    return task


def update(actor: User, task: Task, form) -> Task:
    task.status = enum_value(TaskStatus, form.get("new_status"), "Status")
    task.owner_user_id = _owner(actor, form)
    task.due_date = optional_date(form.get("due_date"), "Due date")
    audit.record(actor, "update_task", "task", task.id, {"status": task.status.value})
    db.session.commit()
    return task
