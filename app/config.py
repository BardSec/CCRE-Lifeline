from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _csv(name: str) -> list[str]:
    return [v.strip().lower() for v in os.environ.get(name, "").split(",") if v.strip()]


class Config:
    # ── App ───────────────────────────────────────────────────────────────────
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "")
    DEBUG: bool = _bool("DEBUG", False)
    TESTING: bool = False

    # Set when running behind Cloudflare Tunnel / a reverse proxy. Enables
    # ProxyFix (so redirect URIs and client IPs are correct) and forces secure
    # cookies. Also means "deployed": the dev login is refused.
    BEHIND_PROXY: bool = _bool("BEHIND_PROXY", False)

    # ── Database ──────────────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI: str = os.environ.get("DATABASE_URL", "")
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # ── SSO — Microsoft Entra ID ──────────────────────────────────────────────
    AZURE_CLIENT_ID: str = os.environ.get("AZURE_CLIENT_ID", "")
    AZURE_CLIENT_SECRET: str = os.environ.get("AZURE_CLIENT_SECRET", "")
    # Your directory (tenant) ID, or "common" to accept any Microsoft tenant
    # (then ALLOWED_DOMAINS is what keeps outsiders out).
    AZURE_TENANT_ID: str = os.environ.get("AZURE_TENANT_ID", "")

    # ── Authorization ─────────────────────────────────────────────────────────
    # Emails that receive the admin role on login.
    ADMIN_EMAILS: list[str] = _csv("ADMIN_EMAILS")
    # Email domains allowed to sign in. Blank allows any account that
    # authenticates (admins in ADMIN_EMAILS are always allowed).
    ALLOWED_DOMAINS: list[str] = _csv("ALLOWED_DOMAINS")
    # Role assigned to new users not in ADMIN_EMAILS.
    DEFAULT_USER_ROLE: str = os.environ.get("DEFAULT_USER_ROLE", "viewer")

    # ── Evidence file storage ─────────────────────────────────────────────────
    STORAGE_BACKEND: str = os.environ.get("STORAGE_BACKEND", "local")
    EVIDENCE_DIR: str = os.environ.get("EVIDENCE_DIR", "/app/evidence")
    MAX_UPLOAD_BYTES: int = int(os.environ.get("MAX_UPLOAD_BYTES", 52_428_800))
    # Flask rejects larger request bodies with 413 before they are read.
    MAX_CONTENT_LENGTH: int = MAX_UPLOAD_BYTES + 1024 * 1024
    # Evidence is documentation (policies, audit reports, exports), so office
    # formats are allowed beyond the usual PDF/JPG/PNG.
    ALLOWED_CONTENT_TYPES: list[str] = [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/gif",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/csv",
    ]

    # ── Sessions / cookies ────────────────────────────────────────────────────
    SESSION_COOKIE_NAME = "rubricops"
    SESSION_COOKIE_SECURE: bool = _bool("COOKIE_SECURE", True) or BEHIND_PROXY
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8
    WTF_CSRF_TIME_LIMIT = None  # tied to the session instead

    # ── Rate limiting ─────────────────────────────────────────────────────────
    LOGIN_RATE_LIMIT: str = os.environ.get("LOGIN_RATE_LIMIT", "10 per minute")
    RATELIMIT_ENABLED = True

    # ── Background jobs ───────────────────────────────────────────────────────
    SCHEDULER_ENABLED: bool = _bool("SCHEDULER_ENABLED", True)

    # ── Seed ──────────────────────────────────────────────────────────────────
    SEED_TENANT_NAME: str = os.environ.get("SEED_TENANT_NAME", "Lakeside School District")

    @classmethod
    def sso_enabled(cls) -> bool:
        return bool(cls.AZURE_TENANT_ID and cls.AZURE_CLIENT_ID and cls.AZURE_CLIENT_SECRET)

    @classmethod
    def validate(cls) -> None:
        if not cls.SQLALCHEMY_DATABASE_URI:
            raise RuntimeError("Missing configuration: DATABASE_URL")
        if len(cls.SECRET_KEY) < 32 or cls.SECRET_KEY.startswith("CHANGE-ME"):
            raise RuntimeError("SECRET_KEY must be set to a random value of at least 32 characters.")
        if cls.DEFAULT_USER_ROLE not in ("viewer", "contributor", "evaluator"):
            raise RuntimeError("DEFAULT_USER_ROLE must be viewer, contributor, or evaluator.")
        if cls.STORAGE_BACKEND != "local":
            raise RuntimeError(f"Unknown STORAGE_BACKEND: {cls.STORAGE_BACKEND!r} (supported: local)")
        sso = ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET")
        missing = [k for k in sso if not getattr(cls, k)]
        if 0 < len(missing) < len(sso):
            # Half-configured SSO would silently fall back to the dev login.
            raise RuntimeError(f"SSO is partially configured; missing: {', '.join(missing)}")
        if missing and cls.BEHIND_PROXY:
            # The dev login takes any email with no password, so it must never
            # be reachable on a deployed instance.
            raise RuntimeError(
                "Refusing to start: BEHIND_PROXY is set but SSO is not configured, "
                "which would expose the password-less dev login."
            )


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "t" * 40
    AZURE_TENANT_ID = AZURE_CLIENT_ID = AZURE_CLIENT_SECRET = ""
    BEHIND_PROXY = False
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SCHEDULER_ENABLED = False
    ADMIN_EMAILS = ["admin@district.edu"]
    ALLOWED_DOMAINS = ["district.edu"]
    DEFAULT_USER_ROLE = "viewer"
    # Tests use their own database next to the app's (created if missing):
    # TEST_DATABASE_URL, else DATABASE_URL with "_test" appended to its name.
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL") or (
        os.environ["DATABASE_URL"] + "_test" if os.environ.get("DATABASE_URL")
        else "postgresql+psycopg2://rubricops:changeme@localhost:5440/rubricops_test"
    )
