"""Dashboard: zone counters, ordering, filters and territory scoping."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ConstructionObject, Developer
from app.models.enums import ConstructionStatus, KeyStatus, Zone
from tests.conftest import World, auth, make_object

URL = "/api/v1/dashboard"
SCORED = datetime(2026, 10, 12, 8, 30, tzinfo=UTC)


def scored(db: Session, world: World, name: str, score: int, zone: Zone, **fields: object) -> ConstructionObject:
    return make_object(
        db, world.ust, name, score=score, zone=zone, key_status=KeyStatus.ok, last_scored_at=SCORED, **fields
    )


def test_counts_cover_every_object_including_unscored(client: TestClient, db: Session, world: World) -> None:
    scored(db, world, "red", 90, Zone.red)
    scored(db, world, "red 2", 70, Zone.red)
    scored(db, world, "yellow", 40, Zone.yellow)
    scored(db, world, "green", 5, Zone.green)
    make_object(db, world.ust, "new 1")
    make_object(db, world.ust, "new 2")

    body = client.get(URL, headers=auth(world.users["mio_ust"])).json()

    assert body["counts"] == {"green": 1, "yellow": 1, "red": 2, "unscored": 2, "total": 6}
    assert len(body["objects"]) == 6


def test_objects_are_sorted_by_score_with_unscored_last(client: TestClient, db: Session, world: World) -> None:
    scored(db, world, "middle", 40, Zone.yellow)
    make_object(db, world.ust, "unscored")
    scored(db, world, "top", 90, Zone.red)
    scored(db, world, "bottom", 5, Zone.green)

    names = [item["name"] for item in client.get(URL, headers=auth(world.users["mio_ust"])).json()["objects"]]

    assert names == ["top", "middle", "bottom", "unscored"]


def test_row_shape(client: TestClient, db: Session, world: World) -> None:
    developer = Developer(bin="123456789012", name="ТОО Застройщик")
    db.add(developer)
    db.flush()
    obj = scored(
        db,
        world,
        "ЖК Алтын",
        55,
        Zone.yellow,
        developer_id=developer.id,
        district_id=world.district.id,
    )
    obj.key_status = KeyStatus.stalled
    obj.construction_status = ConstructionStatus.stalled
    obj.stalled_since = date.today() - timedelta(days=12)
    obj.is_demo = True
    db.flush()

    [row] = client.get(URL, headers=auth(world.users["admin"])).json()["objects"]

    assert row == {
        "id": obj.id,
        "code": obj.code,
        "name": "ЖК Алтын",
        "developer_name": "ТОО Застройщик",
        "score": 55,
        "zone": "yellow",
        "key_status": "stalled",
        "key_status_detail": {"stalled_days": 12},
        "district_name": "Центральный",
        "lat": None,
        "lon": None,
        "is_demo": True,
    }


def test_last_updated_is_the_latest_calculation(client: TestClient, db: Session, world: World) -> None:
    scored(db, world, "old", 10, Zone.green).last_scored_at = SCORED - timedelta(days=3)
    scored(db, world, "new", 20, Zone.green).last_scored_at = SCORED
    make_object(db, world.ust, "never scored")
    db.flush()

    body = client.get(URL, headers=auth(world.users["mio_ust"])).json()

    assert datetime.fromisoformat(body["last_updated_at"]) == SCORED


def test_empty_dashboard(client: TestClient, world: World) -> None:
    body = client.get(URL, headers=auth(world.users["mio_semey"])).json()
    assert body == {
        "counts": {"green": 0, "yellow": 0, "red": 0, "unscored": 0, "total": 0},
        "last_updated_at": None,
        "objects": [],
    }


def test_dashboard_is_scoped_to_the_users_territory(client: TestClient, db: Session, world: World) -> None:
    scored(db, world, "Усть", 90, Zone.red)
    make_object(db, world.semey, "Семей", score=10, zone=Zone.green, last_scored_at=SCORED)

    def names(who: str) -> list[str]:
        return [item["name"] for item in client.get(URL, headers=auth(world.users[who])).json()["objects"]]

    assert names("mio_ust") == ["Усть"]
    assert names("mio_semey") == ["Семей"]
    assert names("mio_region") == ["Усть", "Семей"]
    assert names("admin") == ["Усть", "Семей"]
    assert names("admin_semey") == ["Семей"]
    counts = client.get(URL, headers=auth(world.users["mio_ust"])).json()["counts"]
    assert (counts["red"], counts["green"], counts["total"]) == (1, 0, 1)


def test_territory_filter_includes_the_subtree_and_stays_within_scope(
    client: TestClient, db: Session, world: World
) -> None:
    scored(db, world, "Усть", 90, Zone.red)
    make_object(db, world.semey, "Семей", score=10, zone=Zone.green)
    region = auth(world.users["mio_region"])

    def names(territory: int, headers: dict[str, str] = region) -> list[str]:
        response = client.get(f"{URL}?territory_id={territory}", headers=headers)
        assert response.status_code == 200
        return [item["name"] for item in response.json()["objects"]]

    assert names(world.region.id) == ["Усть", "Семей"]
    assert names(world.ust.id) == ["Усть"]
    assert names(world.semey.id) == ["Семей"]
    assert names(world.ust.id, auth(world.users["mio_semey"])) == []  # outside the user's scope
    assert names(999_999) == []


def test_district_filter(client: TestClient, db: Session, world: World) -> None:
    scored(db, world, "В районе", 50, Zone.yellow, district_id=world.district.id)
    scored(db, world, "Без района", 60, Zone.yellow)
    headers = auth(world.users["mio_ust"])

    body = client.get(f"{URL}?district_id={world.district.id}", headers=headers).json()

    assert [item["name"] for item in body["objects"]] == ["В районе"]
    assert body["counts"]["total"] == 1
    assert body["counts"]["yellow"] == 1


@pytest.mark.parametrize("who", ["gask", "law"])
def test_receiving_bodies_have_no_dashboard(client: TestClient, world: World, who: str) -> None:
    assert client.get(URL, headers=auth(world.users[who])).status_code == 403


def test_dashboard_requires_authentication(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
