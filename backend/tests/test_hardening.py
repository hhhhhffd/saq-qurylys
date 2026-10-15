"""Regression tests for scoping of shared resources, error format and failure behaviour."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.deps import SessionDep
from app.errors import register_error_handlers
from app.events import objects_changed
from app.models import Developer, Evidence, SignalCard, Territory
from app.models.enums import EvidenceKind, LockMode, Recipient, SignalOrigin, SignalStatus, TerritoryLevel
from tests.conftest import World, auth, make_object


def _developer(db: Session, bin_: str = "123456789012") -> Developer:
    developer = Developer(bin=bin_, name="ТОО Общий", director="Директор", phones=["+77010000001"])
    db.add(developer)
    db.flush()
    return developer


def test_developer_visibility_follows_objects(client: TestClient, db: Session, world: World) -> None:
    developer = _developer(db)
    make_object(db, world.ust, developer_id=developer.id)
    ust, semey = auth(world.users["mio_ust"]), auth(world.users["mio_semey"])

    assert client.get("/api/v1/developers", headers=ust).json()["total"] == 1
    assert client.get("/api/v1/developers", headers=semey).json()["total"] == 0
    assert client.patch(f"/api/v1/developers/{developer.id}", headers=semey, json={"director": "X"}).status_code == 404
    assert (
        client.post(
            f"/api/v1/developers/{developer.id}/linked-entities",
            headers=semey,
            json={"kind": "website", "value": "x.kz"},
        ).status_code
        == 404
    )
    # An exact BIN still finds the developer, so an officer can link one registered elsewhere.
    by_bin = client.get(f"/api/v1/developers?q={developer.bin}", headers=semey).json()
    assert by_bin["total"] == 1

    # Once the Semey officer has an object with this developer, it becomes visible to them as well.
    make_object(db, world.semey, developer_id=developer.id)
    assert client.get("/api/v1/developers", headers=semey).json()["total"] == 1


def test_developer_without_objects_is_visible_to_everyone(client: TestClient, db: Session, world: World) -> None:
    _developer(db)
    assert client.get("/api/v1/developers", headers=auth(world.users["mio_semey"])).json()["total"] == 1


def test_developer_linked_entity_delete_is_scoped(client: TestClient, db: Session, world: World) -> None:
    developer = _developer(db)
    make_object(db, world.ust, developer_id=developer.id)
    created = client.post(
        f"/api/v1/developers/{developer.id}/linked-entities",
        headers=auth(world.users["mio_ust"]),
        json={"kind": "phone", "value": "+77015550000"},
    )
    assert created.status_code == 201
    entity_id = created.json()["id"]
    assert (
        client.delete(f"/api/v1/linked-entities/{entity_id}", headers=auth(world.users["mio_semey"])).status_code == 404
    )
    assert (
        client.delete(f"/api/v1/linked-entities/{entity_id}", headers=auth(world.users["mio_ust"])).status_code == 204
    )


def test_regional_admin_cannot_change_country_wide_resources(client: TestClient, world: World) -> None:
    regional = auth(world.users["admin_semey"])
    assert client.put("/api/v1/settings", headers=regional, json={"review_days": 3}).status_code == 403
    holiday = {"day": "2026-05-01", "kind": "holiday", "name": "Праздник"}
    assert client.post("/api/v1/holidays", headers=regional, json=holiday).status_code == 403
    assert client.delete("/api/v1/holidays/2026-05-01", headers=regional).status_code == 403
    assert client.get("/api/v1/settings", headers=regional).status_code == 200


def test_regional_admin_audit_is_limited_to_their_territory(client: TestClient, db: Session, world: World) -> None:
    ust_object = make_object(db, world.ust)
    semey_object = make_object(db, world.semey)
    for user, obj in (("mio_ust", ust_object), ("mio_semey", semey_object)):
        client.post(
            f"/api/v1/objects/{obj.id}/complaints", headers=auth(world.users[user]), json={"received_at": "2026-09-01"}
        )
    seen = client.get("/api/v1/audit?entity_type=complaint", headers=auth(world.users["admin_semey"])).json()
    assert [item["username"] for item in seen["items"]] == ["t_mio_semey"]
    everything = client.get("/api/v1/audit?entity_type=complaint", headers=auth(world.users["admin"])).json()
    assert everything["total"] == 2


def _evidence(db: Session, **owner: int) -> Evidence:
    evidence = Evidence(
        kind=EvidenceKind.screenshot_png,
        bucket="b",
        s3_key=f"k/{uuid4().hex}",
        sha256="a" * 64,
        size_bytes=1,
        content_type="image/png",
        retention_until=date(2030, 1, 1),
        lock_mode=LockMode.GOVERNANCE,
        **owner,
    )
    db.add(evidence)
    db.flush()
    return evidence


def test_receiving_bodies_see_only_evidence_of_cards_sent_to_them(
    client: TestClient, db: Session, world: World
) -> None:
    from app.models import Document
    from app.models.enums import DocType

    obj = make_object(db, world.ust)
    document = Document(object_id=obj.id, doc_type=DocType.dsu_permit)
    db.add(document)
    db.flush()
    listed = _evidence(db, document_id=document.id)
    unlisted = _evidence(db, document_id=document.id)
    card = SignalCard(
        number="SQ-2026-0001",
        object_id=obj.id,
        origin=SignalOrigin.auto,
        recipient=Recipient.gask,
        status=SignalStatus.requires_confirmation,
        sections={"permit_checks": [{"doc_type": "dsu_permit", "evidence_ids": [listed.id]}], "publications": []},
    )
    db.add(card)
    db.flush()
    own = _evidence(db, signal_card_id=card.id)
    gask, law, mio = auth(world.users["gask"]), auth(world.users["law"]), auth(world.users["mio_ust"])

    def status(evidence: Evidence, headers: dict[str, str]) -> int:
        return int(client.get(f"/api/v1/evidence/{evidence.id}", headers=headers).status_code)

    # Not sent yet: the receiving body sees nothing, the officer sees everything.
    assert [status(e, gask) for e in (listed, unlisted, own)] == [404, 404, 404]
    assert [status(e, mio) for e in (listed, unlisted, own)] == [200, 200, 200]

    card.status = SignalStatus.sent
    db.flush()
    assert [status(e, gask) for e in (listed, unlisted, own)] == [200, 404, 200]
    assert [status(e, law) for e in (listed, unlisted, own)] == [404, 404, 404]  # another recipient


def test_framework_errors_use_contract_format(client: TestClient, world: World) -> None:
    missing = client.get("/api/v1/nope", headers=auth(world.users["admin"]))
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "http_404"
    wrong_method = client.delete("/api/v1/objects", headers=auth(world.users["admin"]))
    assert wrong_method.status_code == 405
    assert wrong_method.json()["detail"]["code"] == "http_405"


def test_unparsable_csv_is_a_422(client: TestClient, world: World) -> None:
    huge_cell = "x" * 200_000
    response = client.post(
        "/api/v1/objects/import",
        headers=auth(world.users["mio_ust"]),
        files={"file": ("a.csv", f"name,territory_code\n{huge_cell},ust-kamenogorsk\n".encode(), "text/csv")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "csv_invalid"


def test_import_matching_is_scoped_and_unambiguous(client: TestClient, db: Session, world: World) -> None:
    make_object(db, world.ust, "ЖК Дубль", address="ул. Мира 1")
    make_object(db, world.ust, "ЖК Дубль", address="ул. Мира 1")
    semey_object = make_object(db, world.semey, "ЖК Чужой", cadastral_number="05-777")
    headers = auth(world.users["mio_ust"])
    csv_text = (
        "name,territory_code,address,cadastral_number\n"
        "ЖК Дубль,ust-kamenogorsk,ул. Мира 1,\n"  # two matches
        "ЖК Чужой,ust-kamenogorsk,,05-777\n"  # cadastral number exists only outside the scope: new object
        "ЖК Без адреса,ust-kamenogorsk,,\n"
        "ЖК Без адреса,ust-kamenogorsk,,\n"  # no address or cadastral number: never merged
    )
    body = client.post(
        "/api/v1/objects/import", headers=headers, files={"file": ("a.csv", csv_text.encode(), "text/csv")}
    ).json()
    assert body["created"] == 3 and body["updated"] == 0
    assert [(e["row"], "несколько" in e["message"]) for e in body["errors"]] == [(2, True)]
    db.refresh(semey_object)
    assert semey_object.name == "ЖК Чужой"

    unknown = client.post(
        "/api/v1/objects/import",
        headers=headers,
        files={
            "file": ("a.csv", f"code,name,territory_code\n{semey_object.code},X,ust-kamenogorsk\n".encode(), "text/csv")
        },
    ).json()
    assert unknown["errors"][0]["message"].endswith("не найден или недоступен")


def test_import_resets_district_when_city_changes(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust, district_id=world.district.id)
    csv_text = f"code,name,territory_code\n{obj.code},{obj.name},semey\n"
    body = client.post(
        "/api/v1/objects/import",
        headers=auth(world.users["mio_region"]),
        files={"file": ("a.csv", csv_text.encode(), "text/csv")},
    ).json()
    assert body["updated"] == 1
    db.refresh(obj)
    assert obj.territory_id == world.semey.id and obj.district_id is None


def test_unique_violation_maps_to_409(db: Session, world: World) -> None:
    mini = FastAPI()
    register_error_handlers(mini)
    mini.dependency_overrides[get_session] = lambda: db

    @mini.post("/duplicate-territory")
    def duplicate_territory(session: SessionDep) -> None:
        session.add(Territory(level=TerritoryLevel.region, code="vko", name="Дубль"))
        session.flush()

    response = TestClient(mini).post("/duplicate-territory")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "conflict"


def test_objects_changed_deduplicates_and_stops_on_first_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def flaky(name: str, args: list[int], **kwargs: object) -> None:
        calls.append(args[0])
        if args[0] == 2:
            raise ConnectionError("broker down")

    monkeypatch.setattr(get_settings(), "events_enabled", True)
    monkeypatch.setattr("app.events.celery_app.send_task", flaky)
    objects_changed([1, 1, 2, 3, 4])
    assert calls == [1, 2]
