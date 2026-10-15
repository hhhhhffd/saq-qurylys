"""Sync of the housing portal registry: `POST getobjects`, then `GET objects-detail/<id>` for every record.

Per record: find or create the object, upsert its document (confirmed by the portal), keep the raw answer as
evidence of the check. A document that the registry no longer lists is set back to `checking` for a manual check;
it is never marked `not_found` automatically, because absence from an undocumented API proves little.
"""

import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit, storage
from app.events import objects_changed
from app.models import AppSetting, ConstructionObject, Document, Territory
from app.models.enums import CheckSource, CheckStatus, EvidenceKind, TerritoryLevel
from app.modules.registry_sync.client import HomeportalClient
from app.modules.registry_sync.records import RegistryFormatError, RegistryRecord
from app.modules.registry_sync.schemas import SyncResult
from app.modules.registry_sync.upsert import (
    Changes,
    ObjectFacts,
    complete_object,
    construction_status_on,
    create_object,
    ensure_developer,
    find_registry_object,
    local_today,
    plausible_location,
    registry_note,
    upsert_registry_document,
)
from app.storage import EvidenceLink

logger = logging.getLogger(__name__)

LAST_SYNC_KEY = "homeportal_last_sync"
REGION_ID_VKO = 16
# Writers of registry data take this lock per record, so two runs at once (a scheduled one and a manual one) cannot
# both create the same new object.
_ADVISORY_LOCK_KEY = 7_201_610_013


def _sync_record(
    session: Session,
    territory: Territory,
    record: RegistryRecord,
    raw: bytes,
    now: datetime,
    changes: Changes,
) -> bool:
    """False when the record was skipped: unknown to SAQ and already completed according to the portal."""
    session.execute(select(func.pg_advisory_xact_lock(_ADVISORY_LOCK_KEY)))
    today = local_today(territory)
    obj = find_registry_object(session, territory.id, record)
    if obj is None and record.is_completed(today):
        return False
    located = plausible_location(session, territory, record.lat, record.lon)
    facts = ObjectFacts(
        aliases=[],
        developer=ensure_developer(session, record),
        address=record.address,
        cadastral_number=record.cadastral_number,
        lat=record.lat if located else None,
        lon=record.lon if located else None,
        planned_completion=record.commissioning_at,
    )
    if obj is None:
        obj = create_object(
            session,
            territory_id=territory.id,
            name=record.object_name,
            facts=facts,
            construction_status=construction_status_on(record.started_at, today),
            changes=changes,
        )
    else:
        complete_object(session, obj, facts, changes)
    document = upsert_registry_document(
        session,
        obj,
        record,
        checked_at=now,
        note=registry_note(record, f"Создано синхронизацией {now.date().isoformat()}."),
        changes=changes,
    )
    storage.put_evidence(
        session,
        raw,
        EvidenceKind.registry_response,
        "application/json",
        record.detail_url,
        link=EvidenceLink(document_id=document.id),
    )
    return True


def _flag_missing(
    session: Session, seen_numbers: set[str], territory_ids: set[int], now: datetime, changes: Changes
) -> None:
    """Documents the portal confirmed earlier and no longer lists go back to `checking`."""
    documents = session.scalars(
        select(Document)
        .join(ConstructionObject, ConstructionObject.id == Document.object_id)
        .where(
            Document.check_source == CheckSource.housing_portal,
            Document.check_status == CheckStatus.confirmed,
            Document.checked_by.is_(None),
            Document.number.is_not(None),
            ConstructionObject.territory_id.in_(territory_ids),
            ConstructionObject.is_demo.is_(False),
        )
        .order_by(Document.id)
    )
    for document in documents:
        if document.number in seen_numbers:
            continue
        before = audit.snapshot(document)
        remark = (
            f"{now.date().isoformat()}: запись не найдена в выгрузке реестра КЖК, требуется ручная сверка "
            "(отсутствие в выгрузке не доказывает отсутствие документа)."
        )
        document.check_status = CheckStatus.checking
        document.checked_at = None
        document.note = f"{document.note}\n{remark}" if document.note else remark
        session.flush()
        session.refresh(document)
        audit.record(session, None, "document.update", "document", document.id, before, audit.snapshot(document))
        changes.documents_unconfirmed += 1
        changes.object_ids.add(document.object_id)


def _run(session: Session, client: HomeportalClient, region_id: int, result: SyncResult, changes: Changes) -> None:
    ids = client.list_registry_ids(region_id)
    if not ids:
        result.errors.append("Реестр вернул пустой список объектов; синхронизация остановлена")
        return
    cities = {
        territory.name.casefold(): territory
        for territory in session.scalars(select(Territory).where(Territory.level == TerritoryLevel.city))
    }
    now = datetime.now(UTC)
    seen_numbers: set[str] = set()
    territory_ids: set[int] = set()
    complete = True
    for registry_id in ids:
        try:
            record, raw = client.fetch_record(registry_id)
        except (httpx.HTTPError, RegistryFormatError) as exc:
            result.errors.append(f"Запись {registry_id}: {exc}")
            complete = False
            continue
        result.fetched += 1
        territory = cities.get((record.city or "").casefold())
        if territory is None:
            logger.warning("Registry record %s: city %r is not a territory of SAQ; skipped", registry_id, record.city)
            result.skipped += 1
            continue
        record_changes = Changes()
        try:
            stored = _sync_record(session, territory, record, raw, now, record_changes)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Registry record %s could not be saved", registry_id)
            result.errors.append(f"Запись {registry_id}: не удалось сохранить")
            complete = False
            continue
        if not stored:
            result.skipped += 1
            continue
        changes.merge(record_changes)
        territory_ids.add(territory.id)
        if record.number:
            seen_numbers.add(record.number)
    # A document may be absent only because its record could not be fetched or saved: then say nothing.
    if complete and territory_ids:
        record_changes = Changes()
        _flag_missing(session, seen_numbers, territory_ids, now, record_changes)
        session.commit()
        changes.merge(record_changes)


def save_last_sync(session: Session, result: SyncResult) -> None:
    value = result.model_dump(mode="json")
    row = session.get(AppSetting, LAST_SYNC_KEY)
    if row is None:
        session.add(AppSetting(key=LAST_SYNC_KEY, value=value))
    else:
        row.value = value
    session.commit()


def load_last_sync(session: Session) -> SyncResult | None:
    row = session.get(AppSetting, LAST_SYNC_KEY)
    return SyncResult.model_validate(row.value) if row is not None else None


def sync_homeportal(
    session: Session, region_id: int = REGION_ID_VKO, *, client: HomeportalClient | None = None
) -> SyncResult:
    """Run the sync once and store the outcome. Network and format problems are reported in `errors`, not raised."""
    result = SyncResult(ok=False, region_id=region_id, started_at=datetime.now(UTC), finished_at=datetime.now(UTC))
    changes = Changes()
    owns_client = client is None
    client = client or HomeportalClient()
    try:
        _run(session, client, region_id, result, changes)
    except (httpx.HTTPError, RegistryFormatError) as exc:
        session.rollback()
        result.errors.append(f"Реестр недоступен или ответил в неизвестном формате: {exc}")
    finally:
        if owns_client:
            client.close()
    result.objects_created = changes.objects_created
    result.documents_created = changes.documents_created
    result.documents_updated = changes.documents_updated
    result.documents_unconfirmed = changes.documents_unconfirmed
    result.finished_at = datetime.now(UTC)
    result.ok = not result.errors
    save_last_sync(session, result)
    objects_changed(changes.object_ids)
    logger.info("Homeportal sync finished: %s", result.model_dump_json())
    return result
