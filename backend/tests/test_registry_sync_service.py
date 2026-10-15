import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import seed, storage
from app.config import get_settings
from app.models import AppSetting, AuditLog, ConstructionObject, Document, Evidence
from app.models.enums import CheckStatus, EvidenceKind
from app.modules.registry_sync import tasks
from app.modules.registry_sync.client import REQUEST_PAUSE_S, USER_AGENT, HomeportalClient
from app.modules.registry_sync.pilot import import_pilot
from app.modules.registry_sync.service import LAST_SYNC_KEY, sync_homeportal
from tests.conftest import World, auth

FIXTURES = Path(__file__).parent / "fixtures" / "homeportal"
ALL_IDS = [1505, 1452, 1428, 1398, 1375, 1331, 1330, 1329, 1241, 1218, 1141, 1077, 1027, 953, 807]
DETAIL_URL = re.compile(r"/api/v1/objects-detail/(\d+)$")


def _raw(registry_id: int) -> bytes:
    return (FIXTURES / f"detail_{registry_id}.json").read_bytes()


class FakePortal:
    """Serves the sanitized fixtures the way api.homeportal.kz answers, and remembers the requests."""

    def __init__(self, ids: list[int] = ALL_IDS) -> None:
        self.ids = ids
        self.requests: list[httpx.Request] = []
        self.failures: dict[int, int] = {}  # registry id -> HTTP status
        self.list_status = 200
        self.edit: dict[int, Callable[[dict[str, Any]], None]] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "POST" and request.url.path == "/api/v1/getobjects":
            assert json.loads(request.content) == {"region_id": 16}
            if self.list_status != 200:
                return httpx.Response(self.list_status)
            body = json.loads((FIXTURES / "getobjects_region16.json").read_text(encoding="utf-8"))
            body["data"]["objects"]["data"] = [
                item for item in body["data"]["objects"]["data"] if item["id"] in self.ids
            ]
            return httpx.Response(200, json=body)
        match = DETAIL_URL.search(request.url.path)
        assert request.method == "GET" and match is not None, request.url
        registry_id = int(match[1])
        if registry_id in self.failures:
            return httpx.Response(self.failures[registry_id])
        if registry_id in self.edit:
            body = json.loads(_raw(registry_id))
            self.edit[registry_id](body)
            return httpx.Response(200, json=body)
        return httpx.Response(200, content=_raw(registry_id), headers={"content-type": "application/json"})

    def client(self, **kwargs: Any) -> HomeportalClient:
        return HomeportalClient(
            httpx.Client(transport=httpx.MockTransport(self)), pause_s=kwargs.pop("pause_s", 0), **kwargs
        )


@pytest.fixture
def portal() -> FakePortal:
    return FakePortal()


@pytest.fixture
def ready(db: Session) -> Session:
    seed.seed_reference(db)
    seed.load_districts(db)
    return db


def _document(db: Session, number: str) -> Document:
    return db.scalars(select(Document).where(Document.number == number)).one()


def _evidence(db: Session, document: Document) -> list[Evidence]:
    return list(db.scalars(select(Evidence).where(Evidence.document_id == document.id).order_by(Evidence.id)))


def test_first_sync_creates_objects_for_records_that_are_not_completed(
    ready: Session, portal: FakePortal, bucket: str
) -> None:
    result = sync_homeportal(ready, client=portal.client())

    assert result.ok and result.errors == []
    assert (result.fetched, result.objects_created, result.documents_created, result.skipped) == (15, 9, 10, 5)
    names = set(ready.scalars(select(ConstructionObject.name)))
    # Completed according to the portal (commissioning date passed) and unknown to SAQ: not created.
    assert names == {
        "МЖК PARK LINE", "ЖК Satti City", "МЖК Renesans", "ЖК Viva Life", "ЖК Asyl Tau",
        "ЖК ASYLTAS", "ЖК Orda", "ЖК ASYLYM", "ЖК Золотой квадрат",
    }  # fmt: skip

    document = _document(ready, "597/МҚЗТ-К-83у")
    assert document.check_status is CheckStatus.confirmed and document.checked_by is None
    assert document.checked_at is not None and (datetime.now(UTC) - document.checked_at).total_seconds() < 60
    obj = ready.get(ConstructionObject, document.object_id)
    assert obj is not None and obj.district_id is not None and obj.developer_id is not None
    assert obj.cadastral_number == "05-085-091-1658"
    renesans = ready.scalars(select(ConstructionObject).where(ConstructionObject.name == "МЖК Renesans")).one()
    assert renesans.lat is None  # the registry puts it 140 km away


