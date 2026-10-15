import logging

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import audit
from app.csv_import import (
    ImportResult,
    ImportRowError,
    RowError,
    parse_date,
    parse_enum,
    parse_float,
    read_rows,
    require,
)
from app.geo import make_point
from app.models import AppUser, ConstructionObject, Developer, District, Territory
from app.models.enums import ConstructionStatus, TerritoryLevel
from app.modules.objects.service import apply_status_rules
from app.scope import TerritoryScope

logger = logging.getLogger(__name__)

REQUIRED = {"name", "territory_code"}
COLUMNS = REQUIRED | {
    "code",
    "district",
    "developer_bin",
    "developer_name",
    "aliases",
    "address",
    "cadastral_number",
    "land_purpose",
    "lat",
    "lon",
    "planned_completion",
    "forecast_completion",
    "construction_status",
    "stalled_since",
    "prior_violations",
}
ALIAS_SEPARATOR = "|"


def _resolve_developer(session: Session, row: dict[str, str | None]) -> Developer | None:
    bin_ = row.get("developer_bin")
    if bin_ is None:
        if row.get("developer_name"):
            raise RowError("Для застройщика укажите «developer_bin»")
        return None
    if not (len(bin_) == 12 and bin_.isdigit()):
        raise RowError("Поле «developer_bin»: БИН должен состоять из 12 цифр")
    developer = session.scalar(select(Developer).where(Developer.bin == bin_))
    if developer is None:
        name = row.get("developer_name")
        if name is None:
            raise RowError(f"Застройщик с БИН {bin_} не найден; для создания укажите «developer_name»")
        developer = Developer(bin=bin_, name=name)
        session.add(developer)
        session.flush()
    return developer


def _find_existing(
    session: Session, row: dict[str, str | None], territory_id: int, name: str
) -> ConstructionObject | None:
    code = row.get("code")
    if code is not None:
        obj = session.scalar(select(ConstructionObject).where(ConstructionObject.code == code))
        if obj is None:
            raise RowError(f"Объект с кодом {code} не найден")
        return obj
    cadastral = row.get("cadastral_number")
    if cadastral is not None:
        return session.scalar(select(ConstructionObject).where(ConstructionObject.cadastral_number == cadastral))
    return session.scalar(
        select(ConstructionObject).where(
            ConstructionObject.territory_id == territory_id,
            func.lower(ConstructionObject.name) == name.lower(),
            func.coalesce(func.lower(ConstructionObject.address), "") == (row.get("address") or "").lower(),
        )
    )


def _import_row(
    session: Session, scope: TerritoryScope, user: AppUser, row: dict[str, str | None], request: Request
) -> tuple[bool, int]:
    """Create or update one object. Returns (created, object id)."""
    name = require(row, "name")
    territory_code = require(row, "territory_code")
    territory = session.scalar(select(Territory).where(Territory.code == territory_code.lower()))
    if territory is None or territory.level is not TerritoryLevel.city or not scope.contains(territory.id):
        raise RowError(f"Город с кодом «{territory_code}» не найден или недоступен")

    district_id = None
    district_name = row.get("district")
    if district_name is not None:
        district_id = session.scalar(
            select(District.id).where(
                District.territory_id == territory.id, func.lower(District.name) == district_name.lower()
            )
        )
        if district_id is None:
            raise RowError(f"Район «{district_name}» не найден в городе {territory.name}")

    lat = parse_float(row.get("lat"), "lat", -90, 90)
    lon = parse_float(row.get("lon"), "lon", -180, 180)
    if (lat is None) != (lon is None):
        raise RowError("Координаты «lat» и «lon» указываются вместе")
    status = parse_enum(row.get("construction_status"), "construction_status", ConstructionStatus)
    values = {
        "planned_completion": parse_date(row.get("planned_completion"), "planned_completion"),
        "forecast_completion": parse_date(row.get("forecast_completion"), "forecast_completion"),
        "stalled_since": parse_date(row.get("stalled_since"), "stalled_since"),
    }
    developer = _resolve_developer(session, row)

    existing = _find_existing(session, row, territory.id, name)
    if existing is not None and not scope.contains(existing.territory_id):
        raise RowError("Объект находится вне вашей зоны ответственности")

    obj = existing or ConstructionObject(name=name, territory_id=territory.id)
    before = audit.snapshot(obj) if existing else None
    obj.name = name
    obj.territory_id = territory.id
    if district_id is not None:
        obj.district_id = district_id
    if developer is not None:
        obj.developer_id = developer.id
    for column in ("address", "cadastral_number", "land_purpose", "prior_violations"):
        if row.get(column) is not None:
            setattr(obj, column, row[column])
    aliases = row.get("aliases")
    if aliases is not None:
        obj.aliases = [alias.strip() for alias in aliases.split(ALIAS_SEPARATOR) if alias.strip()]
    for column, value in values.items():
        if value is not None:
            setattr(obj, column, value)
    if lat is not None:
        obj.location = make_point(lat, lon)
    if status is not None:
        obj.construction_status = status
    elif existing is None:
        obj.construction_status = ConstructionStatus.active
    apply_status_rules(obj)

    if existing is None:
        session.add(obj)
    session.flush()
    session.refresh(obj)
    action = "object.import_update" if existing else "object.import_create"
    audit.record(session, user, action, "object", obj.id, before, audit.snapshot(obj), request)
    return existing is None, obj.id


def import_objects(
    session: Session, scope: TerritoryScope, user: AppUser, raw: bytes, request: Request
) -> tuple[ImportResult, list[int]]:
    """Import objects from CSV. Each row runs in its own savepoint so a bad row never blocks the others."""
    result = ImportResult()
    changed: list[int] = []
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
        changed.append(object_id)
        if created:
            result.created += 1
        else:
            result.updated += 1
    return result, changed
