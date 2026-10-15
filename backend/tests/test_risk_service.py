"""Recalculation against a real database: facts from rows, persistence, schedule, red-zone reactions."""

from collections.abc import Callable
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import (
    AppUser,
    AuditLog,
    ConstructionObject,
    Notification,
    RiskFactor,
    RiskScore,
    SignalCard,
)
from app.models.enums import (
    CheckStatus,
    ComplaintStatus,
    ConstructionStatus,
    DetectedBy,
    DocType,
    KeyStatus,
    NotificationKind,
    PhraseCategory,
    Role,
    ScoreTrigger,
    SignalOrigin,
    SignalStatus,
    Zone,
)
from app.modules.risk import service, tasks
from app.modules.settings.service import save_settings
from tests.conftest import World, make_object
from tests.support_risk import (
    NOW,
    add_ad,
    add_complaint,
    add_document,
    add_inspection,
    red_object,
)

BOOKING = ((PhraseCategory.booking, DetectedBy.dictionary, None),)


def recalc(db: Session, obj: ConstructionObject, trigger: ScoreTrigger = ScoreTrigger.event) -> service.RecalcResult:
    result = service.recalculate(db, obj.id, trigger, NOW)
    assert result is not None
    return result


def cards(db: Session, obj: ConstructionObject) -> list[SignalCard]:
    return list(db.scalars(select(SignalCard).where(SignalCard.object_id == obj.id).order_by(SignalCard.id)))


# ---------------------------------------------------------------- persistence and schedule


