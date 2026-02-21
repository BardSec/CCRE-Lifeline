from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import audit, require_admin
from app.auth.security import hash_password
from app.database import get_db
from app.models import AuditLog, Tenant, User, UserRole

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/users", response_class=HTMLResponse)
async def list_users(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    users = (
        db.query(User)
        .filter(User.tenant_id == current_user.tenant_id)
        .order_by(User.name)
        .all()
    )
    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "current_user": current_user, "users": users, "UserRole": UserRole},
    )


@router.post("/users")
async def create_user(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("viewer"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    existing = db.query(User).filter(
        User.tenant_id == current_user.tenant_id,
        User.email == email.lower().strip(),
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered in this tenant")

    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = User(
        tenant_id=current_user.tenant_id,
        email=email.lower().strip(),
        password_hash=hash_password(password),
        name=name,
        role=UserRole(role),
        is_active=True,
    )
    db.add(user)
    audit(db, actor=current_user, action="create_user", entity_type="user",
          detail={"email": email, "role": role})
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)


@router.post("/users/{user_id}/update")
async def update_user(
    user_id: uuid.UUID,
    role: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(
        User.id == user_id, User.tenant_id == current_user.tenant_id
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own account here")

    if role:
        user.role = UserRole(role)
    if is_active is not None:
        user.is_active = is_active == "true"

    audit(db, actor=current_user, action="update_user", entity_type="user",
          entity_id=str(user_id), detail={"role": role, "is_active": is_active})
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)


@router.get("/tenant", response_class=HTMLResponse)
async def tenant_settings(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    return templates.TemplateResponse(
        "admin/tenant.html",
        {"request": request, "current_user": current_user, "tenant": tenant},
    )


@router.post("/tenant")
async def update_tenant(
    name: str = Form(...),
    timezone: str = Form("America/Chicago"),
    stale_evidence_days: int = Form(90),
    stale_policy_days: int = Form(365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    tenant.name = name
    tenant.timezone = timezone
    tenant.stale_evidence_days = stale_evidence_days
    tenant.stale_policy_days = stale_policy_days
    audit(db, actor=current_user, action="update_tenant", entity_type="tenant",
          entity_id=str(tenant.id))
    db.commit()
    return RedirectResponse(url="/admin/tenant", status_code=status.HTTP_302_FOUND)


@router.get("/audit-log", response_class=HTMLResponse)
async def audit_log(
    request: Request,
    page: int = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    per_page = 50
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.tenant_id == current_user.tenant_id)
        .order_by(AuditLog.timestamp.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    total = db.query(AuditLog).filter(AuditLog.tenant_id == current_user.tenant_id).count()
    return templates.TemplateResponse(
        "admin/audit_log.html",
        {
            "request": request,
            "current_user": current_user,
            "logs": logs,
            "page": page,
            "total": total,
            "per_page": per_page,
        },
    )
