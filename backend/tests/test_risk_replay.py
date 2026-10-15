"""Replayed score history (SPEC 10.5): facts limited to what was dated by the slice, stored rows, idempotence,
and the guarantees that a replay is a read-only reconstruction (no notifications, no change of the object)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Complaint, ConstructionObject, Document, Notification, RiskScore, SignalCard
from app.models.enums import (
    AdStatus,
    CheckStatus,
    ComplaintStatus,
    DetectedBy,
    DocType,
    NotificationKind,
    PhraseCategory,
    ScoreTrigger,
    Zone,
)
from app.modules.risk import service
from app.modules.risk.queries import latest_score_stmt
from app.modules.risk.replay import replay_history
from tests.conftest import World, auth, make_object
from tests.support_risk import add_ad, add_document, add_inspection

DAY = timedelta(days=1)
# Yesterday at noon in Almaty: in the past (a replay never reaches the future), far from the midnight where
# the UTC and local dates differ.
BASE = (datetime.now(UTC) - DAY).replace(hour=7, minute=0, second=0, microsecond=0)
DEPOSIT = ((PhraseCategory.deposit, DetectedBy.dictionary, None),)


def ago(days: int) -> datetime:
    return BASE - days * DAY


def slice_at(db: Session, obj: ConstructionObject, moment: datetime) -> RiskScore:
    assert replay_history(db, obj, moment, moment, DAY) == 1
    return db.scalars(
        select(RiskScore).where(
            RiskScore.object_id == obj.id, RiskScore.trigger == ScoreTrigger.replay, RiskScore.calculated_at == moment
        )
    ).one()


def fired(row: RiskScore) -> set[str]:
    return {factor["code"] for factor in row.breakdown["factors"] if factor["triggered"]}


def flags(row: RiskScore) -> set[str]:
    return {item["code"] for item in row.breakdown["needs_check"]}


def replay_rows(db: Session, obj: ConstructionObject) -> list[RiskScore]:
    return list(
        db.scalars(
            select(RiskScore)
            .where(RiskScore.object_id == obj.id, RiskScore.trigger == ScoreTrigger.replay)
            .order_by(RiskScore.calculated_at)
        )
    )


def real_rows(db: Session, obj: ConstructionObject) -> list[tuple[int, datetime]]:
    return [
        (row.id, row.calculated_at)
        for row in db.scalars(
            select(RiskScore)
            .where(RiskScore.object_id == obj.id, RiskScore.trigger != ScoreTrigger.replay)
            .order_by(RiskScore.id)
        )
    ]


def add_complaint(
    db: Session,
    obj: ConstructionObject,
    received_days_ago: int,
    *,
    verified_days_ago: int | None = None,
    is_verified: bool | None = None,
    status: ComplaintStatus = ComplaintStatus.in_review,
) -> Complaint:
    complaint = Complaint(
        object_id=obj.id,
        received_at=ago(received_days_ago).date(),
        is_collective=True,
        status=status,
        is_verified=verified_days_ago is not None if is_verified is None else is_verified,
        verified_at=ago(verified_days_ago) if verified_days_ago is not None else None,
    )
    db.add(complaint)
    db.flush()
    return complaint


# ---------------------------------------------------------------- facts as of the slice


def test_ads_count_by_their_timestamp_inside_the_window_ending_at_the_slice(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_ad(db, obj, ago(45), hits=DEPOSIT)

    assert fired(slice_at(db, obj, ago(50))) == set()  # not published yet
    inside = slice_at(db, obj, ago(40))
    assert fired(inside) == {"r2_money_offer", "r3_active_ads"} and (inside.score, inside.zone) == (35, Zone.yellow)
    assert fired(slice_at(db, obj, ago(10))) == set()  # published more than ad_window_days (30) before the slice


def test_ad_status_and_phrase_hits_are_read_as_they_are_now(db: Session, world: World) -> None:
    unconfirmed_link = make_object(db, world.ust, "ЖК Без привязки")
    add_ad(db, unconfirmed_link, ago(20), hits=DEPOSIT, status=AdStatus.verification)
    rejected = make_object(db, world.ust, "ЖК Отклонено")
    add_ad(db, rejected, ago(20), hits=((PhraseCategory.deposit, DetectedBy.dictionary, False),))

    row = slice_at(db, unconfirmed_link, ago(10))
    assert fired(row) == set() and flags(row) == {"legal_basis_unknown", "link_unverified"}
    assert fired(slice_at(db, rejected, ago(10))) == {"r3_active_ads"}


def test_complaints_are_known_from_the_day_received_and_verified_from_the_verification_time(
    db: Session, world: World
) -> None:
    obj = make_object(db, world.ust)
    add_complaint(db, obj, received_days_ago=40, verified_days_ago=10)

    before = slice_at(db, obj, ago(50))
    assert fired(before) == set() and flags(before) == {"legal_basis_unknown"}  # not received yet
    unverified = slice_at(db, obj, ago(20))
    assert fired(unverified) == set() and "complaint_unverified" in flags(unverified)  # received, not verified
    verified = slice_at(db, obj, ago(5))
    assert fired(verified) == {"r4_collective_complaint"} and "complaint_unverified" not in flags(verified)
    assert verified.score == 15


def test_a_verified_complaint_without_a_verification_time_counts_from_the_moment_it_was_entered(
    db: Session, world: World
) -> None:
    obj = make_object(db, world.ust)
    complaint = add_complaint(db, obj, received_days_ago=40, is_verified=True)
    complaint.created_at = ago(10)
    db.flush()

    assert fired(slice_at(db, obj, ago(20))) == set()
    assert fired(slice_at(db, obj, ago(5))) == {"r4_collective_complaint"}


def test_document_checks_count_from_their_check_date(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    for doc_type, days in ((DocType.guarantee, 20), (DocType.dsu_permit, 10)):
        add_document(db, obj, doc_type, CheckStatus.not_found).checked_at = ago(days)
    db.flush()

    assert flags(slice_at(db, obj, ago(30))) == {"legal_basis_unknown"}  # nothing checked yet
    one_checked = slice_at(db, obj, ago(15))
    assert fired(one_checked) == set() and flags(one_checked) == {"legal_basis_unknown"}  # one type is not enough
    both = slice_at(db, obj, ago(5))
    assert fired(both) == {"r1_no_legal_basis"} and both.breakdown["legal_basis_status"] == "absent_established"


def test_a_document_without_a_check_date_is_known_from_the_moment_it_was_entered(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    for doc_type in (DocType.guarantee, DocType.dsu_permit):
        document = Document(object_id=obj.id, doc_type=doc_type, check_status=CheckStatus.not_found, created_at=ago(10))
        db.add(document)
    db.flush()

    assert fired(slice_at(db, obj, ago(20))) == set()
    assert fired(slice_at(db, obj, ago(5))) == {"r1_no_legal_basis"}


def test_inspections_count_from_their_date(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, readiness_actual_pct=30)
    add_ad(db, obj, ago(25), claimed_readiness_pct=80)
    add_inspection(db, obj, ago(10).date(), pct=30)

    before = slice_at(db, obj, ago(15))
    assert "r5_readiness_mismatch" not in fired(before) and "readiness_unverified" in flags(before)
    after = slice_at(db, obj, ago(5))
    assert "r5_readiness_mismatch" in fired(after) and "readiness_unverified" not in flags(after)


# ---------------------------------------------------------------- stored slices


def test_slices_are_stored_with_the_trigger_the_date_and_the_full_breakdown(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_ad(db, obj, ago(25), hits=DEPOSIT)

    assert replay_history(db, obj, ago(30), ago(0), 10 * DAY) == 4

    rows = replay_rows(db, obj)
    assert [row.calculated_at for row in rows] == [ago(30), ago(20), ago(10), ago(0)]
    assert [(row.score, row.zone) for row in rows] == [(0, Zone.green)] + [(35, Zone.yellow)] * 3
    assert {row.trigger for row in rows} == {ScoreTrigger.replay}
    assert rows[1].zone_reasons == ["score_25_59"]
    assert [factor["code"] for factor in rows[1].breakdown["factors"]] == [
        "r1_no_legal_basis",
        "r2_money_offer",
        "r3_active_ads",
        "r4_collective_complaint",
        "r5_readiness_mismatch",
        "r6_stalled_or_delayed",
    ]
    [evidence] = next(f for f in rows[1].breakdown["factors"] if f["code"] == "r2_money_offer")["evidence"]
    assert evidence["type"] == "ad_post" and evidence["fragment"] == "бронь"


def test_a_replay_changes_neither_the_object_nor_anyone_else(
    client: TestClient,
    db: Session,
    world: World,
    sent_tasks: list[tuple[str, tuple[object, ...]]],
) -> None:
    obj = make_object(db, world.ust)
    for doc_type in (DocType.guarantee, DocType.dsu_permit):
        add_document(db, obj, doc_type, CheckStatus.not_found).checked_at = ago(40)
    add_ad(db, obj, ago(35), hits=DEPOSIT)
    db.flush()
    before = {name: getattr(obj, name) for name in ("score", "zone", "key_status", "last_scored_at", "next_check_at")}
    notifications = db.scalar(select(func.count()).select_from(Notification))
    sent_tasks.clear()

    replay_history(db, obj, ago(60), ago(0), 7 * DAY)

    assert Zone.red in {row.zone for row in replay_rows(db, obj)}  # it did reach the red zone in the past
    db.refresh(obj)
    assert {name: getattr(obj, name) for name in before} == before
    assert db.scalar(select(func.count()).select_from(Notification)) == notifications
    assert db.scalars(select(Notification).where(Notification.kind == NotificationKind.red_zone)).first() is None
    assert db.scalars(select(SignalCard).where(SignalCard.object_id == obj.id)).first() is None
    assert sent_tasks == []


def test_slices_stop_before_the_first_real_score(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_ad(db, obj, ago(25), hits=DEPOSIT)
    service.recalculate(db, obj.id, ScoreTrigger.event, ago(3))
    service.recalculate(db, obj.id, ScoreTrigger.manual, ago(1))

    assert replay_history(db, obj, ago(10), ago(0), DAY) == 7

    assert [row.calculated_at for row in replay_rows(db, obj)] == [ago(days) for days in range(10, 3, -1)]
    assert replay_history(db, obj, ago(3), ago(0), DAY) == 0  # nothing is left before the first real score


def test_the_first_real_score_is_the_earliest_of_any_non_replay_trigger(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    service.recalculate(db, obj.id, ScoreTrigger.schedule, ago(6))
    service.recalculate(db, obj.id, ScoreTrigger.manual, ago(2))

    replay_history(db, obj, ago(10), ago(0), DAY)

    assert max(row.calculated_at for row in replay_rows(db, obj)) == ago(7)


def test_no_slice_is_stored_in_the_future(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)

    replay_history(db, obj, ago(2), datetime.now(UTC) + 5 * DAY, DAY)

    assert max(row.calculated_at for row in replay_rows(db, obj)) <= datetime.now(UTC)


def test_the_step_must_be_positive(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    with pytest.raises(ValueError, match="step"):
        replay_history(db, obj, ago(10), ago(0), timedelta(0))


# ---------------------------------------------------------------- repeating a replay


def test_a_second_run_replaces_the_replay_rows_of_its_range_and_nothing_else(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_ad(db, obj, ago(25), hits=DEPOSIT)
    service.recalculate(db, obj.id, ScoreTrigger.event, ago(0))
    replay_history(db, obj, ago(60), ago(5), 5 * DAY)
    real = real_rows(db, obj)
    outside = replay_rows(db, obj)[0]

    # The same days again, a day later: the slices of the first run inside the new range go, the older stay.
    replay_history(db, obj, ago(50), ago(4), 5 * DAY)

    rows = replay_rows(db, obj)
    assert outside.id == rows[0].id and outside.calculated_at == ago(60)
    assert [row.calculated_at for row in rows] == [ago(60), ago(55), *(ago(days) for days in range(50, 4, -5))]
    assert real_rows(db, obj) == real


def test_a_second_run_sees_the_facts_that_were_added_since(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    replay_history(db, obj, ago(10), ago(5), DAY)
    assert {row.score for row in replay_rows(db, obj)} == {0}

    add_ad(db, obj, ago(12), hits=DEPOSIT)
    replay_history(db, obj, ago(10), ago(5), DAY)

    assert [row.score for row in replay_rows(db, obj)] == [35] * 6


# ---------------------------------------------------------------- what the rest of the system sees


def test_replay_rows_never_replace_the_current_score_but_show_in_the_history(
    client: TestClient, db: Session, world: World
) -> None:
    obj = make_object(db, world.ust)
    add_ad(db, obj, ago(25), hits=DEPOSIT)
    real = service.recalculate(db, obj.id, ScoreTrigger.event, ago(2))
    assert real is not None
    # Stored after the real score (a higher id) yet dated before it.
    replay_history(db, obj, ago(20), ago(0), DAY)
    headers = auth(world.users["mio_ust"])

    assert db.scalar(latest_score_stmt(obj.id)) == real.risk_score
    latest = client.get(f"/api/v1/objects/{obj.id}", headers=headers).json()["latest_score"]
    assert datetime.fromisoformat(latest["calculated_at"]) == real.risk_score.calculated_at

    body = client.get(f"/api/v1/objects/{obj.id}/score-history", headers=headers, params={"limit": 100}).json()
    times = [item["calculated_at"] for item in body["items"]]
    assert times == sorted(times, reverse=True)
    assert body["items"][0]["trigger"] == "event"
    assert {item["trigger"] for item in body["items"]} == {"event", "replay"}
    assert sum(item["trigger"] == "replay" for item in body["items"]) == 18


def test_an_object_with_only_replayed_history_has_no_current_score(
    client: TestClient, db: Session, world: World
) -> None:
    """Replay writes slices up to `end` when nothing was calculated yet: they are not the current breakdown."""
    obj = make_object(db, world.ust)
    add_ad(db, obj, ago(25), hits=DEPOSIT)
    assert replay_history(db, obj, ago(20), ago(0), DAY) == 21
    assert replay_rows(db, obj)

    assert db.scalar(latest_score_stmt(obj.id)) is None
    detail = client.get(f"/api/v1/objects/{obj.id}", headers=auth(world.users["mio_ust"])).json()
    assert detail["latest_score"] is None


def test_the_red_zone_notice_ignores_replayed_history(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    for doc_type in (DocType.guarantee, DocType.dsu_permit):
        add_document(db, obj, doc_type, CheckStatus.not_found).checked_at = ago(40)
    add_ad(db, obj, ago(2), hits=DEPOSIT)
    real = service.recalculate(db, obj.id, ScoreTrigger.event, ago(1))
    assert real is not None and real.entered_red
    # Stored later than the red score, so with higher ids: green and yellow slices must not look like a streak.
    replay_history(db, obj, ago(60), ago(2), 3 * DAY)
    assert {row.zone for row in replay_rows(db, obj)} >= {Zone.green, Zone.yellow}

    notice = service.notify_red_zone(db, obj.id)

    assert notice is not None and notice.notified >= 1
    notifications = list(db.scalars(select(Notification).where(Notification.kind == NotificationKind.red_zone)))
    assert len(notifications) == notice.notified
    assert {item.payload["risk_score_id"] for item in notifications} == {real.risk_score.id}


def test_the_object_stays_unscored_when_only_replayed(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    replay_history(db, obj, ago(10), ago(0), 5 * DAY)
    db.refresh(obj)
    assert (obj.score, obj.zone, obj.last_scored_at) == (None, None, None)


def test_an_object_that_does_not_exist_cannot_be_replayed(db: Session, world: World) -> None:
    ghost = ConstructionObject(id=10**9, territory_id=world.ust.id, name="призрак")
    with pytest.raises(ValueError, match="does not exist"):
        replay_history(db, ghost, ago(10), ago(0), DAY)
