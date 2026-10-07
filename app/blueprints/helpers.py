from __future__ import annotations

from functools import wraps

from flask import abort
from flask_login import current_user

from app.models import UserRole


def role_required(*roles: UserRole):
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


require_admin = role_required(UserRole.admin)
require_evaluator_or_above = role_required(UserRole.admin, UserRole.evaluator)
require_contributor_or_above = role_required(
    UserRole.admin, UserRole.evaluator, UserRole.contributor
)
