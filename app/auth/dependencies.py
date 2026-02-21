from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.security import COOKIE_NAME, decode_token
from app.database import get_db
from app.models import AuditLog, User, UserRole


def _get_current_user(
    db: Session,
    token: Optional[str],
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session payload")

    user = db.query(User).filter(User.id == uuid.UUID(user_id), User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> User:
    return _get_current_user(db, token)


def require_roles(*roles: UserRole):
    """Dependency factory: allow only users with specified roles."""
    def _inner(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not permitted for this action",
            )
        return current_user
    return _inner


require_admin = require_roles(UserRole.admin)
require_evaluator_or_above = require_roles(UserRole.admin, UserRole.evaluator)
require_contributor_or_above = require_roles(UserRole.admin, UserRole.evaluator, UserRole.contributor)


def audit(
    db: Session,
    *,
    actor: User,
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    detail: Optional[dict] = None,
) -> None:
    """Write an audit log entry."""
    log = AuditLog(
        tenant_id=actor.tenant_id,
        actor_user_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        ip_address=ip_address,
        detail_json=detail,
    )
    db.add(log)
    # Caller is responsible for db.commit()
