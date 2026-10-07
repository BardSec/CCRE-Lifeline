from __future__ import annotations

from flask import has_request_context, request

from app.extensions import db
from app.models import AuditLog, User


def record(
    actor: User,
    action: str,
    entity_type: str,
    entity_id: object | None = None,
    detail: dict | None = None,
) -> None:
    """Add an audit entry to the current session. The caller commits."""
    db.session.add(AuditLog(
        tenant_id=actor.tenant_id,
        actor_user_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        ip_address=request.remote_addr if has_request_context() else None,
        detail_json=detail,
    ))
