from __future__ import annotations

import logging

from flask import Blueprint, abort, current_app, redirect, request, url_for
from flask_login import login_required, login_user, logout_user

from app import login_manager, oauth
from app.database import get_db
from app.models import AuditLog, Tenant, User, UserRole

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


# ── Flask-Login user loader ─────────────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    return get_db().query(User).filter(
        User.id == user_id,
        User.is_active == True,
    ).first()


# ── Routes ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/login")
def login():
    redirect_uri = url_for("auth.callback", _external=True)
    return oauth.microsoft.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/callback")
def callback():
    token = oauth.microsoft.authorize_access_token()
    userinfo = token.get("userinfo") or {}

    email = (userinfo.get("email") or userinfo.get("preferred_username") or "").lower().strip()
    name = userinfo.get("name") or email

    if not email:
        logger.warning("OIDC callback: no email in userinfo")
        abort(403)

    # ── Authorization: email or domain allow-list ──────────────────────────────
    domain = email.split("@")[-1] if "@" in email else ""
    admin_emails: list[str] = current_app.config.get("ADMIN_EMAILS", [])
    allowed_domains: list[str] = current_app.config.get("ALLOWED_DOMAINS", [])

    if email not in admin_emails and domain not in allowed_domains and allowed_domains:
        logger.warning("OIDC callback: unauthorized email %s", email)
        abort(403)

    db = get_db()

    # ── Tenant (single-tenant: use the first/only seeded tenant) ──────────────
    tenant: Tenant | None = db.query(Tenant).first()
    if not tenant:
        logger.error("OIDC callback: no tenant found — run `make seed` first")
        abort(500)

    # ── User provisioning ─────────────────────────────────────────────────────
    user: User | None = db.query(User).filter(
        User.tenant_id == tenant.id,
        User.email == email,
    ).first()

    if not user:
        role = UserRole.admin if email in admin_emails else UserRole(
            current_app.config.get("DEFAULT_USER_ROLE", "viewer")
        )
        user = User(
            tenant_id=tenant.id,
            email=email,
            name=name,
            role=role,
            is_active=True,
        )
        db.add(user)
        db.flush()
        logger.info("OIDC: provisioned new user %s with role %s", email, role)
    else:
        # Auto-promote to admin if added to ADMIN_EMAILS list after initial login.
        if email in admin_emails and user.role != UserRole.admin:
            user.role = UserRole.admin
            logger.info("OIDC: promoted %s to admin", email)

    _audit(db, user, "login", "user", str(user.id))
    db.commit()

    login_user(user)
    return redirect(url_for("dashboard.index"))


@auth_bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/healthz")
def healthz():
    return {"status": "ok"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _audit(db, actor: User, action: str, entity_type: str,
           entity_id: str | None = None, detail: dict | None = None) -> None:
    db.add(AuditLog(
        tenant_id=actor.tenant_id,
        actor_user_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=request.remote_addr,
        detail_json=detail,
    ))