def test_raw_answer_is_kept_as_evidence_of_the_document(ready: Session, portal: FakePortal, bucket: str) -> None:
    sync_homeportal(ready, client=portal.client())

    document = _document(ready, "597/МҚЗТ-К-83у")
    [evidence] = _evidence(ready, document)
    assert evidence.kind is EvidenceKind.registry_response and evidence.content_type == "application/json"
    assert evidence.source_url == "https://api.homeportal.kz/api/v1/objects-detail/1398"
    assert evidence.sha256 == hashlib.sha256(_raw(1398)).hexdigest() and evidence.created_by is None
    stored = storage.get_client().get_object(bucket, evidence.s3_key)
    try:
        assert stored.read() == _raw(1398)  # exactly as received
    finally:
        stored.close()
        stored.release_conn()
    assert (
        ready.scalar(select(func.count()).select_from(Evidence).where(Evidence.kind == EvidenceKind.registry_response))
        == 10
    )


def test_changes_are_audited_by_the_system(ready: Session, portal: FakePortal, bucket: str) -> None:
    sync_homeportal(ready, client=portal.client())
    rows = list(ready.scalars(select(AuditLog).where(AuditLog.action.in_(["object.create", "document.create"]))))
    assert {row.action for row in rows} == {"object.create", "document.create"}
    assert all(row.user_id is None for row in rows)


def test_repeating_the_sync_updates_and_never_duplicates(ready: Session, portal: FakePortal, bucket: str) -> None:
    sync_homeportal(ready, client=portal.client())
    first_check = _document(ready, "597/МҚЗТ-К-83у").checked_at
    audit_rows = ready.scalar(select(func.count()).select_from(AuditLog))

    result = sync_homeportal(ready, client=portal.client())

    assert result.ok and (result.objects_created, result.documents_created, result.documents_updated) == (0, 0, 0)
    assert ready.scalar(select(func.count()).select_from(ConstructionObject)) == 9
    assert ready.scalar(select(func.count()).select_from(Document)) == 10
    assert ready.scalar(select(func.count()).select_from(AuditLog)) == audit_rows  # a fresh check date is not news
    second_check = _document(ready, "597/МҚЗТ-К-83у").checked_at
    assert first_check is not None and second_check is not None and second_check > first_check
    assert len(_evidence(ready, _document(ready, "597/МҚЗТ-К-83у"))) == 2  # every fetch is kept


def test_sync_after_the_pilot_import_finds_the_pilot_objects(ready: Session, portal: FakePortal, bucket: str) -> None:
    import_pilot(ready)
    objects_before = ready.scalar(select(func.count()).select_from(ConstructionObject))
    documents_before = ready.scalar(select(func.count()).select_from(Document))

    result = sync_homeportal(ready, client=portal.client())

    assert result.ok and result.objects_created == 0 and result.documents_created == 0
    assert ready.scalar(select(func.count()).select_from(ConstructionObject)) == objects_before
    assert ready.scalar(select(func.count()).select_from(Document)) == documents_before
    # Three records of ЖАНЫМ belong to the one pilot object, matched by their document numbers.
    zhanym = {_document(ready, number).object_id for number in ("ДПГ-23-16-068/155", "ДС № 2 к ДПГ-23-16-068/155")}
    assert len(zhanym) == 1
    refreshed = _document(ready, "ДПГ-23-16-068/155").checked_at
    assert refreshed is not None and refreshed > datetime(2026, 10, 13, tzinfo=UTC)


