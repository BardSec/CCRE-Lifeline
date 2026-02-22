from __future__ import annotations

from functools import wraps
from typing import Optional

from flask import abort, request
from flask_login import current_user
from sqlalchemy.orm import Session

from app.models import AuditLog, User, UserRole


def require_roles(*roles: UserRole):
    """Decorator factory: abort 403 if the current user's role is not in *roles*."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


require_admin = require_roles(UserRole.admin)
require_evaluator_or_above = require_roles(UserRole.admin, UserRole.evaluator)
require_contributor_or_above = require_roles(
    UserRole.admin, UserRole.evaluator, UserRole.contributor
)


def audit(
    db: Session,
    *,
    actor: User,
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    detail: Optional[dict] = None,
) -> None:
    db.add(AuditLog(
        tenant_id=actor.tenant_id,
        actor_user_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        ip_address=request.remote_addr,
        detail_json=detail,
    ))
