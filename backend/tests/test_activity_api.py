"""Live activity feed: event kinds, replay exclusion, cursor behaviour, territory scope and roles."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ConstructionObject, RiskScore, SignalCard
from app.models.enums import AdOrigin, Platform, ScoreTrigger, SignalOrigin, SignalStatus, Zone
from app.modules.activity.service import GRACE, Position, decode_cursor, encode_cursor
from tests.conftest import World, auth, make_object
from tests.support_ads import add_ad

URL = "/api/v1/activity"

_card_numbers = iter(range(1, 10_000))


def ago(**delta: float) -> datetime:
    return datetime.now(UTC) - timedelta(**delta)


def add_score(
    db: Session,
    obj: ConstructionObject,
    score: int,
    zone: Zone,
    at: datetime,
    trigger: ScoreTrigger = ScoreTrigger.event,
) -> RiskScore:
    row = RiskScore(
        object_id=obj.id, score=score, zone=zone, zone_reasons=[], breakdown={}, trigger=trigger, calculated_at=at
    )
    db.add(row)
    db.flush()
    return row


def add_card(
    db: Session,
    obj: ConstructionObject,
    created_at: datetime,
    *,
    sent_at: datetime | None = None,
    origin: SignalOrigin = SignalOrigin.auto,
) -> SignalCard:
    card = SignalCard(
        number=f"SQ-2026-{next(_card_numbers):04d}",
        object_id=obj.id,
        origin=origin,
        status=SignalStatus.sent if sent_at else SignalStatus.requires_confirmation,
        sections={},
        sent_at=sent_at,
        created_at=created_at,
    )
    db.add(card)
    db.flush()
    return card


def feed(client: TestClient, user: Any, **params: Any) -> dict[str, Any]:
    response = client.get(URL, headers=auth(user), params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def ids(body: dict[str, Any]) -> list[str]:
    return [item["id"] for item in body["items"]]


def visible(client: TestClient, user: Any) -> set[str]:
    """Every event the user can see: a cursor at the start of the look-back leaves nothing out."""
    start = encode_cursor(Position(ago(days=6), 0, 0), datetime.now(UTC))
    return set(ids(feed(client, user, after=start, limit=100)))


class Poller:
    """What the web client does: passes the cursor back and takes only the events whose ids it has not seen."""

    def __init__(self, client: TestClient, user: Any) -> None:
        self.client, self.user = client, user
        self.cursor: str | None = None
        self.seen: set[str] = set()

    def poll(self, **params: Any) -> list[str]:
        if self.cursor is not None:
            params["after"] = self.cursor
        body = feed(self.client, self.user, **params)
        self.cursor = body["cursor"]
        fresh = [event_id for event_id in ids(body) if event_id not in self.seen]
        self.seen.update(ids(body))
        return fresh


# ---------------------------------------------------------------- event kinds


def test_ad_received_carries_origin_platform_and_linked_object(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "ЖК Алтын", is_demo=True)
    ad = add_ad(
        db,
        world.ust,
        object_id=obj.id,
        origin=AdOrigin.citizen,
        platform=Platform.telegram,
        is_demo=True,
        created_at=ago(minutes=1),
    )

    (event,) = feed(client, world.users["mio_ust"])["items"]

    assert event["id"] == f"ad_received:{ad.id}"
    assert event["kind"] == "ad_received"
    assert event["ad_id"] == ad.id
    assert event["origin"] == "citizen"
    assert event["platform"] == "telegram"
    assert event["object_id"] == obj.id
    assert event["object_name"] == "ЖК Алтын"
    assert event["is_demo"] is True
    assert event["score_before"] is None
    assert event["signal_id"] is None


def test_ad_without_object_has_no_object_fields(client: TestClient, db: Session, world: World) -> None:
    add_ad(db, world.ust, origin=AdOrigin.collector, created_at=ago(minutes=1))

    (event,) = feed(client, world.users["mio_ust"])["items"]

    assert event["origin"] == "collector"
    assert event["object_id"] is None
    assert event["object_name"] is None
    assert event["is_demo"] is False


def test_score_changed_carries_scores_and_zones(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "ЖК Зарядье", is_demo=True)
    add_score(db, obj, 45, Zone.yellow, ago(hours=2))
    changed = add_score(db, obj, 70, Zone.red, ago(minutes=5))

    (event,) = feed(client, world.users["mio_ust"])["items"]

    assert event["id"] == f"score_changed:{changed.id}"
    assert event["kind"] == "score_changed"
    assert event["object_id"] == obj.id
    assert event["object_name"] == "ЖК Зарядье"
    assert (event["score_before"], event["score_after"]) == (45, 70)
    assert (event["zone_before"], event["zone_after"]) == ("yellow", "red")
    assert event["is_demo"] is True


def test_unchanged_score_is_not_an_event(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_score(db, obj, 45, Zone.yellow, ago(hours=2))
    add_score(db, obj, 45, Zone.yellow, ago(hours=1), ScoreTrigger.schedule)

    assert feed(client, world.users["mio_ust"])["items"] == []


def test_zone_change_with_the_same_score_is_an_event(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_score(db, obj, 60, Zone.yellow, ago(hours=2))
    add_score(db, obj, 60, Zone.red, ago(hours=1))

    (event,) = feed(client, world.users["mio_ust"])["items"]

    assert (event["score_before"], event["score_after"]) == (60, 60)
    assert (event["zone_before"], event["zone_after"]) == ("yellow", "red")


def test_first_score_of_an_object_is_not_an_event(client: TestClient, db: Session, world: World) -> None:
    add_score(db, make_object(db, world.ust), 45, Zone.yellow, ago(hours=1))

    assert feed(client, world.users["mio_ust"])["items"] == []


def test_previous_score_older_than_the_lookback_still_counts(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_score(db, obj, 20, Zone.green, ago(days=30))
    add_score(db, obj, 40, Zone.yellow, ago(hours=1))

    (event,) = feed(client, world.users["mio_ust"])["items"]

    assert (event["score_before"], event["score_after"]) == (20, 40)


def test_replayed_history_is_neither_an_event_nor_a_previous_row(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_score(db, obj, 10, Zone.green, ago(days=3))
    add_score(db, obj, 99, Zone.red, ago(days=2), ScoreTrigger.replay)
    add_score(db, obj, 98, Zone.red, ago(hours=1), ScoreTrigger.replay)
    changed = add_score(db, obj, 30, Zone.yellow, ago(minutes=30))
    # A replay-only object (history rebuilt, never scored live) produces nothing.
    replayed = make_object(db, world.ust, "Только история")
    add_score(db, replayed, 10, Zone.green, ago(hours=3), ScoreTrigger.replay)
    add_score(db, replayed, 80, Zone.red, ago(hours=2), ScoreTrigger.replay)

    (event,) = feed(client, world.users["mio_ust"])["items"]

    assert event["id"] == f"score_changed:{changed.id}"
    assert (event["score_before"], event["score_after"]) == (10, 30)


def test_signal_created_and_sent(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "ЖК Север")
    auto = add_card(db, obj, ago(hours=3))
    sent = add_card(db, obj, ago(hours=2), sent_at=ago(minutes=10), origin=SignalOrigin.manual)

    items = {item["id"]: item for item in feed(client, world.users["mio_ust"])["items"]}

    assert set(items) == {
        f"signal_created:{auto.id}",
        f"signal_created:{sent.id}",
        f"signal_sent:{sent.id}",
    }
    created = items[f"signal_created:{auto.id}"]
    assert created["kind"] == "signal_created"
    assert created["signal_id"] == auto.id
    assert created["number"] == auto.number
    assert created["origin"] == "auto"
    assert created["object_id"] == obj.id
    assert created["object_name"] == "ЖК Север"
    sent_event = items[f"signal_sent:{sent.id}"]
    assert sent_event["kind"] == "signal_sent"
    assert sent_event["number"] == sent.number
    assert sent_event["origin"] == "manual"


def test_events_older_than_the_lookback_are_left_out(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_ad(db, world.ust, created_at=ago(days=8))
    add_score(db, obj, 10, Zone.green, ago(days=9))
    add_score(db, obj, 50, Zone.yellow, ago(days=8))
    add_card(db, obj, ago(days=8), sent_at=ago(days=8))

    assert feed(client, world.users["mio_ust"])["items"] == []


# ---------------------------------------------------------------- order and cursor


def test_without_cursor_the_latest_five_come_newest_first(client: TestClient, db: Session, world: World) -> None:
    created = [add_ad(db, world.ust, created_at=ago(minutes=60 - minute)) for minute in range(8)]

    body = feed(client, world.users["mio_ust"])

    assert ids(body) == [f"ad_received:{ad.id}" for ad in reversed(created[-5:])]
    assert body["cursor"]


def test_empty_feed_returns_a_cursor_that_catches_later_events(client: TestClient, db: Session, world: World) -> None:
    poller = Poller(client, world.users["mio_ust"])
    assert poller.poll() == []

    ad = add_ad(db, world.ust, created_at=ago(seconds=1))

    assert poller.poll() == [f"ad_received:{ad.id}"]


def test_polling_delivers_only_newer_events_once(client: TestClient, db: Session, world: World) -> None:
    poller = Poller(client, world.users["mio_ust"])
    first = add_ad(db, world.ust, created_at=ago(minutes=10))
    assert poller.poll() == [f"ad_received:{first.id}"]
    cursor = poller.cursor

    assert poller.poll() == []  # nothing new, though the grace window sends the last event again

    newer = add_ad(db, world.ust, created_at=ago(minutes=1))
    assert poller.poll() == [f"ad_received:{newer.id}"]
    assert poller.cursor != cursor
    assert poller.poll() == []


def test_equal_timestamps_are_neither_repeated_nor_skipped(client: TestClient, db: Session, world: World) -> None:
    poller = Poller(client, world.users["mio_ust"])
    obj = make_object(db, world.ust)
    moment = ago(minutes=5)
    add_score(db, obj, 10, Zone.green, ago(hours=1))
    first_ad = add_ad(db, world.ust, created_at=moment)
    assert poller.poll() == [f"ad_received:{first_ad.id}"]

    # Everything below shares the cursor's timestamp and arrives after the poll.
    second_ad = add_ad(db, world.ust, created_at=moment)
    score = add_score(db, obj, 50, Zone.yellow, moment)
    card = add_card(db, obj, moment)
    sent_card = add_card(db, obj, ago(hours=1), sent_at=moment)

    assert poller.poll() == [
        f"signal_sent:{sent_card.id}",
        f"signal_created:{card.id}",
        f"score_changed:{score.id}",
        f"ad_received:{second_ad.id}",
    ]
    assert poller.poll() == []


def test_a_burst_larger_than_the_limit_is_delivered_in_pages_without_gaps(
    client: TestClient, db: Session, world: World
) -> None:
    poller = Poller(client, world.users["mio_ust"])
    poller.poll()
    moment = ago(minutes=2)
    created = [add_ad(db, world.ust, created_at=moment) for _ in range(7)]

    delivered: list[str] = []
    for expected_size in (3, 3, 1):
        fresh = poller.poll(limit=3)
        assert len(fresh) == expected_size
        delivered.extend(reversed(fresh))  # pages are newest first; reading them oldest first rebuilds the order

    assert delivered == [f"ad_received:{ad.id}" for ad in created]
    assert poller.poll(limit=3) == []


# ---------------------------------------------------------------- late rows and the grace window


def test_a_row_committed_after_a_newer_event_is_still_delivered(client: TestClient, db: Session, world: World) -> None:
    """A post is dated by the start of its transaction: one that commits late carries a time before the cursor."""
    poller = Poller(client, world.users["mio_ust"])
    newer = add_ad(db, world.ust, created_at=ago(seconds=30))
    assert poller.poll() == [f"ad_received:{newer.id}"]

    late = add_ad(db, world.ust, created_at=ago(seconds=75))

    assert poller.poll() == [f"ad_received:{late.id}"]
    assert poller.poll() == []


def test_a_late_row_of_every_kind_is_delivered(client: TestClient, db: Session, world: World) -> None:
    poller = Poller(client, world.users["mio_ust"])
    obj = make_object(db, world.ust)
    add_score(db, obj, 10, Zone.green, ago(hours=1))
    newest = add_ad(db, world.ust, created_at=ago(seconds=10))
    assert poller.poll() == [f"ad_received:{newest.id}"]

    score = add_score(db, obj, 50, Zone.yellow, ago(seconds=60))
    card = add_card(db, obj, ago(seconds=50), sent_at=ago(seconds=40))

    assert set(poller.poll()) == {
        f"score_changed:{score.id}",
        f"signal_created:{card.id}",
        f"signal_sent:{card.id}",
    }


def test_the_cursor_never_moves_back_when_late_rows_are_sent(client: TestClient, db: Session, world: World) -> None:
    poller = Poller(client, world.users["mio_ust"])
    add_ad(db, world.ust, created_at=ago(seconds=30))
    poller.poll()
    assert poller.cursor is not None
    before, _ = decode_cursor(poller.cursor)

    add_ad(db, world.ust, created_at=ago(seconds=75))
    assert len(poller.poll()) == 1
    assert poller.cursor is not None
    after, _ = decode_cursor(poller.cursor)

    assert after == before


def test_a_row_older_than_the_grace_window_is_not_looked_for(client: TestClient, db: Session, world: World) -> None:
    poller = Poller(client, world.users["mio_ust"])
    add_ad(db, world.ust, created_at=ago(seconds=30))
    poller.poll()

    add_ad(db, world.ust, created_at=ago(seconds=30) - GRACE - timedelta(seconds=10))

    assert poller.poll() == []


# ---------------------------------------------------------------- a client that was away


def test_a_cursor_older_than_ten_minutes_gets_the_latest_events_and_a_reset(
    client: TestClient, db: Session, world: World
) -> None:
    user = world.users["mio_ust"]
    created = [add_ad(db, world.ust, created_at=ago(minutes=20 - minute)) for minute in range(8)]
    stale = encode_cursor(Position(ago(minutes=30), 0, 0), ago(minutes=11))

    body = feed(client, user, after=stale)

    assert body["reset"] is True
    assert ids(body) == [f"ad_received:{ad.id}" for ad in reversed(created[-5:])]  # not the 8 since the cursor
    again = feed(client, user, after=body["cursor"])
    assert again["reset"] is False and set(ids(again)) <= set(ids(body))  # no news, only the window


def test_a_quiet_system_does_not_reset_a_client_that_keeps_polling(
    client: TestClient, db: Session, world: World
) -> None:
    """The age that counts is the age of the cursor, not the age of the newest event."""
    user = world.users["mio_ust"]
    add_ad(db, world.ust, created_at=ago(hours=5))
    body = feed(client, user)

    for _ in range(2):
        body = feed(client, user, after=body["cursor"])
        assert body["reset"] is False

    recent = encode_cursor(Position(ago(hours=5), 0, 0), ago(minutes=9))
    assert feed(client, user, after=recent)["reset"] is False


def test_a_first_poll_has_no_reset(client: TestClient, world: World) -> None:
    assert feed(client, world.users["mio_ust"])["reset"] is False


@pytest.mark.parametrize("cursor", ["not-a-cursor", "", "bm9wZQ==", "MjAyNi0xMC0xM1QwMDowMDowMHwwfDE="])
def test_malformed_cursor_is_rejected(client: TestClient, world: World, cursor: str) -> None:
    response = client.get(URL, headers=auth(world.users["mio_ust"]), params={"after": cursor})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_cursor"


def test_limit_is_bounded(client: TestClient, world: World) -> None:
    headers = auth(world.users["mio_ust"])

    assert client.get(URL, headers=headers, params={"limit": 0}).status_code == 422
    assert client.get(URL, headers=headers, params={"limit": 101}).status_code == 422


# ---------------------------------------------------------------- scope and roles


def test_feed_is_limited_to_the_users_territory(client: TestClient, db: Session, world: World) -> None:
    ust_object = make_object(db, world.ust, "ЖК Усть")
    semey_object = make_object(db, world.semey, "ЖК Семей")
    ust_ad = add_ad(db, world.ust, created_at=ago(minutes=9))
    semey_ad = add_ad(db, world.semey, created_at=ago(minutes=8))
    foreign_ad = add_ad(db, None, created_at=ago(minutes=7))
    add_score(db, ust_object, 10, Zone.green, ago(hours=2))
    ust_score = add_score(db, ust_object, 50, Zone.yellow, ago(minutes=6))
    add_score(db, semey_object, 10, Zone.green, ago(hours=2))
    semey_score = add_score(db, semey_object, 50, Zone.yellow, ago(minutes=5))
    ust_card = add_card(db, ust_object, ago(minutes=4), sent_at=ago(minutes=3))
    semey_card = add_card(db, semey_object, ago(minutes=2), sent_at=ago(minutes=1))

    expected_ust = {
        f"ad_received:{ust_ad.id}",
        f"score_changed:{ust_score.id}",
        f"signal_created:{ust_card.id}",
        f"signal_sent:{ust_card.id}",
    }
    expected_semey = {
        f"ad_received:{semey_ad.id}",
        f"score_changed:{semey_score.id}",
        f"signal_created:{semey_card.id}",
        f"signal_sent:{semey_card.id}",
    }
    assert visible(client, world.users["mio_ust"]) == expected_ust
    assert visible(client, world.users["mio_semey"]) == expected_semey
    assert visible(client, world.users["mio_region"]) == expected_ust | expected_semey
    assert visible(client, world.users["admin_semey"]) == expected_semey
    assert visible(client, world.users["admin"]) == expected_ust | expected_semey | {f"ad_received:{foreign_ad.id}"}


@pytest.mark.parametrize("role", ["admin", "mio_ust"])
def test_registry_roles_can_read_the_feed(client: TestClient, world: World, role: str) -> None:
    assert client.get(URL, headers=auth(world.users[role])).status_code == 200


@pytest.mark.parametrize("role", ["gask", "law"])
def test_receiving_bodies_get_403(client: TestClient, world: World, role: str) -> None:
    assert client.get(URL, headers=auth(world.users[role])).status_code == 403


def test_anonymous_request_is_rejected(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
