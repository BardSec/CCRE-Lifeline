"""
Evidence file storage.

Files are always served back through the authenticated download route, never
by direct URL. Only the local backend exists today; an R2 backend would
implement the same three methods and be selected with STORAGE_BACKEND.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from flask import current_app

_SAFE_EXT = re.compile(r"^[a-z0-9]{1,10}$")


def safe_extension(filename: str) -> str:
    """Return a lowercase alphanumeric extension, or "bin".

    The extension comes from the client-supplied filename and ends up in the
    storage path, so anything other than plain alphanumerics (slashes, dots,
    "..") is discarded.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext if _SAFE_EXT.match(ext) else "bin"


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"Storage key escapes the evidence directory: {key!r}")
        return path

    def save(self, tenant_id: str, data: bytes, ext: str) -> str:
        """Write *data* under a tenant-scoped key and return the key."""
        key = f"{tenant_id}/evidence/{uuid.uuid4()}.{ext}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()


def get_storage() -> LocalStorage:
    # Config.validate() guarantees STORAGE_BACKEND is "local".
    return LocalStorage(current_app.config["EVIDENCE_DIR"])
