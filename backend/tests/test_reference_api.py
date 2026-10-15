from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AuditLog, Notification
from app.models.enums import NotificationKind
from app.modules.settings.service import get_setting, load_settings
from tests.conftest import World, auth, make_object


def test_settings_defaults_partial_update_and_validation(client: TestClient, db: Session, world: World) -> None:
    admin, officer = auth(world.users["admin"]), auth(world.users["mio_ust"])
    defaults = client.get("/api/v1/settings", headers=officer).json()
    assert defaults["review_days"] == 5 and defaults["ad_window_days"] == 7
    assert defaults["link_confidence_threshold"] == 0.8 and defaults["yellow_interval_days"] == 7

    updated = client.put("/api/v1/settings", headers=admin, json={"review_days": 3})
    assert updated.status_code == 200
    assert updated.json()["review_days"] == 3 and updated.json()["ad_window_days"] == 7
    assert get_setting(db, "review_days") == 3
    assert load_settings(db).complaints_threshold == 3

    assert client.put("/api/v1/settings", headers=admin, json={"review_days": 0}).status_code == 422
    assert client.put("/api/v1/settings", headers=admin, json={"unknown_key": 1}).status_code == 422
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "settings.update")).one()
    assert audit.before == {"review_days": 5} and audit.after == {"review_days": 3}


def test_recipient_emails_setting(client: TestClient, world: World) -> None:
    admin = auth(world.users["admin"])
    ok = client.put("/api/v1/settings", headers=admin, json={"recipient_emails": {"gask": ["gask@example.kz"]}})
    assert ok.status_code == 200 and ok.json()["recipient_emails"]["gask"] == ["gask@example.kz"]
    assert (
        client.put("/api/v1/settings", headers=admin, json={"recipient_emails": {"gask": ["not an email"]}}).status_code
        == 422
    )


def test_holiday_crud(client: TestClient, db: Session, world: World) -> None:
    admin = auth(world.users["admin"])
    body = {"day": "2026-03-23", "kind": "holiday", "name": "Наурыз (перенос)"}
    assert client.post("/api/v1/holidays", headers=admin, json=body).status_code == 201
    assert client.post("/api/v1/holidays", headers=admin, json=body).status_code == 409
    client.post(
        "/api/v1/holidays", headers=admin, json={"day": "2026-03-28", "kind": "workday", "name": "Рабочая суббота"}
    )
    listed = client.get("/api/v1/holidays?year=2026", headers=auth(world.users["mio_ust"])).json()
    assert [(h["day"], h["kind"]) for h in listed] == [("2026-03-23", "holiday"), ("2026-03-28", "workday")]
    assert client.get("/api/v1/holidays?year=2027", headers=admin).json() == []
    assert client.delete("/api/v1/holidays/2026-03-23", headers=admin).status_code == 204
    assert client.delete("/api/v1/holidays/2026-03-23", headers=admin).status_code == 404
    assert db.scalars(select(AuditLog.action).where(AuditLog.entity_type == "holiday")).all() == [
        "holiday.create",
        "holiday.create",
        "holiday.delete",
    ]


def test_developers_validation_and_search(client: TestClient, world: World) -> None:
    headers = auth(world.users["mio_ust"])
    assert client.post("/api/v1/developers", headers=headers, json={"bin": "12345", "name": "x"}).status_code == 422
    assert (
        client.post(
            "/api/v1/developers", headers=headers, json={"bin": "123456789012", "name": "x", "phones": ["abc"]}
        ).status_code
        == 422
    )
    created = client.post(
        "/api/v1/developers",
        headers=headers,
        json={"bin": "123456789012", "name": "ТОО Строй", "founders": ["Иванов И."]},
    )
    assert created.status_code == 201
    assert (
        client.post("/api/v1/developers", headers=headers, json={"bin": "123456789012", "name": "Дубль"}).status_code
        == 409
    )
    patched = client.patch(
        f"/api/v1/developers/{created.json()['id']}",
        headers=headers,
        json={"director": "Петров П.", "phones": ["+7 701 111 22 33"]},
    )
    assert patched.json()["director"] == "Петров П." and patched.json()["phones"] == ["+77011112233"]
    assert client.get("/api/v1/developers?q=строй", headers=headers).json()["total"] == 1
    assert client.get("/api/v1/developers?q=1234567", headers=headers).json()["total"] == 1


