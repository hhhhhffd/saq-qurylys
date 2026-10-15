"""Dates that depend on "today" are read in the time zone of the object's territory, like the risk engine does."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Territory
from app.models.enums import ConstructionStatus, KeyStatus, TerritoryLevel
from tests.conftest import World, auth, make_object

# 20:00 UTC on 12 October is already 13 October (01:00) in Almaty (UTC+5) and still 12 October (16:00) in New York.
INSTANT = datetime(2026, 10, 12, 20, 0, tzinfo=UTC)
ALMATY_TODAY = date(2026, 10, 13)
NEW_YORK_TODAY = date(2026, 10, 12)


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
        return INSTANT.astimezone(tz) if tz else INSTANT


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.modules.objects.service.datetime", FrozenDatetime)


def new_york(db: Session, world: World) -> Territory:
    city = Territory(
        parent_id=world.region.id, level=TerritoryLevel.city, code="ny", name="Нью-Йорк", timezone="America/New_York"
    )
    db.add(city)
    db.flush()
    return city


# ---------------------------------------------------------------- stalled_since


def test_entering_stalled_stamps_the_local_date(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    response = client.patch(
        f"/api/v1/objects/{obj.id}", headers=auth(world.users["mio_ust"]), json={"construction_status": "stalled"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["stalled_since"] == ALMATY_TODAY.isoformat()  # not the UTC date, 12 October


def test_creating_a_stalled_object_stamps_the_local_date(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/objects",
        headers=auth(world.users["mio_ust"]),
        json={"name": "ЖК Стоит", "territory_id": world.ust.id, "construction_status": "stalled"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["stalled_since"] == ALMATY_TODAY.isoformat()


def test_importing_a_stalled_object_stamps_the_local_date(client: TestClient, world: World) -> None:
    csv_text = "name,territory_code,construction_status\nЖК Импорт,ust-kamenogorsk,stalled\n"
    response = client.post(
        "/api/v1/objects/import",
        headers=auth(world.users["mio_ust"]),
        files={"file": ("objects.csv", csv_text.encode(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1
    listing = client.get("/api/v1/objects?q=Импорт", headers=auth(world.users["mio_ust"])).json()["items"]
    detail = client.get(f"/api/v1/objects/{listing[0]['id']}", headers=auth(world.users["mio_ust"])).json()
    assert detail["stalled_since"] == ALMATY_TODAY.isoformat()


def test_each_territory_uses_its_own_time_zone(client: TestClient, db: Session, world: World) -> None:
    city = new_york(db, world)
    obj = make_object(db, city)
    response = client.patch(
        f"/api/v1/objects/{obj.id}", headers=auth(world.users["mio_region"]), json={"construction_status": "stalled"}
    )
    assert response.json()["stalled_since"] == NEW_YORK_TODAY.isoformat()


def test_an_explicit_stalled_since_is_kept(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    response = client.patch(
        f"/api/v1/objects/{obj.id}",
        headers=auth(world.users["mio_ust"]),
        json={"construction_status": "stalled", "stalled_since": "2026-09-01"},
    )
    assert response.json()["stalled_since"] == "2026-09-01"


# ---------------------------------------------------------------- key_status_detail


def test_downtime_is_counted_to_the_local_date(client: TestClient, db: Session, world: World) -> None:
    since = ALMATY_TODAY - timedelta(days=12)
    ust = make_object(db, world.ust, "ЖК Усть", key_status=KeyStatus.stalled, stalled_since=since)
    city = new_york(db, world)
    ny = make_object(db, city, "ЖК Нью-Йорк", key_status=KeyStatus.stalled, stalled_since=since)
    headers = auth(world.users["mio_region"])

    rows = {row["id"]: row for row in client.get("/api/v1/objects", headers=headers).json()["items"]}
    dashboard = {row["id"]: row for row in client.get("/api/v1/dashboard", headers=headers).json()["objects"]}
    detail = client.get(f"/api/v1/objects/{ust.id}", headers=headers).json()

    assert rows[ust.id]["key_status_detail"] == {"stalled_days": 12}
    assert dashboard[ust.id]["key_status_detail"] == {"stalled_days": 12}
    assert detail["key_status_detail"] == {"stalled_days": 12}
    assert rows[ny.id]["key_status_detail"] == {"stalled_days": 11}  # it is still the 12th in New York
    assert dashboard[ny.id]["key_status_detail"] == {"stalled_days": 11}


def test_status_other_than_stalled_has_no_detail(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(
        db, world.ust, key_status=KeyStatus.ok, construction_status=ConstructionStatus.active, stalled_since=None
    )
    row = client.get(f"/api/v1/objects/{obj.id}", headers=auth(world.users["mio_ust"])).json()
    assert row["key_status_detail"] is None


# ---------------------------------------------------------------- inspections


def inspect(client: TestClient, world: World, object_id: int, day: date, who: str = "mio_ust") -> Any:
    return client.post(
        f"/api/v1/objects/{object_id}/inspections",
        headers=auth(world.users[who]),
        data={"inspected_at": day.isoformat(), "readiness_pct": "40"},
    )


def test_an_inspection_cannot_be_dated_in_the_future(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)

    tomorrow = inspect(client, world, obj.id, ALMATY_TODAY + timedelta(days=1))

    assert tomorrow.status_code == 422, tomorrow.text
    assert tomorrow.json()["detail"]["code"] == "inspected_at_in_future"
    assert client.get(f"/api/v1/objects/{obj.id}", headers=auth(world.users["mio_ust"])).json()["inspections"] == []
    db.refresh(obj)
    assert obj.readiness_actual_pct is None


def test_an_inspection_of_the_local_today_or_earlier_is_accepted(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    # 13 October is "today" in Almaty although the UTC date is still the 12th.
    assert inspect(client, world, obj.id, ALMATY_TODAY).status_code == 201
    assert inspect(client, world, obj.id, ALMATY_TODAY - timedelta(days=30)).status_code == 201


def test_the_future_limit_follows_the_territory_time_zone(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, new_york(db, world))
    # The 13th is the future in New York, where it is the 12th.
    assert inspect(client, world, obj.id, ALMATY_TODAY, "mio_region").status_code == 422
    assert inspect(client, world, obj.id, NEW_YORK_TODAY, "mio_region").status_code == 201