def test_document_missing_from_the_registry_goes_back_to_checking(
    ready: Session, portal: FakePortal, bucket: str, sent_tasks: list[tuple[str, tuple[object, ...]]]
) -> None:
    import_pilot(ready)
    sent_tasks.clear()
    portal.ids = [item for item in ALL_IDS if item != 1398]

    result = sync_homeportal(ready, client=portal.client())

    assert result.ok and result.documents_unconfirmed == 1
    document = _document(ready, "597/МҚЗТ-К-83у")
    assert document.check_status is CheckStatus.checking  # never `not_found` automatically
    assert document.checked_at is None
    assert document.note is not None and "запись не найдена в выгрузке реестра КЖК" in document.note
    assert document.note.startswith("Участие БВУ.")  # the original note is kept
    audit = ready.scalars(
        select(AuditLog).where(AuditLog.entity_id == document.id, AuditLog.action == "document.update")
    ).one()
    assert (
        audit.user_id is None
        and audit.before["check_status"] == "confirmed"
        and audit.after["check_status"] == "checking"
    )
    assert ("risk.recalc_object", (document.object_id,)) in sent_tasks


def test_human_checked_documents_are_not_touched(ready: Session, portal: FakePortal, bucket: str, world: World) -> None:
    import_pilot(ready)
    portal.ids = [item for item in ALL_IDS if item != 1398]
    document = _document(ready, "597/МҚЗТ-К-83у")
    document.checked_by = world.users["mio_ust"].id
    ready.flush()

    result = sync_homeportal(ready, client=portal.client())

    assert result.documents_unconfirmed == 0
    ready.refresh(document)
    assert document.check_status is CheckStatus.confirmed


def test_failed_record_prevents_marking_documents_as_missing(ready: Session, portal: FakePortal, bucket: str) -> None:
    import_pilot(ready)
    portal.ids = [item for item in ALL_IDS if item != 1398]
    portal.failures[1375] = 500

    result = sync_homeportal(ready, client=portal.client())

    assert not result.ok and any("1375" in error for error in result.errors)
    assert result.documents_unconfirmed == 0  # 1398 may be missing only because the run was incomplete
    assert _document(ready, "597/МҚЗТ-К-83у").check_status is CheckStatus.confirmed


def test_empty_registry_answer_is_not_trusted(ready: Session, portal: FakePortal, bucket: str) -> None:
    import_pilot(ready)
    portal.ids = []

    result = sync_homeportal(ready, client=portal.client())

    assert not result.ok and "пустой список" in result.errors[0]
    assert (
        ready.scalar(select(func.count()).select_from(Document).where(Document.check_status == CheckStatus.checking))
        == 17
    )


def test_registry_outage_is_reported_and_stored_not_raised(ready: Session, portal: FakePortal) -> None:
    portal.list_status = 503

    result = sync_homeportal(ready, client=portal.client())

    assert not result.ok and result.errors and result.fetched == 0
    stored = ready.get(AppSetting, LAST_SYNC_KEY)
    assert stored is not None and stored.value["ok"] is False and stored.value["region_id"] == 16


def test_unknown_basis_is_not_trusted(ready: Session, portal: FakePortal, bucket: str) -> None:
    portal.ids = [1398]
    portal.edit[1398] = lambda body: body["data"]["basicData"]["authority"].update(name="Иное основание")

    result = sync_homeportal(ready, client=portal.client())

    assert result.ok
    document = _document(ready, "597/МҚЗТ-К-83у")
    assert document.check_status is CheckStatus.checking and document.checked_at is None


def test_record_of_an_unknown_city_is_skipped(ready: Session, portal: FakePortal, bucket: str) -> None:
    portal.ids = [1398]
    portal.edit[1398] = lambda body: body["data"]["basicData"]["city"].update(name_ru="г. Атлантида")

    result = sync_homeportal(ready, client=portal.client())

    assert (result.fetched, result.skipped, result.objects_created) == (1, 1, 0)


