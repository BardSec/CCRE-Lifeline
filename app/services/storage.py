from __future__ import annotations

import uuid
from pathlib import Path

from flask import current_app


def _evidence_dir() -> Path:
    return Path(current_app.config["EVIDENCE_DIR"])


def save_file(tenant_id: str, data: bytes, ext: str) -> str:
    """Write *data* to a tenant-scoped path. Returns the object_key."""
    key = f"{tenant_id}/evidence/{uuid.uuid4()}.{ext}"
    path = _evidence_dir() / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return key


def read_file(object_key: str) -> bytes:
    path = _evidence_dir() / object_key
    if not path.exists():
        raise FileNotFoundError(object_key)
    return path.read_bytes()


def delete_file(object_key: str) -> None:
    path = _evidence_dir() / object_key
    if path.exists():
        path.unlink()
