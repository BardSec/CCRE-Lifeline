from __future__ import annotations

import logging

import click
from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Config
from app.extensions import csrf, db, limiter, login_manager, migrate, oauth

log = logging.getLogger(__name__)


def create_app(config: type[Config] = Config) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config)
    app.config_class = config

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config.validate()

    if app.config["BEHIND_PROXY"]:
        # Cloudflare Tunnel terminates TLS; trust its X-Forwarded-* headers so
        # url_for(_external=True) builds https:// redirect URIs and the audit
        # log records the real client IP.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # ── Extensions ─────────────────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    oauth.init_app(app)

    if config.sso_enabled():
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
    else:
        log.warning("SSO is not configured: the password-less dev login is ON. "
                    "Local development only.")

    from app import models  # noqa: F401  (register tables for Flask-Migrate)

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

    _error_pages(app)
    _cli(app)

    # ── Scheduler ──────────────────────────────────────────────────────────────
    if app.config["SCHEDULER_ENABLED"]:
        from app.jobs.scheduler import start_scheduler
        start_scheduler(app)

    return app


def _error_pages(app: Flask) -> None:
    from flask_wtf.csrf import CSRFError

    messages = {
        400: "The request was invalid.",
        403: "You don't have permission to do that.",
        404: "That page doesn't exist.",
        413: "That file is too large.",
        415: "That file type isn't allowed.",
        429: "Too many attempts. Wait a minute and try again.",
    }

    def render(code: int, message: str, description: str | None = None):
        return render_template("error.html", code=code, message=message,
                               description=description), code

    def handler(code: int, message: str):
        def _handle(e):
            # Our own BadRequest messages ("Title is required.") are worth
            # showing; Werkzeug's generic defaults are not.
            default = type(e).description if hasattr(type(e), "description") else None
            detail = getattr(e, "description", None)
            return render(code, message, detail if detail != default else None)
        return _handle

    for code, message in messages.items():
        app.register_error_handler(code, handler(code, message))

    @app.errorhandler(CSRFError)
    def _csrf(e):
        return render(400, "Your form expired. Go back, reload the page, and try again.")


def _cli(app: Flask) -> None:
    @app.cli.command("seed")
    def seed_command():
        """Create the tenant and the default rubric if they don't exist."""
        from app.services.seed import seed
        for line in seed(app.config["SEED_TENANT_NAME"]):
            click.echo(line)
