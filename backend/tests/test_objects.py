import re
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AdPost, AuditLog, ConstructionObject, RiskScore
from app.models.enums import KeyStatus, Platform, ScoreTrigger, Zone
from tests.conftest import World, auth, make_object

CODE_PATTERN = re.compile(r"^SQ-OBJ-\d{4,}$")


def _create(client: TestClient, world: World, **overrides: object) -> dict[str, Any]:
    payload = {"name": "ЖК Алтын", "territory_id": world.ust.id, **overrides}
    response = client.post("/api/v1/objects", headers=auth(world.users["mio_ust"]), json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_codes_come_from_the_sequence(client: TestClient, world: World) -> None:
    numbers = []
    for index in range(3):
        code = _create(client, world, name=f"ЖК {index}")["code"]
        assert CODE_PATTERN.match(code)
        numbers.append(int(code.removeprefix("SQ-OBJ-")))
    assert numbers == sorted(numbers)
    assert len(set(numbers)) == 3
    assert numbers[1] == numbers[0] + 1


def test_code_is_zero_padded_to_four_digits(db: Session, world: World) -> None:
    db.execute(text("SELECT setval('object_code_seq', 41)"))  # sequences are not transactional; any value is safe
    assert make_object(db, world.ust).code == "SQ-OBJ-0042"


def test_create_object_returns_detail_and_writes_audit(
    client: TestClient, db: Session, world: World, sent_tasks: list
) -> None:
    developer = client.post(
        "/api/v1/developers",
        headers=auth(world.users["mio_ust"]),
        json={"bin": "123456789012", "name": "ТОО Тест", "phones": ["+7 777 123 45 67", "87771234567"]},
    ).json()
    assert developer["phones"] == ["+77771234567"]

    body = _create(
        client,
        world,
        developer_id=developer["id"],
        district_id=world.district.id,
        lat=49.95,
        lon=82.61,
        aliases=["Алтын 1"],
        planned_completion="2027-12-31",
    )
    assert body["lat"] == 49.95 and body["lon"] == 82.61
    assert body["district_name"] == "Центральный"
    assert body["developer"]["name"] == "ТОО Тест"
    assert body["latest_score"] is None
    assert body["ads_7d_count"] == 0
    assert body["readiness_gap_pp"] is None
    assert body["documents"] == [] and body["complaints"] == [] and body["inspections"] == []

    entry = db.scalars(
        select(AuditLog).where(AuditLog.action == "object.create", AuditLog.entity_id == body["id"])
    ).one()
    assert entry.user_id == world.users["mio_ust"].id
    assert entry.before is None
    assert entry.after["name"] == "ЖК Алтын"
    assert entry.ip == "testclient"
    assert ("risk.recalc_object", (body["id"],)) in sent_tasks


def test_update_object_audits_before_and_after(client: TestClient, db: Session, world: World, sent_tasks: list) -> None:
    created = _create(client, world, address="ул. Старая")
    sent_tasks.clear()
    response = client.patch(
        f"/api/v1/objects/{created['id']}",
        headers=auth(world.users["mio_ust"]),
        json={"address": "ул. Новая", "construction_status": "stalled"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["address"] == "ул. Новая"
    assert body["stalled_since"] == datetime.now().date().isoformat()  # defaulted on entering `stalled`

    entry = db.scalars(
        select(AuditLog).where(AuditLog.action == "object.update", AuditLog.entity_id == created["id"])
    ).one()
    assert entry.before["address"] == "ул. Старая"
    assert entry.after["address"] == "ул. Новая"
    assert ("risk.recalc_object", (created["id"],)) in sent_tasks

    back = client.patch(
        f"/api/v1/objects/{created['id']}", headers=auth(world.users["mio_ust"]), json={"construction_status": "active"}
    ).json()
    assert back["stalled_since"] is None


def test_district_must_belong_to_object_city(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/objects",
        headers=auth(world.users["mio_region"]),
        json={"name": "ЖК", "territory_id": world.semey.id, "district_id": world.district.id},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_district"


def test_object_must_belong_to_a_city(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/objects", headers=auth(world.users["admin"]), json={"name": "ЖК", "territory_id": world.region.id}
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_territory"


def test_list_filters_sorting_and_pagination(client: TestClient, db: Session, world: World) -> None:
    make_object(
        db,
        world.ust,
        "ЖК Красный",
        score=90,
        zone=Zone.red,
        key_status=KeyStatus.no_permit_with_offer,
        district_id=world.district.id,
    )
    make_object(
        db,
        world.ust,
        "ЖК Жёлтый",
        score=40,
        zone=Zone.yellow,
        key_status=KeyStatus.permit_checking,
        aliases=["Золотой квартал"],
    )
    make_object(db, world.ust, "ЖК Новый")  # never scored
    headers = auth(world.users["mio_ust"])

    everything = client.get("/api/v1/objects", headers=headers).json()
    assert [row["name"] for row in everything["items"]] == [
        "ЖК Красный",
        "ЖК Жёлтый",
        "ЖК Новый",
    ]  # score desc, unscored last
    assert everything["total"] == 3

    page = client.get("/api/v1/objects?limit=1&offset=1", headers=headers).json()
    assert [row["name"] for row in page["items"]] == ["ЖК Жёлтый"]
    assert page["total"] == 3

    red = client.get("/api/v1/objects?zone=red", headers=headers).json()
    assert [row["name"] for row in red["items"]] == ["ЖК Красный"]
    assert red["items"][0]["district_name"] == "Центральный"
    assert red["items"][0]["key_status"] == "no_permit_with_offer"

    by_district = client.get(f"/api/v1/objects?district_id={world.district.id}", headers=headers).json()
    assert by_district["total"] == 1
    assert client.get("/api/v1/objects?q=золотой", headers=headers).json()["total"] == 1  # alias search
    assert client.get("/api/v1/objects?q=ЖК%20жёлт", headers=headers).json()["total"] == 1
    assert client.get("/api/v1/objects?q=%25", headers=headers).json()["total"] == 0  # LIKE wildcards are escaped


def test_stalled_key_status_detail(client: TestClient, db: Session, world: World) -> None:
    since = datetime.now(UTC).date() - timedelta(days=45)
    make_object(db, world.ust, "ЖК Стоит", key_status=KeyStatus.stalled, stalled_since=since)
    row = client.get("/api/v1/objects", headers=auth(world.users["mio_ust"])).json()["items"][0]
    assert row["key_status_detail"] == {"stalled_days": 45}


def test_detail_reports_recent_ads_gap_and_latest_score(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust, readiness_actual_pct=30, readiness_claimed_pct=55)
    now = datetime.now(UTC)
    db.add_all(
        [
            AdPost(platform=Platform.instagram, object_id=obj.id, published_at=now - timedelta(days=2)),
            AdPost(platform=Platform.instagram, object_id=obj.id, published_at=now - timedelta(days=40)),
        ]
    )
    db.add_all(
        [
            RiskScore(
                object_id=obj.id,
                score=10,
                zone=Zone.green,
                breakdown=[],
                trigger=ScoreTrigger.schedule,
                calculated_at=now - timedelta(days=1),
            ),
            RiskScore(
                object_id=obj.id,
                score=75,
                zone=Zone.red,
                zone_reasons=["no_permit"],
                breakdown=[{"code": "no_permit"}],
                trigger=ScoreTrigger.event,
                calculated_at=now,
            ),
        ]
    )
    db.flush()
    body = client.get(f"/api/v1/objects/{obj.id}", headers=auth(world.users["mio_ust"])).json()
    assert body["ads_7d_count"] == 1
    assert body["readiness_gap_pp"] == 25
    assert body["latest_score"]["score"] == 75
    assert body["latest_score"]["zone_reasons"] == ["no_permit"]


def test_demo_flag_is_not_settable_through_api(client: TestClient, db: Session, world: World) -> None:
    created = _create(client, world, is_demo=True, score=100)
    obj = db.get(ConstructionObject, created["id"])
    assert obj is not None and obj.is_demo is False and obj.score is None
