from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import audit, get_current_user, require_contributor_or_above
from app.database import get_db
from app.models import Evaluation, RubricItem, Task, TaskStatus, User

router = APIRouter(prefix="/tasks", tags=["tasks"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def list_tasks(
    request: Request,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Task).filter(Task.tenant_id == current_user.tenant_id)
    if status_filter:
        q = q.filter(Task.status == status_filter)
    tasks = q.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc()).all()
    users = db.query(User).filter(User.tenant_id == current_user.tenant_id, User.is_active == True).all()
    return templates.TemplateResponse(
        "tasks/list.html",
        {
            "request": request,
            "current_user": current_user,
            "tasks": tasks,
            "users": users,
            "TaskStatus": TaskStatus,
            "status_filter": status_filter,
        },
    )


@router.post("/{task_id}/update")
async def update_task(
    task_id: uuid.UUID,
    new_status: str = Form(...),
    owner_user_id: Optional[str] = Form(None),
    due_date: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_contributor_or_above),
):
    task = db.query(Task).filter(
        Task.id == task_id, Task.tenant_id == current_user.tenant_id
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = TaskStatus(new_status)
    task.owner_user_id = uuid.UUID(owner_user_id) if owner_user_id else None
    task.due_date = datetime.fromisoformat(due_date) if due_date else None

    audit(db, actor=current_user, action="update_task", entity_type="task",
          entity_id=str(task_id), detail={"status": new_status})
    db.commit()
    return RedirectResponse(url="/tasks", status_code=status.HTTP_302_FOUND)


@router.post("/create")
async def create_task(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    evaluation_id: Optional[str] = Form(None),
    rubric_item_id: Optional[str] = Form(None),
    owner_user_id: Optional[str] = Form(None),
    due_date: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_contributor_or_above),
):
    task = Task(
        tenant_id=current_user.tenant_id,
        title=title,
        description=description,
        evaluation_id=uuid.UUID(evaluation_id) if evaluation_id else None,
        rubric_item_id=uuid.UUID(rubric_item_id) if rubric_item_id else None,
        owner_user_id=uuid.UUID(owner_user_id) if owner_user_id else None,
        due_date=datetime.fromisoformat(due_date) if due_date else None,
        status=TaskStatus.open,
    )
    db.add(task)
    audit(db, actor=current_user, action="create_task", entity_type="task",
          detail={"title": title})
    db.commit()
    return RedirectResponse(url="/tasks", status_code=status.HTTP_302_FOUND)
