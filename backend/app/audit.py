from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fastapi import Request
from geoalchemy2.elements import WKBElement
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.models import AppUser, AuditLog

_EXCLUDED_COLUMNS = {"password_hash", "tsa_token"}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, WKBElement):
        return None  # geometries are not stored in the audit trail; lat/lon are in the object itself
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def snapshot(entity: object) -> dict[str, Any]:
    """JSON-safe copy of an ORM entity's column values (secrets and geometries excluded)."""
    mapper = sa_inspect(entity).mapper  # type: ignore[union-attr]
    return {
        attr.key: _jsonable(getattr(entity, attr.key))
        for attr in mapper.column_attrs
        if attr.key not in _EXCLUDED_COLUMNS
    }


def client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def record(
    session: Session,
    user: AppUser | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    request: Request | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user.id if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=_jsonable(before),
        after=_jsonable(after),
        ip=client_ip(request),
    )
    session.add(entry)
    session.flush()
    return entry
