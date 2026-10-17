from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, object_session

from app.errors import api_error, forbidden
from app.models import ConstructionObject, Developer, District, Territory
from app.models.enums import ConstructionStatus, KeyStatus, TerritoryLevel, Zone
from app.scope import TerritoryScope


def get_object_in_scope(session: Session, scope: TerritoryScope, object_id: int) -> ConstructionObject:
    """Out-of-scope objects are reported as missing so their existence is not disclosed."""
    obj = session.get(ConstructionObject, object_id)
    if obj is None or not scope.contains(obj.territory_id):
        raise api_error(404, "object_not_found", "Объект не найден")
    return obj


def territory_today(session: Session, territory_id: int) -> date:
    """Today's date in the time zone of the territory (the risk engine reads dates the same way). The zone
    is looked up once per territory and session: lists call this for every row."""
    zones: dict[int, str] = session.info.setdefault("territory_timezones", {})
    if territory_id not in zones:
        zones[territory_id] = session.scalars(select(Territory.timezone).where(Territory.id == territory_id)).one()
    return datetime.now(ZoneInfo(zones[territory_id])).date()


def key_status_detail(obj: ConstructionObject, today: date | None = None) -> dict[str, int] | None:
    if obj.key_status is KeyStatus.stalled and obj.stalled_since is not None:
        if today is None:
            session = object_session(obj)
            today = territory_today(session, obj.territory_id) if session else datetime.now(UTC).date()
        return {"stalled_days": (today - obj.stalled_since).days}
    return None


def check_references(
    session: Session,
    scope: TerritoryScope,
    territory_id: int,
    district_id: int | None,
    developer_id: int | None,
) -> None:
    territory = session.get(Territory, territory_id)
    if territory is None or territory.level is not TerritoryLevel.city:
        raise api_error(422, "invalid_territory", "Объект должен относиться к городу")
    if not scope.contains(territory.id):
        raise forbidden("Территория вне вашей зоны ответственности")
    if district_id is not None:
        district = session.get(District, district_id)
        if district is None or district.territory_id != territory_id:
            raise api_error(422, "invalid_district", "Район не найден в выбранном городе")
    if developer_id is not None and session.get(Developer, developer_id) is None:
        raise api_error(422, "developer_not_found", "Застройщик не найден")


def apply_status_rules(session: Session, obj: ConstructionObject) -> None:
    """`stalled_since` follows the status: set to today (in the object's territory) on entering `stalled`,
    cleared on leaving it."""
    if obj.construction_status is ConstructionStatus.stalled:
        if obj.stalled_since is None:
            obj.stalled_since = territory_today(session, obj.territory_id)
    else:
        obj.stalled_since = None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def object_rows_stmt(
    scope: TerritoryScope,
    *,
    zone: Zone | None = None,
    district_id: int | None = None,
    territory_id: int | None = None,
    q: str | None = None,
) -> Select[ConstructionObject, str | None, str | None]:
    """Registry query shared by the objects list and the dashboard: (object, developer name, district name)."""
    stmt = (
        select(ConstructionObject, Developer.name, District.name)
        .outerjoin(Developer, Developer.id == ConstructionObject.developer_id)
        .outerjoin(District, District.id == ConstructionObject.district_id)
    )
    stmt = scope.restrict(stmt, ConstructionObject.territory_id)
    if zone is not None:
        stmt = stmt.where(ConstructionObject.zone == zone)
    if district_id is not None:
        stmt = stmt.where(ConstructionObject.district_id == district_id)
    if territory_id is not None:
        stmt = stmt.where(ConstructionObject.territory_id == territory_id)
    if q:
        pattern = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(
            or_(
                ConstructionObject.name.ilike(pattern),
                ConstructionObject.code.ilike(pattern),
                ConstructionObject.address.ilike(pattern),
                ConstructionObject.cadastral_number.ilike(pattern),
                func.array_to_string(ConstructionObject.aliases, " ").ilike(pattern),
                Developer.name.ilike(pattern),
                Developer.bin.ilike(pattern),
            )
        )
    return stmt
