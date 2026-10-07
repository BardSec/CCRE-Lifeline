"""Form-input parsing. Bad input raises BadRequest (400) instead of a 500."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TypeVar

from werkzeug.exceptions import BadRequest

E = TypeVar("E", bound=Enum)


def required(value: str | None, field: str) -> str:
    value = (value or "").strip()
    if not value:
        raise BadRequest(f"{field} is required.")
    return value


def optional_uuid(value: str | None, field: str) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        raise BadRequest(f"{field} is not a valid id.")


def optional_date(value: str | None, field: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise BadRequest(f"{field} is not a valid date.")


def required_date(value: str | None, field: str) -> datetime:
    parsed = optional_date(value, field)
    if parsed is None:
        raise BadRequest(f"{field} is required.")
    return parsed


def int_in_range(value: str | None, field: str, lo: int, hi: int, default: int | None = None) -> int:
    if value in (None, "") and default is not None:
        return default
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise BadRequest(f"{field} must be a number.")
    if not lo <= parsed <= hi:
        raise BadRequest(f"{field} must be between {lo} and {hi}.")
    return parsed


def enum_value(enum_cls: type[E], value: str | None, field: str) -> E:
    try:
        return enum_cls(value)
    except ValueError:
        raise BadRequest(f"{field} is not a valid choice.")
