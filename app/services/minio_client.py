from __future__ import annotations

from functools import lru_cache

from minio import Minio

from app.config import get_settings


@lru_cache(maxsize=1)
def get_minio_client() -> Minio:
    settings = get_settings()
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )
