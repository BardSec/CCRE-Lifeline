"""Microsoft Entra ID sign-in (OIDC via Authlib), with a dev login when SSO is unset."""
from __future__ import annotations

import logging
import uuid

from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for
from flask_login import login_required, login_user, logout_user

from app.extensions import db, limiter, login_manager, oauth
from app.models import User
from app.services import users

log = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


def _login_limit() -> str:
    return current_app.config["LOGIN_RATE_LIMIT"]


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return None
    user = db.session.get(User, uid)
    # Re-checked on every request, so deactivating a user ends their session.
    return user if user and user.is_active else None


@auth_bp.route("/login")
def login():
    return render_template("login.html", sso=current_app.config_class.sso_enabled())


@auth_bp.route("/auth/start")
@limiter.limit(_login_limit)
def auth_start():
    if not current_app.config_class.sso_enabled():
        abort(404)
    redirect_uri = url_for("auth.callback", _external=True)
    return oauth.microsoft.authorize_redirect(redirect_uri, prompt="select_account")


@auth_bp.route("/auth/callback")
@limiter.limit(_login_limit)
def callback():
    if not current_app.config_class.sso_enabled():
        abort(404)
    try:
        token = oauth.microsoft.authorize_access_token()
    except Exception:
        log.warning("OIDC token exchange failed", exc_info=True)
        return _denied("Microsoft sign-in did not complete. Try again.")

    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or userinfo.get("preferred_username") or "").strip().lower()
    return _finish(email, userinfo.get("name"))


@auth_bp.route("/login/dev", methods=["POST"])
@limiter.limit(_login_limit)
def dev_login():
    # Only exists while SSO is unset, and Config.validate() refuses to start
    # with BEHIND_PROXY and no SSO, so this can't be reached when deployed.
    if current_app.config_class.sso_enabled():
        abort(404)
    email = (request.form.get("email") or "").strip().lower()
    return _finish(email, email.split("@")[0])


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/healthz")
@limiter.exempt
def healthz():
    return {"status": "ok"}


def _finish(email: str, name: str | None):
    try:
        users.check_allowed(email, current_app.config)
        user = users.record_login(email, name, current_app.config)
    except users.AccessDenied as e:
        log.warning("sign-in refused for %s: %s", email or "(no email)", e)
        return _denied(str(e))
    session.clear()  # drop anything set before sign-in (session fixation)
    session.permanent = True
    login_user(user)
    return redirect(url_for("dashboard.index"))


def _denied(message: str):
    session.clear()
    return render_template("login.html", sso=current_app.config_class.sso_enabled(), error=message), 403