def test_requests_identify_us_and_keep_a_pause(ready: Session, portal: FakePortal, bucket: str) -> None:
    sleeps: list[float] = []
    portal.ids = [1398, 1375]

    sync_homeportal(ready, client=portal.client(pause_s=REQUEST_PAUSE_S, sleep=sleeps.append, clock=lambda: 100.0))

    assert len(portal.requests) == 3  # the list and two details
    assert {request.headers["user-agent"] for request in portal.requests} == {USER_AGENT}
    assert USER_AGENT == "SAQ-QURYLYS/1.0 (pilot; contact: admin)" and REQUEST_PAUSE_S >= 1.5
    assert sleeps == [REQUEST_PAUSE_S, REQUEST_PAUSE_S]  # none before the first request


def test_last_run_is_stored_and_served(
    client: TestClient, ready: Session, world: World, portal: FakePortal, bucket: str
) -> None:
    assert client.get("/api/v1/registry-sync/status", headers=auth(world.users["admin"])).json() == {
        "scheduled_enabled": False,
        "last_sync": None,
    }
    sync_homeportal(ready, client=portal.client())

    for user in ("admin", "mio_ust"):
        body = client.get("/api/v1/registry-sync/status", headers=auth(world.users[user])).json()
        assert body["last_sync"]["ok"] is True and body["last_sync"]["objects_created"] == 9
    for user in ("gask", "law"):
        assert client.get("/api/v1/registry-sync/status", headers=auth(world.users[user])).status_code == 403
    assert client.get("/api/v1/registry-sync/status").status_code == 401


def test_admin_starts_a_run_by_hand(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[dict[str, Any]] = []

    class _Task:
        id = "task-123"

    def send_task(name: str, **kwargs: Any) -> _Task:
        sent.append({"name": name, **kwargs})
        return _Task()

    monkeypatch.setattr("app.modules.registry_sync.router.celery_app.send_task", send_task)

    response = client.post("/api/v1/registry-sync/homeportal", headers=auth(world.users["admin"]))

    assert response.status_code == 202 and response.json() == {"task_id": "task-123"}
    assert sent == [
        {"name": "registry.sync_homeportal", "kwargs": {"scheduled": False}, "queue": "collect", "retry": False}
    ]
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "registry_sync.start")).one()
    assert audit.user_id == world.users["admin"].id and audit.after == {"task_id": "task-123"}


def test_only_a_global_admin_may_start_a_run(client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("nothing may be queued")

    monkeypatch.setattr("app.modules.registry_sync.router.celery_app.send_task", boom)
    for user in ("admin_semey", "mio_ust", "gask", "law"):
        assert client.post("/api/v1/registry-sync/homeportal", headers=auth(world.users[user])).status_code == 403
    assert client.post("/api/v1/registry-sync/homeportal").status_code == 401


def test_unreachable_queue_is_reported(client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("redis down")

    monkeypatch.setattr("app.modules.registry_sync.router.celery_app.send_task", broken)
    response = client.post("/api/v1/registry-sync/homeportal", headers=auth(world.users["admin"]))
    assert response.status_code == 503 and response.json()["detail"]["code"] == "queue_unavailable"


class _Borrowed:
    def __init__(self, session: Session) -> None:
        self.session = session

    def __enter__(self) -> Session:
        return self.session

    def __exit__(self, *exc: object) -> None:
        return None


def test_scheduled_run_does_nothing_until_enabled(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_sync(session: Session) -> _FakeResult:
        calls.append(1)
        return _FakeResult()

    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: lambda: _Borrowed(db))
    monkeypatch.setattr(tasks, "sync_homeportal", fake_sync)

    monkeypatch.setattr(get_settings(), "homeportal_sync_enabled", False)
    assert tasks.sync_homeportal_task(scheduled=True) is None and calls == []

    # An administrator's request is explicit and runs regardless of the flag.
    assert tasks.sync_homeportal_task(scheduled=False) == {"ok": True} and calls == [1]

    monkeypatch.setattr(get_settings(), "homeportal_sync_enabled", True)
    assert tasks.sync_homeportal_task(scheduled=True) == {"ok": True} and calls == [1, 1]


class _FakeResult:
    def model_dump(self, mode: str) -> dict[str, Any]:
        return {"ok": True}