def test_recalculation_stores_score_and_updates_the_object(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_document(db, obj, DocType.dsu_permit)
    result = recalc(db, obj, ScoreTrigger.manual)

    stored = db.scalars(select(RiskScore).where(RiskScore.object_id == obj.id)).one()
    assert stored.id == result.risk_score.id
    assert (stored.score, stored.zone, stored.trigger, stored.calculated_at) == (
        0,
        Zone.green,
        ScoreTrigger.manual,
        NOW,
    )
    assert stored.zone_reasons == ["permit_confirmed"]
    assert [item["code"] for item in stored.breakdown] == [
        "no_permit",
        "money_offer",
        "active_ads",
        "complaints",
        "readiness_overstated",
        "on_schedule",
    ]
    db.refresh(obj)
    assert (obj.score, obj.zone, obj.key_status, obj.last_scored_at) == (0, Zone.green, KeyStatus.ok, NOW)


@pytest.mark.parametrize(
    ("build", "zone", "days"),
    [
        (lambda db, world: red_object(db, world.ust), Zone.red, 1),
        (lambda db, world: make_object(db, world.ust), Zone.yellow, 7),
        (lambda db, world: _green_object(db, world), Zone.green, 30),
    ],
)
def test_next_check_depends_on_the_zone(
    db: Session, world: World, build: Callable[[Session, World], ConstructionObject], zone: Zone, days: int
) -> None:
    obj = build(db, world)
    recalc(db, obj)
    assert obj.zone is zone
    assert obj.next_check_at == NOW + timedelta(days=days)


def _green_object(db: Session, world: World) -> ConstructionObject:
    obj = make_object(db, world.ust)
    add_document(db, obj, DocType.guarantee)
    return obj


def test_check_intervals_are_taken_from_settings(db: Session, world: World) -> None:
    save_settings(db, {"yellow_interval_days": 3, "green_interval_days": 10})
    yellow, green = make_object(db, world.ust), _green_object(db, world)
    recalc(db, yellow)
    recalc(db, green)
    assert yellow.next_check_at == NOW + timedelta(days=3)
    assert green.next_check_at == NOW + timedelta(days=10)


def test_every_recalculation_appends_to_the_history(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    recalc(db, obj)
    recalc(db, obj)
    assert len(db.scalars(select(RiskScore).where(RiskScore.object_id == obj.id)).all()) == 2


def test_missing_object_is_reported_as_none(db: Session, world: World) -> None:
    assert service.recalculate(db, 999_999, ScoreTrigger.event, NOW) is None


def test_the_object_row_is_locked_without_blocking_child_inserts(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    statements: list[str] = []
    connection = db.connection()
    event.listen(connection, "before_cursor_execute", lambda *args: statements.append(args[2]))
    recalc(db, obj)
    locking = [sql for sql in statements if "FROM construction_object" in sql and "FOR " in sql]
    assert locking
    assert "FOR NO KEY UPDATE" in locking[0]


# ---------------------------------------------------------------- facts from rows


def test_ads_count_only_inside_the_window(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_ad(db, obj, NOW - timedelta(days=8), hits=BOOKING)
    assert recalc(db, obj).evaluation.facts.active_ads is False
    add_ad(db, obj, NOW - timedelta(days=6, hours=23))
    result = recalc(db, obj)
    assert result.evaluation.facts.active_ads is True
    assert result.evaluation.facts.money_offer is False  # the booking ad is outside the window


def test_window_follows_the_setting(db: Session, world: World) -> None:
    save_settings(db, {"ad_window_days": 14})
    obj = make_object(db, world.ust)
    add_ad(db, obj, NOW - timedelta(days=10), hits=BOOKING)
    assert recalc(db, obj).evaluation.facts.money_offer is True


def test_ads_of_other_objects_are_ignored(db: Session, world: World) -> None:
    obj, other = make_object(db, world.ust), make_object(db, world.ust, "ЖК Другой")
    add_ad(db, other, hits=BOOKING)
    assert recalc(db, obj).evaluation.facts.active_ads is False


@pytest.mark.parametrize(
    ("detected_by", "confirmed", "counts"),
    [
        (DetectedBy.dictionary, None, True),
        (DetectedBy.dictionary, True, True),
        (DetectedBy.dictionary, False, False),
        (DetectedBy.llm, None, False),
        (DetectedBy.llm, False, False),
        (DetectedBy.llm, True, True),
    ],
)
def test_phrase_hits_count_by_origin_and_confirmation(
    db: Session, world: World, detected_by: DetectedBy, confirmed: bool | None, counts: bool
) -> None:
    obj = make_object(db, world.ust)
    add_ad(db, obj, hits=((PhraseCategory.booking, detected_by, confirmed),))
    result = recalc(db, obj)
    assert result.evaluation.facts.money_offer is counts
    assert (result.evaluation.zone is Zone.red) is counts


def test_confirmed_payment_scheme_is_a_money_offer(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_ad(db, obj, payment_schemes=("installment",))
    result = recalc(db, obj)
    assert result.evaluation.zone is Zone.red
    money = next(item for item in result.risk_score.breakdown if item["code"] == "money_offer")
    assert money["detail"]["payment_schemes"] == ["installment"]


def test_breakdown_evidence_refers_to_the_rows(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    document = add_document(db, obj, DocType.dsu_permit, CheckStatus.checking)
    ad = add_ad(db, obj, hits=BOOKING)
    complaint = add_complaint(db, obj, collective=True)
    inspection = add_inspection(db, obj)
    breakdown = {item["code"]: item for item in recalc(db, obj).risk_score.breakdown}
    assert breakdown["no_permit"]["evidence"] == [{"type": "document", "id": document.id}]
    assert breakdown["money_offer"]["evidence"] == [{"type": "ad_post", "id": ad.id}]
    assert breakdown["active_ads"]["evidence"] == [{"type": "ad_post", "id": ad.id}]
    assert breakdown["complaints"]["evidence"] == [{"type": "complaint", "id": complaint.id}]
    obj.readiness_claimed_pct, obj.readiness_actual_pct = 90, 40
    db.flush()
    again = {item["code"]: item for item in recalc(db, obj).risk_score.breakdown}
    assert again["readiness_overstated"]["evidence"] == [{"type": "inspection", "id": inspection.id}]
    assert again["readiness_overstated"]["detail"]["gap_pp"] == 50


def test_confirmed_payments_complaint_without_permit_is_red(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_complaint(db, obj, confirmed_payments=True, status=ComplaintStatus.closed)
    result = recalc(db, obj)
    assert result.evaluation.zone is Zone.red
    assert result.risk_score.zone_reasons == ["no_permit", "confirmed_payments"]


def test_closing_the_only_collective_complaint_lets_the_object_turn_green(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_document(db, obj, DocType.dsu_permit)
    complaint = add_complaint(db, obj, collective=True)
    assert recalc(db, obj).risk_score.zone is Zone.yellow
    complaint.status = ComplaintStatus.closed
    db.flush()
    result = recalc(db, obj)
    assert (result.risk_score.zone, result.risk_score.score) == (Zone.green, 0)


def test_on_schedule_uses_the_latest_inspection(db: Session, world: World) -> None:
    obj = make_object(
        db,
        world.ust,
        construction_status=ConstructionStatus.active,
        planned_completion=NOW.date() + timedelta(days=200),
        forecast_completion=NOW.date() + timedelta(days=200),
    )
    add_document(db, obj, DocType.dsu_permit)
    add_inspection(db, obj, NOW.date() - timedelta(days=90))
    assert recalc(db, obj).evaluation.facts.on_schedule is False
    add_inspection(db, obj, NOW.date() - timedelta(days=3))
    result = recalc(db, obj)
    assert result.evaluation.facts.on_schedule is True
    assert result.risk_score.score == 0


def test_stalled_object_reports_its_downtime(db: Session, world: World) -> None:
    obj = make_object(
        db,
        world.ust,
        construction_status=ConstructionStatus.stalled,
        stalled_since=NOW.date() - timedelta(days=45),
    )
    add_document(db, obj, DocType.dsu_permit)
    result = recalc(db, obj)
    assert obj.key_status is KeyStatus.stalled
    assert result.evaluation.key_status_detail == {"stalled_days": 45}


def test_object_dates_are_read_in_the_territory_time_zone(db: Session, world: World) -> None:
    # 20:00 UTC on 12 Oct is already 13 Oct in Almaty: a plan ending on the 12th is overdue there.
    late = datetime(2026, 10, 12, 20, 0, tzinfo=UTC)
    obj = make_object(db, world.ust, planned_completion=date(2026, 10, 12))
    add_document(db, obj, DocType.dsu_permit)
    result = service.recalculate(db, obj.id, ScoreTrigger.event, late)
    assert result is not None
    assert result.evaluation.facts.overdue is True


def test_inactive_factor_is_left_out_of_the_score_but_not_of_the_zone(db: Session, world: World) -> None:
    obj = red_object(db, world.ust)
    assert recalc(db, obj).risk_score.score == 40 + 20 + 15
    db.get_one(RiskFactor, "money_offer").is_active = False
    db.flush()
    result = recalc(db, obj)
    assert result.risk_score.score == 40 + 15
    assert "money_offer" not in {item["code"] for item in result.risk_score.breakdown}
    assert result.risk_score.zone is Zone.red


def test_changed_weight_is_used_by_the_next_calculation(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    assert recalc(db, obj).risk_score.score == 40
    db.get_one(RiskFactor, "no_permit").weight = 55
    db.flush()
    assert recalc(db, obj).risk_score.score == 55


# ---------------------------------------------------------------- red zone


def test_entering_red_creates_one_auto_draft(db: Session, world: World) -> None:
    obj = red_object(db, world.ust)
    first = recalc(db, obj)
    assert first.entered_red is True
    [card] = cards(db, obj)
    assert (card.origin, card.status, card.created_by) == (SignalOrigin.auto, SignalStatus.requires_confirmation, None)
    assert card.id == first.signal_card_id
    assert card.number == "SQ-2026-0001"
    assert card.sections["risk_factors"], "the draft carries the factors of the score that turned the object red"
    entry = db.scalars(
        select(AuditLog).where(AuditLog.entity_type == "signal_card", AuditLog.entity_id == card.id)
    ).one()
    assert (entry.action, entry.user_id) == ("signal_card.create", None)

    second = recalc(db, obj)
    assert second.entered_red is False
    assert second.signal_card_id is None
    assert len(cards(db, obj)) == 1


def test_object_that_is_not_red_gets_no_draft(db: Session, world: World) -> None:
    result = recalc(db, make_object(db, world.ust))
    assert result.entered_red is False
    assert result.signal_card_id is None


@pytest.mark.parametrize("status", [SignalStatus.requires_confirmation, SignalStatus.returned, SignalStatus.sent])
def test_open_card_prevents_a_second_draft(db: Session, world: World, status: SignalStatus) -> None:
    obj = red_object(db, world.ust)
    db.add(SignalCard(number="SQ-2026-9001", object_id=obj.id, origin=SignalOrigin.manual, status=status, sections={}))
    db.flush()
    result = recalc(db, obj)
    assert result.entered_red is True
    assert result.signal_card_id is None
    assert len(cards(db, obj)) == 1


@pytest.mark.parametrize("status", [SignalStatus.responded, SignalStatus.closed])
def test_finished_card_does_not_prevent_a_new_draft(db: Session, world: World, status: SignalStatus) -> None:
    obj = red_object(db, world.ust)
    db.add(SignalCard(number="SQ-2026-9001", object_id=obj.id, origin=SignalOrigin.manual, status=status, sections={}))
    db.flush()
    assert recalc(db, obj).signal_card_id is not None
    assert len(cards(db, obj)) == 2


def test_leaving_and_re_entering_red_counts_as_a_new_entry(db: Session, world: World) -> None:
    obj = red_object(db, world.ust)
    assert recalc(db, obj).entered_red is True
    permit = add_document(db, obj, DocType.dsu_permit)
    left = recalc(db, obj)
    assert (left.risk_score.zone, left.entered_red) == (Zone.green, False)
    db.delete(permit)
    db.flush()
    back = recalc(db, obj)
    assert back.entered_red is True
    assert back.signal_card_id is None  # the first draft still waits for confirmation


def test_recalc_task_announces_the_entry_once(
    db: Session, world: World, sent_tasks: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: lambda: nullcontext(db))
    obj = red_object(db, world.ust)
    tasks.recalc_object(obj.id)
    tasks.recalc_object(obj.id)
    assert sent_tasks.count(("notify.red_zone", (obj.id,))) == 1
    assert db.scalars(select(RiskScore).where(RiskScore.object_id == obj.id)).all()[0].trigger is ScoreTrigger.event
    assert len(cards(db, obj)) == 1


def test_recalc_task_ignores_a_deleted_object(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: lambda: nullcontext(db))
    tasks.recalc_object(999_999)  # logs and returns; nothing to assert beyond not raising


# ---------------------------------------------------------------- sweep


def test_sweep_recalculates_due_and_unscored_objects_only(
    db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: lambda: nullcontext(db))
    started = datetime.now(UTC)
    due = make_object(db, world.ust, "due", next_check_at=started - timedelta(days=1), score=1, zone=Zone.green)
    never = make_object(db, world.ust, "never")
    later = make_object(db, world.ust, "later", next_check_at=started + timedelta(days=5), score=1, zone=Zone.green)
    later_check = later.next_check_at

    assert tasks.sweep_due() == 2

    for obj in (due, never):
        db.refresh(obj)
        assert obj.last_scored_at is not None
        assert obj.next_check_at is not None and obj.next_check_at > started
    db.refresh(later)
    assert (later.score, later.next_check_at) == (1, later_check)
    assert {score.trigger for score in db.scalars(select(RiskScore))} == {ScoreTrigger.schedule}


def test_sweep_continues_after_a_failure(db: Session, world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: lambda: nullcontext(db))
    broken, fine = make_object(db, world.ust, "broken"), make_object(db, world.ust, "fine")
    db.commit()  # the sweep rolls back the failing object only; the fixture data must survive that
    original = tasks.recalculate

    def flaky(session: Session, object_id: int, trigger: ScoreTrigger) -> service.RecalcResult | None:
        if object_id == broken.id:
            raise RuntimeError("boom")
        return original(session, object_id, trigger)

    monkeypatch.setattr(tasks, "recalculate", flaky)
    assert tasks.sweep_due() == 1
    db.refresh(fine)
    assert fine.last_scored_at is not None


# ---------------------------------------------------------------- notify.red_zone


def _red_scored(db: Session, world: World) -> ConstructionObject:
    obj = red_object(db, world.ust)
    recalc(db, obj)
    return obj


def _notifications(db: Session, obj: ConstructionObject) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(Notification.kind == NotificationKind.red_zone, Notification.entity_id == obj.id)
        )
    )


def test_red_zone_notifies_mio_officers_whose_scope_covers_the_object(db: Session, world: World) -> None:
    inactive = AppUser(username="t_mio_off", full_name="x", password_hash="x", role=Role.mio_officer, is_active=False)
    db.add(inactive)
    db.flush()
    obj = _red_scored(db, world)

    notice = service.notify_red_zone(db, obj.id)

    assert notice is not None and notice.notified == 2
    recipients = {item.user_id for item in _notifications(db, obj)}
    assert recipients == {world.users["mio_ust"].id, world.users["mio_region"].id}
    sample = _notifications(db, obj)[0]
    assert sample.entity_type == "object"
    assert sample.payload["object_name"] == obj.name
    assert sample.payload["score"] == obj.score


def test_red_zone_notification_is_idempotent_per_stay_in_red(db: Session, world: World) -> None:
    obj = _red_scored(db, world)
    service.notify_red_zone(db, obj.id)
    again = service.notify_red_zone(db, obj.id)
    assert again is not None and again.notified == 0
    recalc(db, obj)  # still red: the same stay
    still = service.notify_red_zone(db, obj.id)
    assert still is not None and still.notified == 0
    assert len(_notifications(db, obj)) == 2

    # Leaves red and comes back: a new entry, announced again.
    obj.zone = Zone.yellow
    db.add(RiskScore(object_id=obj.id, score=10, zone=Zone.yellow, breakdown=[], trigger=ScoreTrigger.event))
    db.flush()
    recalc(db, obj)
    entered = service.notify_red_zone(db, obj.id)
    assert entered is not None and entered.notified == 2
    assert len(_notifications(db, obj)) == 4


def test_red_zone_notification_is_skipped_when_the_object_left_red(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    recalc(db, obj)
    assert service.notify_red_zone(db, obj.id) is None
    assert service.notify_red_zone(db, 999_999) is None
    assert _notifications(db, obj) == []


def test_red_zone_task_sends_mail_to_mio_addresses_once(
    db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: lambda: nullcontext(db))
    sent: list[tuple[list[str], str, str]] = []
    monkeypatch.setattr(
        tasks.mail, "send_email", lambda to, subject, body, attachment=None: sent.append((to, subject, body))
    )
    save_settings(db, {"recipient_emails": {"mio": ["mio@example.kz"], "gask": [], "law_enforcement": []}})
    obj = _red_scored(db, world)

    assert tasks.red_zone(obj.id) == 2
    assert tasks.red_zone(obj.id) == 0  # redelivered: no new notifications, no second mail

    assert len(sent) == 1
    recipients, subject, body = sent[0]
    assert recipients == ["mio@example.kz"]
    assert obj.name in subject
    assert "не установленную виновность" in body


def test_red_zone_task_without_smtp_only_creates_notifications(
    db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: lambda: nullcontext(db))
    obj = _red_scored(db, world)
    assert tasks.red_zone(obj.id) == 2  # SMTP_HOST is empty in tests: send_email is a no-op
    assert tasks.red_zone(999_999) == 0
