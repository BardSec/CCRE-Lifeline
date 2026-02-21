from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "RubricOps"
    DEBUG: bool = False

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+psycopg2://rubricops:changeme@db:5432/rubricops"

    # ── Auth / JWT ────────────────────────────────────────────────────────────
    SECRET_KEY: str = "CHANGE-ME-USE-A-STRONG-RANDOM-SECRET"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours

    # ── MinIO ─────────────────────────────────────────────────────────────────
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin123"
    MINIO_BUCKET: str = "rubricops-evidence"
    MINIO_SECURE: bool = False

    # ── Uploads ───────────────────────────────────────────────────────────────
    MAX_UPLOAD_BYTES: int = 52_428_800  # 50 MB
    ALLOWED_CONTENT_TYPES: List[str] = [
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

    # ── Rate limiting ─────────────────────────────────────────────────────────
    LOGIN_RATE_LIMIT: str = "10/minute"

    # ── Seed (optional, used by seed.py) ─────────────────────────────────────
    SEED_ADMIN_EMAIL: str = "admin@demo.example"
    SEED_ADMIN_PASSWORD: str = "Admin123!"
    SEED_TENANT_NAME: str = "Lakeside School District"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
