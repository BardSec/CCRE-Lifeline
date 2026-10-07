from __future__ import annotations

import logging

from app.extensions import db
from app.models import Tenant, User, UserRole
from app.services import audit

log = logging.getLogger(__name__)


class AccessDenied(Exception):
    pass


def check_allowed(email: str, config) -> None:
    """Raise AccessDenied unless *email* may sign in.

    Admins in ADMIN_EMAILS are always allowed. Otherwise, when ALLOWED_DOMAINS
    is set the email's domain must be on it; when it is blank, any account the
    identity provider authenticated is allowed.
    """
    if not email or "@" not in email:
        raise AccessDenied("No email address was returned for this account.")
    if email in config["ADMIN_EMAILS"]:
        return
    allowed = config["ALLOWED_DOMAINS"]
    if allowed and email.rsplit("@", 1)[1] not in allowed:
        raise AccessDenied("This account's domain is not allowed to sign in.")


def record_login(email: str, name: str | None, config) -> User:
    """Find or create the user for a successful sign-in, then audit it.

    This is a single-organization deployment: every user belongs to the one
    tenant created by `flask seed`.
    """
    tenant = db.session.query(Tenant).order_by(Tenant.created_at).first()
    if tenant is None:
        raise RuntimeError("No tenant exists. Run `flask seed`.")

    is_admin = email in config["ADMIN_EMAILS"]
    user = db.session.query(User).filter_by(tenant_id=tenant.id, email=email).first()

    if user is None:
        role = UserRole.admin if is_admin else UserRole(config["DEFAULT_USER_ROLE"])
        user = User(tenant_id=tenant.id, email=email, name=name or email, role=role, is_active=True)
        db.session.add(user)
        db.session.flush()
        log.info("provisioned new user %s with role %s", email, role.value)
    elif is_admin and user.role != UserRole.admin:
        # Added to ADMIN_EMAILS after their first sign-in.
        user.role = UserRole.admin
        log.info("promoted %s to admin", email)

    if not user.is_active:
        db.session.commit()
        raise AccessDenied("This account has been deactivated. Contact your administrator.")

    audit.record(user, "login", "user", user.id)
    db.session.commit()
    return user
