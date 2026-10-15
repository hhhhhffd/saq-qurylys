import logging

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import audit
from app.csv_import import (
    ImportResult,
    ImportRowError,
    RowError,
    parse_bool,
    parse_enum,
    parse_int,
    read_rows,
    require,
    require_date,
)
from app.models import AppUser, Complaint, ConstructionObject
from app.models.enums import ComplaintSource, ComplaintStatus
from app.modules.complaints.service import set_verified
from app.scope import TerritoryScope

logger = logging.getLogger(__name__)

REQUIRED = {"object_code", "received_at"}
COLUMNS = REQUIRED | {
    "source",
    "external_id",
    "is_collective",
    "signatories_count",
    "summary",
    "status",
    "confirmed_payments",
    "is_verified",
}


def _import_row(
    session: Session, scope: TerritoryScope, user: AppUser, row: dict[str, str | None], request: Request
) -> tuple[bool, int]:
    """Create or update one complaint. Returns (created, object id)."""
    object_code = require(row, "object_code")
    obj = session.scalar(select(ConstructionObject).where(ConstructionObject.code == object_code.upper()))
    if obj is None or not scope.contains(obj.territory_id):
        raise RowError(f"Объект с кодом «{object_code}» не найден или недоступен")

    received_at = require_date(row, "received_at")
    source = parse_enum(row.get("source"), "source", ComplaintSource) or ComplaintSource.eotinish
    status = parse_enum(row.get("status"), "status", ComplaintStatus)
    is_collective = parse_bool(row.get("is_collective"), "is_collective")
    confirmed_payments = parse_bool(row.get("confirmed_payments"), "confirmed_payments")
    is_verified = parse_bool(row.get("is_verified"), "is_verified")
    signatories = parse_int(row.get("signatories_count"), "signatories_count", 1, 100000)
    external_id = row.get("external_id")

    existing = (
        session.scalar(select(Complaint).where(Complaint.source == source, Complaint.external_id == external_id))
        if external_id is not None
        else None
    )
    if existing is not None and existing.object_id != obj.id:
        raise RowError(f"Обращение «{external_id}» уже привязано к другому объекту")

    complaint = existing or Complaint(object_id=obj.id, source=source, external_id=external_id)
    before = audit.snapshot(complaint) if existing else None
    complaint.received_at = received_at
    if row.get("summary") is not None:
        complaint.summary = row["summary"]
    if status is not None:
        complaint.status = status
    elif existing is None:
        complaint.status = ComplaintStatus.new
    if is_collective is not None:
        complaint.is_collective = is_collective
    elif existing is None:
        complaint.is_collective = False
    if confirmed_payments is not None:
        complaint.confirmed_payments = confirmed_payments
    elif existing is None:
        complaint.confirmed_payments = False
    if is_verified is not None:
        set_verified(complaint, is_verified, user)
    if signatories is not None:
        complaint.signatories_count = signatories
    elif existing is None:
        complaint.signatories_count = 1

    if existing is None:
        session.add(complaint)
    session.flush()
    action = "complaint.import_update" if existing else "complaint.import_create"
    audit.record(session, user, action, "complaint", complaint.id, before, audit.snapshot(complaint), request)
    return existing is None, obj.id


def import_complaints(
    session: Session, scope: TerritoryScope, user: AppUser, raw: bytes, request: Request
) -> tuple[ImportResult, set[int]]:
    """Import complaints from CSV; an existing (source, external_id) pair is updated, not duplicated."""
    result = ImportResult()
    changed_objects: set[int] = set()
    for row_number, row in read_rows(raw, REQUIRED, COLUMNS):
        try:
            with session.begin_nested():
                created, object_id = _import_row(session, scope, user, row, request)
        except RowError as exc:
            result.errors.append(ImportRowError(row=row_number, message=str(exc)))
            continue
        except DBAPIError:
            logger.exception("CSV import: database error in row %s", row_number)
            result.errors.append(ImportRowError(row=row_number, message="Не удалось сохранить строку"))
            continue
        changed_objects.add(object_id)
        if created:
            result.created += 1
        else:
            result.updated += 1
    return result, changed_objects
