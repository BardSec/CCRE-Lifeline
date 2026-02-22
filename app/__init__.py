from __future__ import annotations

import logging

from authlib.integrations.flask_client import OAuth
from flask import Flask, redirect, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager

from app.config import Config
from app.database import close_db, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

login_manager = LoginManager()
oauth = OAuth()
limiter = Limiter(key_func=get_remote_address)


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)

    # ── Extensions ─────────────────────────────────────────────────────────────
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    oauth.init_app(app)
    limiter.init_app(app)

    # ── OIDC provider — Microsoft 365 ──────────────────────────────────────────
    oauth.register(
        name="microsoft",
        server_metadata_url=(
            f"https://login.microsoftonline.com/"
            f"{app.config['AZURE_TENANT_ID']}/v2.0/.well-known/openid-configuration"
        ),
        client_id=app.config["AZURE_CLIENT_ID"],
        client_secret=app.config["AZURE_CLIENT_SECRET"],
        client_kwargs={"scope": "openid email profile"},
    )

    # ── Database ───────────────────────────────────────────────────────────────
    init_db(app.config["DATABASE_URL"])
    app.teardown_appcontext(close_db)

    # ── Blueprints ─────────────────────────────────────────────────────────────
    from app.auth import auth_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.dashboard import dashboard_bp
    from app.blueprints.evaluations import evaluations_bp
    from app.blueprints.evidence import evidence_bp
    from app.blueprints.tasks import tasks_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(evaluations_bp)
    app.register_blueprint(evidence_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(admin_bp)

    # ── Scheduler ──────────────────────────────────────────────────────────────
    from app.jobs.scheduler import start_scheduler
    start_scheduler()

    return app
