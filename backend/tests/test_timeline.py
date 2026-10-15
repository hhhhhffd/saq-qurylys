"""GET /dashboard/timeline: the zones of the objects at past moments, from the stored score history."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.geo import make_point
from app.models import ConstructionObject, RiskScore
from app.models.enums import ScoreTrigger, Zone
from app.modules.dashboard.router import MAX_TIMELINE_FRAMES
from tests.conftest import World, auth, make_object

URL = "/api/v1/dashboard/timeline"
END = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def at(days_ago: int) -> datetime:
    return END - days_ago * DAY


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def record(
    db: Session, obj: ConstructionObject, days_ago: int, score: int, zone: Zone, trigger: ScoreTrigger
) -> RiskScore:
    row = RiskScore(
        object_id=obj.id,
        score=score,
        zone=zone,
        zone_reasons=[],
        breakdown={},
        trigger=trigger,
        calculated_at=at(days_ago),
    )
    db.add(row)
    db.flush()
    return row


def get(client: TestClient, world: World, user: str = "mio_ust", **params: str) -> dict[str, Any]:
    response = client.get(URL, headers=auth(world.users[user]), params={"to": stamp(END), **params})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def frame_scores(body: dict[str, Any]) -> list[dict[int, tuple[int, str]]]:
    return [{item["object_id"]: (item["score"], item["zone"]) for item in frame["objects"]} for frame in body["frames"]]


def test_each_frame_holds_the_latest_score_of_every_object_by_that_moment(
    client: TestClient, db: Session, world: World
) -> None:
    first = make_object(db, world.ust, "ЖК Первый", location=make_point(49.9, 82.6), is_demo=True)
    second = make_object(db, world.ust, "ЖК Второй")
    record(db, first, 9, 0, Zone.green, ScoreTrigger.replay)
    record(db, first, 5, 40, Zone.yellow, ScoreTrigger.replay)
    record(db, first, 1, 70, Zone.red, ScoreTrigger.event)
    record(db, second, 6, 10, Zone.green, ScoreTrigger.replay)

    body = get(client, world, **{"from": stamp(at(10)), "step": "day"})

    assert [frame["at"] for frame in body["frames"]] == [stamp(at(days)) for days in range(10, -1, -1)]
    frames = {frame["at"]: scores for frame, scores in zip(body["frames"], frame_scores(body), strict=True)}
    assert frames[stamp(at(10))] == {}  # nothing is scored yet
    assert frames[stamp(at(9))] == {first.id: (0, "green")}  # a score dated exactly at the frame counts
    assert frames[stamp(at(6))] == {first.id: (0, "green"), second.id: (10, "green")}
    assert frames[stamp(at(4))] == {first.id: (40, "yellow"), second.id: (10, "green")}
    assert frames[stamp(at(0))] == {first.id: (70, "red"), second.id: (10, "green")}  # the real score, last frame
    assert body["objects"] == [
        {"object_id": first.id, "name": "ЖК Первый", "lat": 49.9, "lon": 82.6, "is_demo": True},
        {"object_id": second.id, "name": "ЖК Второй", "lat": None, "lon": None, "is_demo": False},
    ]


def test_objects_without_a_score_by_the_last_frame_are_not_listed(
    client: TestClient, db: Session, world: World
) -> None:
    scored = make_object(db, world.ust, "ЖК С баллом")
    make_object(db, world.ust, "ЖК Без балла")
    later = make_object(db, world.ust, "ЖК Оценён позже")
    record(db, scored, 2, 20, Zone.green, ScoreTrigger.event)
    record(db, later, -1, 20, Zone.green, ScoreTrigger.event)  # dated after the end of the period

    body = get(client, world, **{"from": stamp(at(3)), "step": "day"})

    assert [item["object_id"] for item in body["objects"]] == [scored.id]
    assert [len(frame["objects"]) for frame in body["frames"]] == [0, 1, 1, 1]


def test_a_tie_between_scores_of_one_moment_goes_to_the_later_row(
    client: TestClient, db: Session, world: World
) -> None:
    obj = make_object(db, world.ust)
    record(db, obj, 1, 10, Zone.green, ScoreTrigger.replay)
    record(db, obj, 1, 30, Zone.yellow, ScoreTrigger.event)

    [frame] = get(client, world, **{"from": stamp(at(0))})["frames"]

    assert frame["objects"] == [{"object_id": obj.id, "score": 30, "zone": "yellow"}]


def test_weekly_frames_end_at_the_requested_moment(client: TestClient, db: Session, world: World) -> None:
    body = get(client, world, **{"from": stamp(at(21))})
    assert [frame["at"] for frame in body["frames"]] == [stamp(at(days)) for days in (21, 14, 7, 0)]

    # A period that is not a whole number of steps: the oldest frame is dropped, the last is still `to`.
    body = get(client, world, **{"from": stamp(at(20))})
    assert [frame["at"] for frame in body["frames"]] == [stamp(at(days)) for days in (14, 7, 0)]


def test_the_default_period_is_the_last_26_weeks_up_to_now(client: TestClient, db: Session, world: World) -> None:
    before = datetime.now(UTC)
    response = client.get(URL, headers=auth(world.users["mio_ust"]))
    after = datetime.now(UTC)

    frames = [datetime.fromisoformat(frame["at"]) for frame in response.json()["frames"]]
    assert len(frames) == 27
    assert before <= frames[-1] <= after
    assert frames[-1] - frames[0] == timedelta(weeks=26)


def test_dates_without_a_time_are_taken_as_midnight_utc(client: TestClient, db: Session, world: World) -> None:
    response = client.get(
        URL, headers=auth(world.users["mio_ust"]), params={"from": "2026-10-01", "to": "2026-10-03", "step": "day"}
    )
    assert [frame["at"] for frame in response.json()["frames"]] == [
        "2026-10-01T00:00:00Z",
        "2026-10-02T00:00:00Z",
        "2026-10-03T00:00:00Z",
    ]


def test_the_number_of_frames_is_capped(client: TestClient, db: Session, world: World) -> None:
    headers = auth(world.users["mio_ust"])
    longest = END - (MAX_TIMELINE_FRAMES - 1) * DAY
    ok = client.get(URL, headers=headers, params={"from": stamp(longest), "to": stamp(END), "step": "day"})
    assert ok.status_code == 200 and len(ok.json()["frames"]) == MAX_TIMELINE_FRAMES

    too_long = client.get(URL, headers=headers, params={"from": stamp(longest - DAY), "to": stamp(END), "step": "day"})
    assert too_long.status_code == 422 and too_long.json()["detail"]["code"] == "timeline_too_long"


def test_a_period_that_ends_before_it_starts_is_rejected(client: TestClient, db: Session, world: World) -> None:
    response = client.get(URL, headers=auth(world.users["mio_ust"]), params={"from": stamp(END), "to": stamp(at(1))})
    assert response.status_code == 422 and response.json()["detail"]["code"] == "timeline_range_invalid"


def test_an_unknown_step_is_rejected(client: TestClient, db: Session, world: World) -> None:
    response = client.get(URL, headers=auth(world.users["mio_ust"]), params={"step": "month"})
    assert response.status_code == 422


def test_only_objects_in_the_territory_of_the_user_are_shown(client: TestClient, db: Session, world: World) -> None:
    ust = make_object(db, world.ust, "ЖК Усть")
    semey = make_object(db, world.semey, "ЖК Семей")
    for obj in (ust, semey):
        record(db, obj, 1, 10, Zone.green, ScoreTrigger.event)

    def listed(user: str) -> list[int]:
        body = get(client, world, user, **{"from": stamp(at(1)), "step": "day"})
        assert [item["object_id"] for item in body["frames"][-1]["objects"]] == [
            item["object_id"] for item in body["objects"]
        ]
        return [item["object_id"] for item in body["objects"]]

    assert listed("mio_ust") == [ust.id]
    assert listed("mio_semey") == [semey.id]
    assert listed("mio_region") == [ust.id, semey.id]
    assert listed("admin") == [ust.id, semey.id]


def test_only_staff_may_read_the_timeline(client: TestClient, db: Session, world: World) -> None:
    for user in ("gask", "law"):
        assert client.get(URL, headers=auth(world.users[user])).status_code == 403
    assert client.get(URL).status_code == 401
