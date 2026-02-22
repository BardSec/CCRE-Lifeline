from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── App ───────────────────────────────────────────────────────────────────
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "CHANGE-ME-USE-A-STRONG-RANDOM-SECRET")
    DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg2://rubricops:changeme@db:5432/rubricops",
    )

    # ── OIDC — Microsoft 365 ──────────────────────────────────────────────────
    AZURE_CLIENT_ID: str = os.environ.get("AZURE_CLIENT_ID", "")
    AZURE_CLIENT_SECRET: str = os.environ.get("AZURE_CLIENT_SECRET", "")
    # Use "common" to accept any Microsoft tenant, or set to your tenant ID.
    AZURE_TENANT_ID: str = os.environ.get("AZURE_TENANT_ID", "common")

    # ── Authorization ─────────────────────────────────────────────────────────
    # Comma-separated list of emails that receive the admin role on first login.
    ADMIN_EMAILS: list[str] = [
        e.strip().lower()
        for e in os.environ.get("ADMIN_EMAILS", "").split(",")
        if e.strip()
    ]
    # Comma-separated email domains allowed to log in (e.g. "district.edu").
    # Leave blank to allow any Microsoft account that authenticates successfully.
    ALLOWED_DOMAINS: list[str] = [
        d.strip().lower()
        for d in os.environ.get("ALLOWED_DOMAINS", "").split(",")
        if d.strip()
    ]
    # Default role assigned to new users not in ADMIN_EMAILS.
    DEFAULT_USER_ROLE: str = os.environ.get("DEFAULT_USER_ROLE", "viewer")

    # ── Evidence file storage (local volume) ──────────────────────────────────
    EVIDENCE_DIR: str = os.environ.get("EVIDENCE_DIR", "/app/evidence")
    MAX_UPLOAD_BYTES: int = int(os.environ.get("MAX_UPLOAD_BYTES", 52_428_800))
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

    # ── Cookie security ───────────────────────────────────────────────────────
    SESSION_COOKIE_SECURE: bool = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"

    # ── Rate limiting ─────────────────────────────────────────────────────────
    LOGIN_RATE_LIMIT: str = os.environ.get("LOGIN_RATE_LIMIT", "10 per minute")

    # ── Seed ──────────────────────────────────────────────────────────────────
    SEED_TENANT_NAME: str = os.environ.get("SEED_TENANT_NAME", "Lakeside School District")
