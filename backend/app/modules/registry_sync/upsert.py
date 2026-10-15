"""Writing registry records into the database. Shared by the pilot import and the sync.

Rules that both rely on:
- an existing object is only completed (empty fields are filled), never overwritten: people edit objects;
- a document checked by a person (`checked_by`) is left alone;
- documents are matched by number, so a repeated run updates instead of duplicating.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app import audit
from app.geo import make_point
from app.models import ConstructionObject, Developer, District, Document, Territory
from app.models.enums import CheckSource, CheckStatus, ConstructionStatus, DocType
from app.modules.registry_sync.records import RegistryRecord

# Registry coordinates are accepted when they lie this close to the point given by another source.
COORDINATE_TOLERANCE_M = 500
# A point farther than this from the city centre is a data entry error (the registry has one in the pilot data).
CITY_RADIUS_M = 30_000
# Two registry records of the same developer this close to each other describe the same object.
SAME_SITE_M = 150
# The same name this close is the same object even when no number links the two sources.
SAME_NAME_RADIUS_M = 2_000

PERMIT_DOC_TYPES = (DocType.dsu_permit, DocType.guarantee)
_BIN = re.compile(r"[0-9]{12}")
_NAME_NOISE = re.compile(r"\b(?:жк|мжк|жилой комплекс|клубный дом)\b|[\"«»'()]")
_EARTH_RADIUS_M = 6_371_000


@dataclass
class Changes:
    """What a run changed; `object_ids` are the objects to rescore."""

    objects_created: int = 0
    objects_updated: int = 0
    documents_created: int = 0
    documents_updated: int = 0
    documents_refreshed: int = 0
    documents_unconfirmed: int = 0
    object_ids: set[int] = field(default_factory=set)

    def merge(self, other: "Changes") -> None:
        self.objects_created += other.objects_created
        self.objects_updated += other.objects_updated
        self.documents_created += other.documents_created
        self.documents_updated += other.documents_updated
        self.documents_refreshed += other.documents_refreshed
        self.documents_unconfirmed += other.documents_unconfirmed
        self.object_ids |= other.object_ids


def local_today(territory: Territory) -> date:
    return datetime.now(ZoneInfo(territory.timezone)).date()


def construction_status_on(started_at: date | None, today: date) -> ConstructionStatus:
    """Work not started yet when the registry puts its start in the future."""
    return (
        ConstructionStatus.not_started if started_at is not None and started_at > today else ConstructionStatus.active
    )


def normalize_name(name: str) -> str:
    return " ".join(_NAME_NOISE.sub(" ", name.casefold().replace("ё", "е")).split())


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def plausible_location(session: Session, territory: Territory, lat: float | None, lon: float | None) -> bool:
    """A point within the city area. The registry sometimes carries a point from another part of the country."""
    if lat is None or lon is None:
        return False
    distance = session.scalar(
        select(func.ST_DistanceSphere(Territory.center, make_point(lat, lon))).where(Territory.id == territory.id)
    )
    return distance is None or distance <= CITY_RADIUS_M  # no centre recorded: nothing to compare with


# --- finding existing rows -------------------------------------------------------------------------------------


def _live_objects(territory_id: int) -> Select[ConstructionObject]:
    """Real objects of the city: demo objects are never matched with registry data."""
    return select(ConstructionObject).where(
        ConstructionObject.territory_id == territory_id, ConstructionObject.is_demo.is_(False)
    )


def find_object_by_records(
    session: Session, territory_id: int, records: list[RegistryRecord]
) -> ConstructionObject | None:
    """By a document number the registry gave, then by cadastral number, then by developer and site."""
    base = _live_objects(territory_id)
    for record in records:
        if record.number:
            obj = session.scalar(
                base.join(Document, Document.object_id == ConstructionObject.id)
                .where(Document.number == record.number, Document.doc_type == record.doc_type)
                .order_by(ConstructionObject.id)
                .limit(1)
            )
            if obj is not None:
                return obj
    for record in records:
        if record.cadastral_number:
            obj = session.scalar(
                base.where(func.replace(ConstructionObject.cadastral_number, ":", "-") == record.cadastral_number)
                .order_by(ConstructionObject.id)
                .limit(1)
            )
            if obj is not None:
                return obj
    for record in records:
        if record.developer_bin and record.lat is not None and record.lon is not None:
            obj = session.scalar(
                base.join(Developer, Developer.id == ConstructionObject.developer_id)
                .where(
                    Developer.bin == record.developer_bin,
                    func.ST_DistanceSphere(ConstructionObject.location, make_point(record.lat, record.lon))
                    <= SAME_SITE_M,
                )
                .order_by(ConstructionObject.id)
                .limit(1)
            )
            if obj is not None:
                return obj
    return None


def find_object_by_name(
    session: Session, territory_id: int, names: list[str], lat: float | None, lon: float | None
) -> ConstructionObject | None:
    wanted = {normalize_name(name) for name in names} - {""}
    # Columns only: the check needs no entity, and one row with an unreadable value must not stop the import.
    candidates = session.execute(
        select(
            ConstructionObject.id,
            ConstructionObject.name,
            ConstructionObject.aliases,
            ConstructionObject.lat,
            ConstructionObject.lon,
        )
        .where(ConstructionObject.territory_id == territory_id, ConstructionObject.is_demo.is_(False))
        .order_by(ConstructionObject.id)
    )
    for object_id, name, aliases, obj_lat, obj_lon in candidates:
        if not wanted & {normalize_name(value) for value in (name, *aliases)}:
            continue
        near = (
            obj_lat is None
            or obj_lon is None
            or lat is None
            or lon is None
            or distance_m(obj_lat, obj_lon, lat, lon) <= SAME_NAME_RADIUS_M
        )
        if near:
            return session.get(ConstructionObject, object_id)
    return None


def find_registry_object(session: Session, territory_id: int, record: RegistryRecord) -> ConstructionObject | None:
    return find_object_by_records(session, territory_id, [record]) or find_object_by_name(
        session, territory_id, [record.object_name], record.lat, record.lon
    )


# --- objects ---------------------------------------------------------------------------------------------------


def ensure_developer(session: Session, record: RegistryRecord) -> Developer | None:
    """The registry names the legal entity by BIN. An existing developer only gets its empty fields filled."""
    if record.developer_bin is None or _BIN.fullmatch(record.developer_bin) is None or record.developer_name is None:
        return None
    developer = session.scalar(select(Developer).where(Developer.bin == record.developer_bin))
    if developer is None:
        developer = Developer(
            bin=record.developer_bin,
            name=record.developer_name[:255],
            authorized_company=record.authorized_company[:255] if record.authorized_company else None,
        )
        session.add(developer)
        session.flush()
        session.refresh(developer)
        audit.record(session, None, "developer.create", "developer", developer.id, None, audit.snapshot(developer))
    elif developer.authorized_company is None and record.authorized_company:
        before = audit.snapshot(developer)
        developer.authorized_company = record.authorized_company[:255]
        session.flush()
        session.refresh(developer)
        audit.record(session, None, "developer.update", "developer", developer.id, before, audit.snapshot(developer))
    return developer


def assign_district(session: Session, obj: ConstructionObject) -> None:
    """Point in polygon (PostGIS ST_Contains); the smallest district wins where polygons overlap.

    Nothing in the core does this when an object is created, so imports do it themselves. An object outside every
    district polygon keeps no district.
    """
    if obj.district_id is not None:
        return
    district = (
        select(District.id)
        .where(
            District.territory_id == ConstructionObject.territory_id,
            func.ST_Contains(District.boundary, ConstructionObject.location),
        )
        .order_by(func.ST_Area(District.boundary), District.id)
        .limit(1)
        .scalar_subquery()
    )
    session.execute(
        update(ConstructionObject)
        .where(ConstructionObject.id == obj.id, ConstructionObject.location.is_not(None))
        .values(district_id=district)
        .execution_options(synchronize_session=False)
    )
    session.refresh(obj, ["district_id"])


@dataclass(frozen=True)
class ObjectFacts:
    """What the sources say about an object."""

    aliases: list[str]
    developer: Developer | None
    address: str | None
    cadastral_number: str | None
    lat: float | None
    lon: float | None
    planned_completion: date | None


def create_object(
    session: Session,
    *,
    territory_id: int,
    name: str,
    facts: ObjectFacts,
    construction_status: ConstructionStatus,
    changes: Changes,
) -> ConstructionObject:
    obj = ConstructionObject(
        territory_id=territory_id,
        developer_id=facts.developer.id if facts.developer else None,
        name=name[:255],
        aliases=facts.aliases,
        address=facts.address[:500] if facts.address else None,
        cadastral_number=facts.cadastral_number[:64] if facts.cadastral_number else None,
        location=make_point(facts.lat, facts.lon),
        planned_completion=facts.planned_completion,
        forecast_completion=facts.planned_completion,
        construction_status=construction_status,
        is_demo=False,
    )
    session.add(obj)
    session.flush()
    session.refresh(obj)
    assign_district(session, obj)
    audit.record(session, None, "object.create", "object", obj.id, None, audit.snapshot(obj))
    changes.objects_created += 1
    changes.object_ids.add(obj.id)
    return obj


def complete_object(session: Session, obj: ConstructionObject, facts: ObjectFacts, changes: Changes) -> None:
    """Fill what the object lacks; nothing a person may have entered is replaced."""
    before = audit.snapshot(obj)
    if obj.developer_id is None and facts.developer is not None:
        obj.developer_id = facts.developer.id
    if obj.address is None and facts.address:
        obj.address = facts.address[:500]
    if obj.cadastral_number is None and facts.cadastral_number:
        obj.cadastral_number = facts.cadastral_number[:64]
    if obj.lat is None and facts.lat is not None and facts.lon is not None:
        obj.location = make_point(facts.lat, facts.lon)
    if obj.planned_completion is None and facts.planned_completion is not None:
        obj.planned_completion = facts.planned_completion
        if obj.forecast_completion is None:
            obj.forecast_completion = facts.planned_completion
    known = {normalize_name(value) for value in (obj.name, *obj.aliases)}
    new_aliases = {normalize_name(alias): alias for alias in facts.aliases if normalize_name(alias) not in known}
    if new_aliases:
        obj.aliases = [*obj.aliases, *new_aliases.values()]
    session.flush()
    session.refresh(obj)
    assign_district(session, obj)
    after = audit.snapshot(obj)
    if after != before:
        audit.record(session, None, "object.update", "object", obj.id, before, after)
        changes.objects_updated += 1
        changes.object_ids.add(obj.id)


# --- documents -------------------------------------------------------------------------------------------------


def _find_document(session: Session, obj: ConstructionObject, record: RegistryRecord) -> Document | None:
    if record.number:
        document = session.scalar(
            select(Document)
            .where(Document.object_id == obj.id, Document.doc_type == record.doc_type, Document.number == record.number)
            .order_by(Document.id)
            .limit(1)
        )
        if document is not None:
            return document
    # A placeholder made while the object was not in the registry becomes the registry document.
    return session.scalar(
        select(Document)
        .where(
            Document.object_id == obj.id,
            Document.doc_type.in_(PERMIT_DOC_TYPES),
            Document.number.is_(None),
            Document.check_status == CheckStatus.checking,
            Document.check_source == CheckSource.housing_portal,
            Document.checked_by.is_(None),
        )
        .order_by(Document.id)
        .limit(1)
    )


def registry_note(record: RegistryRecord, *extra: str) -> str:
    parts = [
        f"{record.basis}.",
        f"Реестр объектов долевого строительства АО «КЖК» (homeportal.kz), запись № {record.registry_id}: "
        f"{record.detail_url}.",
    ]
    if record.bank:
        parts.append(f"Банк: {record.bank}.")
    if record.cadastral_number:
        parts.append(f"Кадастровый номер по реестру: {record.cadastral_number}.")
    return " ".join([*parts, *extra])


def upsert_registry_document(
    session: Session,
    obj: ConstructionObject,
    record: RegistryRecord,
    *,
    checked_at: datetime,
    note: str,
    changes: Changes,
) -> Document:
    """Create or update the document of a registry record: confirmed by the portal when its basis is a known one."""
    status = CheckStatus.confirmed if record.basis_is_known else CheckStatus.checking
    confirmed_at = checked_at if status is CheckStatus.confirmed else None
    document = _find_document(session, obj, record)
    if document is None:
        document = Document(
            object_id=obj.id,
            doc_type=record.doc_type,
            number=record.number,
            issued_at=record.issued_at,
            issuer=record.issuer,
            check_status=status,
            checked_at=confirmed_at,
            check_source=CheckSource.housing_portal,
            note=note,
        )
        session.add(document)
        session.flush()
        session.refresh(document)
        audit.record(session, None, "document.create", "document", document.id, None, audit.snapshot(document))
        changes.documents_created += 1
        changes.object_ids.add(obj.id)
        return document
    if document.checked_by is not None:
        return document  # a person decided; the registry does not overrule them

    before = audit.snapshot(document)
    was_placeholder = document.number is None
    if was_placeholder:
        document.doc_type = record.doc_type
        document.number = record.number
        document.note = note
    if document.issued_at is None:
        document.issued_at = record.issued_at
    if document.issuer is None:
        document.issuer = record.issuer
    document.check_status = status
    document.check_source = CheckSource.housing_portal
    refreshed = confirmed_at is not None and (document.checked_at is None or document.checked_at < confirmed_at)
    if refreshed:
        document.checked_at = confirmed_at
    elif confirmed_at is None:
        document.checked_at = None
    session.flush()
    session.refresh(document)
    after = audit.snapshot(document)
    substantive = {key for key in after if after[key] != before[key]} - {"checked_at", "updated_at"}
    if substantive:
        audit.record(session, None, "document.update", "document", document.id, before, after)
        changes.documents_updated += 1
        changes.object_ids.add(obj.id)
    elif refreshed:
        changes.documents_refreshed += 1
    return document