def test_linked_entities(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    headers = auth(world.users["mio_ust"])
    phone = client.post(
        f"/api/v1/objects/{obj.id}/linked-entities",
        headers=headers,
        json={"kind": "phone", "value": "8 (701) 555-11-22"},
    )
    assert phone.status_code == 201 and phone.json()["value"] == "+77015551122"
    assert (
        client.post(
            f"/api/v1/objects/{obj.id}/linked-entities",
            headers=headers,
            json={"kind": "phone", "value": "+77015551122"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/objects/{obj.id}/linked-entities", headers=headers, json={"kind": "phone", "value": "12"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/objects/{obj.id}/linked-entities", headers=headers, json={"kind": "website", "value": "altyn.kz"}
        ).status_code
        == 201
    )
    assert len(client.get(f"/api/v1/objects/{obj.id}", headers=headers).json()["linked_entities"]) == 2
    assert client.delete(f"/api/v1/linked-entities/{phone.json()['id']}", headers=headers).status_code == 204
    assert client.delete(f"/api/v1/linked-entities/{phone.json()['id']}", headers=headers).status_code == 404
    assert (
        client.delete(f"/api/v1/linked-entities/{phone.json()['id']}", headers=auth(world.users["gask"])).status_code
        == 403
    )


def test_notifications_belong_to_their_owner(client: TestClient, db: Session, world: World) -> None:
    mine, other = world.users["mio_ust"], world.users["mio_region"]
    db.add_all(
        [
            Notification(user_id=mine.id, kind=NotificationKind.red_zone, entity_type="object", entity_id=1),
            Notification(user_id=mine.id, kind=NotificationKind.signal_sent, read_at=datetime.now(UTC)),
            Notification(user_id=other.id, kind=NotificationKind.red_zone),
        ]
    )
    db.flush()
    headers = auth(mine)
    assert client.get("/api/v1/notifications", headers=headers).json()["total"] == 2
    unread = client.get("/api/v1/notifications?unread=true", headers=headers).json()
    assert unread["total"] == 1 and unread["items"][0]["kind"] == "red_zone"

    foreign = db.scalars(select(Notification).where(Notification.user_id == other.id)).one()
    assert client.post(f"/api/v1/notifications/{foreign.id}/read", headers=headers).status_code == 404
    assert (
        client.post(f"/api/v1/notifications/{unread['items'][0]['id']}/read", headers=headers).json()["read_at"]
        is not None
    )
    assert client.post("/api/v1/notifications/read-all", headers=headers).json() == {"updated": 0}
    assert client.get("/api/v1/notifications?unread=true", headers=auth(other)).json()["total"] == 1
    assert client.post("/api/v1/notifications/read-all", headers=auth(other)).json() == {"updated": 1}


def test_audit_endpoint_visibility(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    client.post(
        f"/api/v1/objects/{obj.id}/complaints", headers=auth(world.users["mio_ust"]), json={"received_at": "2026-09-01"}
    )
    admin_view = client.get("/api/v1/audit?entity_type=complaint", headers=auth(world.users["admin"])).json()
    assert admin_view["total"] == 1 and admin_view["items"][0]["username"] == "t_mio_ust"
    # Officers only see history of signal cards, not registry edits.
    assert client.get("/api/v1/audit", headers=auth(world.users["mio_ust"])).json()["total"] == 0


def test_districts_geojson(client: TestClient, db: Session, world: World) -> None:
    db.execute(
        text(
            "UPDATE district SET boundary = ST_Multi(ST_GeomFromText('POLYGON((82 49,83 49,83 50,82 50,82 49))', 4326)) WHERE id = :id"
        ),
        {"id": world.district.id},
    )
    body = client.get(f"/api/v1/territories/{world.ust.id}/districts", headers=auth(world.users["mio_ust"])).json()
    assert body["type"] == "FeatureCollection"
    [feature] = body["features"]
    assert feature["properties"]["name"] == "Центральный" and feature["geometry"]["type"] == "MultiPolygon"
    assert (
        client.get(f"/api/v1/territories/{world.semey.id}/districts", headers=auth(world.users["mio_ust"])).status_code
        == 404
    )
