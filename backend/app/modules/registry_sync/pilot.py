"""Import of the public pilot snapshot (app/seed_data/pilot): real objects of Ust-Kamenogorsk under construction.

The snapshot is untrusted third-party data collected on one day. Only facts from it are stored: no complaints,
no advertisements and no judgement about an object. The zone of every object is calculated by the risk module
from what is stored here.

What is imported (docs/OPEN_QUESTIONS.md items 11-13):
- every krisha.kz object (`objects`);
- every registry record that no krisha.kz object claims reliably, except records the portal counts as completed
  (commissioning date in the past);
- a registry match is reliable unless the snapshot itself says "не подтверждено" and the registry document number
  is not one of the numbers krisha.kz shows for the object.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.models import ConstructionObject, Document, Territory
from app.models.enums import CheckSource, CheckStatus
from app.modules.registry_sync.records import (
    RegistryRecord,
    clean_text,
    from_snapshot,
    parse_coordinates,
    parse_date,
)
from app.modules.registry_sync.upsert import (
    COORDINATE_TOLERANCE_M,
    PERMIT_DOC_TYPES,
    Changes,
    ObjectFacts,
    complete_object,
    construction_status_on,
    create_object,
    distance_m,
    ensure_developer,
    find_object_by_name,
    find_object_by_records,
    find_registry_object,
    local_today,
    normalize_name,
    plausible_location,
    registry_note,
    upsert_registry_document,
)

PILOT_FILE = Path(__file__).resolve().parents[2] / "seed_data" / "pilot" / "ust-kamenogorsk-public-2026-10-13.json"

_NOT_CONFIRMED = "не подтвержд"


@dataclass
class PilotResult:
    changes: Changes
    krisha_objects: int = 0
    registry_only_objects: int = 0
    skipped_completed: list[str] = field(default_factory=list)
    without_district: int = 0


@dataclass(frozen=True)
class _Match:
    record: RegistryRecord
    distance_m: float | None
    basis: str | None


def _reliable_matches(item: dict[str, Any]) -> tuple[list[_Match], list[_Match]]:
    """(matches to trust, matches the snapshot itself calls unconfirmed and krisha.kz does not back up)."""
    shown = " ".join(item.get("documents_displayed_on_source") or [])
    point = parse_coordinates(item.get("lat"), item.get("lon"))
    reliable: list[_Match] = []
    unresolved: list[_Match] = []
    for raw in item.get("homeportal_registry_matches") or []:
        record = from_snapshot(raw)
        distance = raw.get("coord_distance_m")
        if distance is None and point and record.lat is not None and record.lon is not None:
            distance = distance_m(point[0], point[1], record.lat, record.lon)
        match = _Match(record, distance, clean_text(raw.get("match_basis")))
        doubtful = _NOT_CONFIRMED in (match.basis or "").casefold()
        backed_up = record.number is not None and record.number in shown
        (unresolved if doubtful and not backed_up else reliable).append(match)
    return reliable, unresolved


def _placeholder_note(item: dict[str, Any], unresolved: list[_Match], collected_at: datetime) -> str:
    day = collected_at.date().isoformat()
    parts = [
        f"требуется ручная сверка: в выгрузке реестра КЖК от {day} не найден.",
        f"Сведения об объекте: krisha.kz ({item['source_url']}), снято {day}; самодекларация площадки, не проверено.",
    ]
    if developer := clean_text(item.get("developer_name")):
        parts.append(f"Застройщик по krisha.kz: {developer} (поле площадки, может быть брендом, а не юрлицом).")
    for legal in item.get("developer_legal_names_mentioned") or []:
        parts.append(f"Юрлицо в публичных источниках: {legal['name']} — {legal['role']}.")
    if shown := item.get("documents_displayed_on_source"):
        parts.append(f"На krisha.kz указано: {'; '.join(shown)} (по реестру не подтверждено).")
    for match in unresolved:
        record = match.record
        parts.append(
            f"Возможная запись реестра № {record.registry_id} «{record.object_name}» ({record.number}), "
            f"сопоставление не подтверждено: {match.basis}."
        )
    if item.get("developer_bin"):
        source = str(item.get("developer_bin_source"))
        reason = (
            "запись реестра не сопоставлена с объектом надёжно"
            if "homeportal" in source
            else "не подтверждён официальным реестром"
        )
        parts.append(f"БИН {item['developer_bin']} (источник: {source}) не внесён в карточку застройщика: {reason}.")
    return " ".join(parts)


def _import_krisha_object(
    session: Session,
    territory: Territory,
    item: dict[str, Any],
    *,
    collected_at: datetime,
    today: date,
    changes: Changes,
) -> None:
    reliable, unresolved = _reliable_matches(item)
    records = [match.record for match in reliable]
    name = clean_text(item["name"])
    if name is None:
        raise ValueError(f"object {item.get('krisha_complex_id')} has no name")
    krisha_point = parse_coordinates(item.get("lat"), item.get("lon"))
    krisha_lat, krisha_lon = krisha_point if krisha_point else (None, None)

    obj = find_object_by_records(session, territory.id, records) if records else None
    if obj is None:
        obj = find_object_by_name(session, territory.id, [name], krisha_lat, krisha_lon)

    ranked = sorted(reliable, key=lambda m: m.distance_m if m.distance_m is not None else float("inf"))
    primary = ranked[0] if ranked else None
    registry_point_accepted = (
        primary is not None
        and primary.distance_m is not None
        and primary.distance_m <= COORDINATE_TOLERANCE_M
        and plausible_location(session, territory, primary.record.lat, primary.record.lon)
    )
    # The registry is the official source for position and address, unless the snapshot flags a large mismatch.
    if primary is not None and registry_point_accepted:
        lat, lon, address = primary.record.lat, primary.record.lon, primary.record.address
    else:
        lat, lon, address = krisha_lat, krisha_lon, clean_text(item.get("address"))
    commissioning = [r.commissioning_at for r in records if r.commissioning_at is not None]
    started = [r.started_at for r in records if r.started_at is not None]
    facts = ObjectFacts(
        aliases=[r.object_name for r in records if normalize_name(r.object_name) != normalize_name(name)],
        developer=ensure_developer(session, primary.record) if primary else None,
        address=address,
        cadastral_number=next((m.record.cadastral_number for m in ranked if m.record.cadastral_number), None),
        lat=lat,
        lon=lon,
        planned_completion=max(commissioning)
        if commissioning
        else parse_date(item.get("planned_completion_quarter_end")),
    )
    if obj is None:
        obj = create_object(
            session,
            territory_id=territory.id,
            name=name,
            facts=facts,
            construction_status=construction_status_on(min(started, default=None), today),
            changes=changes,
        )
    else:
        complete_object(session, obj, facts, changes)

    krisha_url = f"Карточка ЖК на krisha.kz: {item['source_url']} (снято {collected_at.date().isoformat()})."
    for match in reliable:
        extra = [krisha_url]
        if match.basis:
            extra.append(f"Сопоставление с krisha.kz: {match.basis}.")
        if match.distance_m is not None and match.distance_m > COORDINATE_TOLERANCE_M:
            extra.append(
                f"Координаты и адрес записи реестра ({match.record.address}) отстоят от krisha.kz "
                f"на ~{round(match.distance_m)} м; положение объекта оставлено по krisha.kz."
            )
        upsert_registry_document(
            session,
            obj,
            match.record,
            checked_at=collected_at,
            note=registry_note(match.record, *extra),
            changes=changes,
        )

    if not reliable and not _has_permit_document(session, obj):
        document = Document(
            object_id=obj.id,
            doc_type=PERMIT_DOC_TYPES[0],
            check_status=CheckStatus.checking,
            check_source=CheckSource.housing_portal,
            note=_placeholder_note(item, unresolved, collected_at),
        )
        session.add(document)
        session.flush()
        session.refresh(document)
        audit.record(session, None, "document.create", "document", document.id, None, audit.snapshot(document))
        changes.documents_created += 1
        changes.object_ids.add(obj.id)


def _has_permit_document(session: Session, obj: ConstructionObject) -> bool:
    return (
        session.scalar(
            select(Document.id).where(Document.object_id == obj.id, Document.doc_type.in_(PERMIT_DOC_TYPES)).limit(1)
        )
        is not None
    )


def _import_registry_only(
    session: Session,
    territory: Territory,
    raw: dict[str, Any],
    doubtful: tuple[str, _Match] | None,
    *,
    collected_at: datetime,
    today: date,
    result: PilotResult,
) -> None:
    record = from_snapshot(raw)
    obj = find_registry_object(session, territory.id, record)
    if obj is None and record.is_completed(today):
        result.skipped_completed.append(f"{record.registry_id} {record.object_name}")
        return
    accepted = plausible_location(session, territory, record.lat, record.lon)
    facts = ObjectFacts(
        aliases=[],
        developer=ensure_developer(session, record),
        address=record.address,
        cadastral_number=record.cadastral_number,
        lat=record.lat if accepted else None,
        lon=record.lon if accepted else None,
        planned_completion=record.commissioning_at,
    )
    if obj is None:
        obj = create_object(
            session,
            territory_id=territory.id,
            name=record.object_name,
            facts=facts,
            construction_status=construction_status_on(record.started_at, today),
            changes=result.changes,
        )
        result.registry_only_objects += 1
    else:
        complete_object(session, obj, facts, result.changes)

    extra: list[str] = []
    if not accepted and record.lat is not None:
        extra.append(
            f"Координаты в реестре ({record.lat}, {record.lon}) вне города и признаны ошибочными: положение не задано."
        )
    if krisha_note := clean_text(raw.get("krisha_note")):
        extra.append(f"По выгрузке krisha.kz: {krisha_note}.")
    if doubtful is not None:
        krisha_name, match = doubtful
        extra.append(
            f"Возможное соответствие: {krisha_name} на krisha.kz — сопоставление не подтверждено: {match.basis}."
        )
    upsert_registry_document(
        session,
        obj,
        record,
        checked_at=collected_at,
        note=registry_note(record, f"Снимок реестра от {collected_at.date().isoformat()}.", *extra),
        changes=result.changes,
    )


def import_pilot(session: Session, path: Path = PILOT_FILE, territory_code: str = "ust-kamenogorsk") -> PilotResult:
    """Load the snapshot. Safe to repeat: objects and documents are found again and only completed or refreshed."""
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    territory = session.scalar(select(Territory).where(Territory.code == territory_code))
    if territory is None:
        raise ValueError(f"unknown territory {territory_code!r}; run `python -m app.seed` first")
    collected = parse_date(snapshot.get("meta", {}).get("collected_at"))
    if collected is None:
        raise ValueError("pilot snapshot has no meta.collected_at")
    collected_at = datetime.combine(collected, time.min, tzinfo=ZoneInfo(territory.timezone))
    today = local_today(territory)

    result = PilotResult(changes=Changes())
    claimed_ids: set[int] = set()
    doubtful_by_registry_id: dict[int, tuple[str, _Match]] = {}
    for item in snapshot["objects"]:
        reliable, unresolved = _reliable_matches(item)
        claimed_ids.update(match.record.registry_id for match in reliable)
        for match in unresolved:
            doubtful_by_registry_id[match.record.registry_id] = (item["name"], match)
        _import_krisha_object(session, territory, item, collected_at=collected_at, today=today, changes=result.changes)
        result.krisha_objects += 1

    for raw in snapshot["homeportal_registry_objects_vko"]:
        if int(raw["registry_id"]) in claimed_ids:
            continue
        _import_registry_only(
            session,
            territory,
            raw,
            doubtful_by_registry_id.get(int(raw["registry_id"])),
            collected_at=collected_at,
            today=today,
            result=result,
        )

    result.without_district = (
        session.scalar(
            select(func.count())
            .select_from(ConstructionObject)
            .where(
                ConstructionObject.is_demo.is_(False),
                ConstructionObject.location.is_not(None),
                ConstructionObject.district_id.is_(None),
            )
        )
        or 0
    )
    return result
