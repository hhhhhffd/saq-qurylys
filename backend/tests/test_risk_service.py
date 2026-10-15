"""Recalculation against a real database: facts from rows, persistence, schedule, red-zone reactions."""

from collections.abc import Callable
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import (
    AppUser,
    AuditLog,
    ConstructionObject,
    Notification,
    PhraseHit,
    RiskFactor,
    RiskScore,
    SignalCard,
)
from app.models.enums import (
    AdStatus,
    CheckStatus,
    ComplaintStatus,
    ConstructionStatus,
    DetectedBy,
    DocType,
    KeyStatus,
    LegalBasisStatus,
    NotificationKind,
    PhraseCategory,
    Role,
    ScoreTrigger,
    SignalOrigin,
    SignalStatus,
    Zone,
)
from app.modules.risk import engine, service, tasks
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

DEPOSIT = ((PhraseCategory.deposit, DetectedBy.dictionary, None),)


def recalc(db: Session, obj: ConstructionObject, trigger: ScoreTrigger = ScoreTrigger.event) -> service.RecalcResult:
    result = service.recalculate(db, obj.id, trigger, NOW)
    assert result is not None
    return result


def cards(db: Session, obj: ConstructionObject) -> list[SignalCard]:
    return list(db.scalars(select(SignalCard).where(SignalCard.object_id == obj.id).order_by(SignalCard.id)))


def factor(result: service.RecalcResult, code: str) -> dict[str, Any]:
    return next(item for item in result.risk_score.breakdown["factors"] if item["code"] == code)


def flags(result: service.RecalcResult) -> list[str]:
    return [item["code"] for item in result.risk_score.breakdown["needs_check"]]


def confirmed_basis(db: Session, obj: ConstructionObject) -> None:
    add_document(db, obj, DocType.guarantee, CheckStatus.confirmed)


# ---------------------------------------------------------------- mandatory scenarios of the case (SPEC 6.6)


def test_scenario_a_unknown_basis_with_a_paid_booking_is_yellow_without_r1(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_ad(db, obj, hits=DEPOSIT)  # the legal basis was never checked: no documents

    result = recalc(db, obj)

    assert (result.risk_score.score, result.risk_score.zone) == (35, Zone.yellow)  # R2 25 + R3 10
    assert result.risk_score.zone_reasons == ["score_25_59"]
    assert not factor(result, engine.R1)["triggered"]
    assert flags(result) == ["legal_basis_unknown"]
    assert result.risk_score.breakdown["legal_basis_status"] == "unknown"
    assert (obj.score, obj.zone, obj.key_status) == (35, Zone.yellow, KeyStatus.money_offer)
    assert result.entered_red is False and cards(db, obj) == []


def test_scenario_b_established_absence_with_a_deposit_is_red_with_one_auto_draft(db: Session, world: World) -> None:
    obj = red_object(db, world.ust)

    result = recalc(db, obj)

    assert (result.risk_score.score, result.risk_score.zone) == (70, Zone.red)  # R1 35 + R2 25 + R3 10
    assert result.risk_score.zone_reasons == ["r1_and_r2"]
    assert result.risk_score.breakdown["legal_basis_status"] == "absent_established"
    assert flags(result) == []
    assert (obj.zone, obj.key_status) == (Zone.red, KeyStatus.no_legal_basis_with_offer)
    assert result.entered_red is True
    [card] = cards(db, obj)
    assert (card.origin, card.status) == (SignalOrigin.auto, SignalStatus.requires_confirmation)
    assert recalc(db, obj).signal_card_id is None  # no second draft
    assert len(cards(db, obj)) == 1


def test_scenario_c_confirmed_guarantee_without_a_permit_and_plain_ads_is_green(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_document(db, obj, DocType.guarantee, CheckStatus.confirmed)  # no dsu_permit at all
    add_ad(db, obj)  # an ordinary advertisement without an offer of money

    result = recalc(db, obj)

    assert (result.risk_score.score, result.risk_score.zone) == (10, Zone.green)  # R3 only
    assert result.risk_score.zone_reasons == ["score_0_24"]
    assert not factor(result, engine.R1)["triggered"]
    assert flags(result) == []
    assert (obj.zone, obj.key_status) == (Zone.green, KeyStatus.active_ads)
    assert result.entered_red is False and cards(db, obj) == []


# ---------------------------------------------------------------- persistence and schedule


def test_recalculation_stores_the_breakdown_object(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    confirmed_basis(db, obj)
    result = recalc(db, obj, ScoreTrigger.manual)

    stored = db.scalars(select(RiskScore).where(RiskScore.object_id == obj.id)).one()
    assert stored.id == result.risk_score.id
    assert (stored.score, stored.zone, stored.trigger, stored.calculated_at) == (
        0,
        Zone.green,
        ScoreTrigger.manual,
        NOW,
    )
    assert set(stored.breakdown) == {"factors", "needs_check", "legal_basis_status"}
    assert [(item["code"], item["label"]) for item in stored.breakdown["factors"]] == [
        ("r1_no_legal_basis", "R1"),
        ("r2_money_offer", "R2"),
        ("r3_active_ads", "R3"),
        ("r4_collective_complaint", "R4"),
        ("r5_readiness_mismatch", "R5"),
        ("r6_stalled_or_delayed", "R6"),
    ]
    assert stored.breakdown["legal_basis_status"] == LegalBasisStatus.confirmed.value
    db.refresh(obj)
    assert (obj.score, obj.zone, obj.key_status, obj.last_scored_at) == (0, Zone.green, KeyStatus.ok, NOW)


@pytest.mark.parametrize(
    ("build", "zone", "days"),
    [
        (lambda db, world: red_object(db, world.ust), Zone.red, 1),
        (lambda db, world: _yellow_object(db, world), Zone.yellow, 7),
        (lambda db, world: make_object(db, world.ust), Zone.green, 30),
    ],
)
def test_next_check_depends_on_the_zone(
    db: Session, world: World, build: Callable[[Session, World], ConstructionObject], zone: Zone, days: int
) -> None:
    obj = build(db, world)
    recalc(db, obj)
    assert obj.zone is zone
    assert obj.next_check_at == NOW + timedelta(days=days)


def _yellow_object(db: Session, world: World) -> ConstructionObject:
    obj = make_object(db, world.ust)
    add_ad(db, obj, hits=DEPOSIT)
    return obj


def test_check_intervals_are_taken_from_settings(db: Session, world: World) -> None:
    save_settings(db, {"yellow_interval_days": 3, "green_interval_days": 10})
    yellow, green = _yellow_object(db, world), make_object(db, world.ust)
    recalc(db, yellow)
    recalc(db, green)
    assert yellow.next_check_at == NOW + timedelta(days=3)
    assert green.next_check_at == NOW + timedelta(days=10)


def test_zone_thresholds_are_taken_from_settings(db: Session, world: World) -> None:
    save_settings(db, {"zone_yellow_min": 40, "zone_red_min": 80})
    obj = _yellow_object(db, world)  # 35
    assert recalc(db, obj).risk_score.zone is Zone.green
    red = red_object(db, world.ust)  # 70
    assert recalc(db, red).risk_score.zone is Zone.yellow


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


# ---------------------------------------------------------------- legal basis from documents


@pytest.mark.parametrize(
    ("documents", "status", "r1"),
    [
        ([], LegalBasisStatus.unknown, False),
        ([(DocType.guarantee, CheckStatus.confirmed)], LegalBasisStatus.confirmed, False),
        ([(DocType.dsu_permit, CheckStatus.confirmed)], LegalBasisStatus.confirmed, False),
        (
            [(DocType.guarantee, CheckStatus.not_found), (DocType.dsu_permit, CheckStatus.not_found)],
            LegalBasisStatus.absent_established,
            True,
        ),
        ([(DocType.guarantee, CheckStatus.not_found)], LegalBasisStatus.unknown, False),  # only one type checked
        ([(DocType.dsu_permit, CheckStatus.not_found)], LegalBasisStatus.unknown, False),
        ([(DocType.dsu_permit, CheckStatus.checking)], LegalBasisStatus.unknown, False),  # a check is running
        (
            [(DocType.guarantee, CheckStatus.not_found), (DocType.dsu_permit, CheckStatus.checking)],
            LegalBasisStatus.unknown,
            False,
        ),
        ([(DocType.psd, CheckStatus.confirmed)], LegalBasisStatus.unknown, False),  # not a legal basis
    ],
)
def test_legal_basis_status_from_documents(
    db: Session, world: World, documents: list[tuple[DocType, CheckStatus]], status: LegalBasisStatus, r1: bool
) -> None:
    obj = make_object(db, world.ust)
    for doc_type, check_status in documents:
        add_document(db, obj, doc_type, check_status)
    result = recalc(db, obj)
    assert result.risk_score.breakdown["legal_basis_status"] == status.value
    assert factor(result, engine.R1)["triggered"] is r1
    assert ("legal_basis_unknown" in flags(result)) is (status is LegalBasisStatus.unknown)


def test_unknown_basis_is_never_red_even_with_every_other_signal(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_document(db, obj, DocType.guarantee, CheckStatus.not_found)  # the permit was not checked
    add_ad(db, obj, hits=DEPOSIT)
    add_complaint(db, obj, collective=True, verified=True, confirmed_payments=True)
    result = recalc(db, obj)
    assert result.risk_score.zone is Zone.yellow
    assert result.risk_score.score == 25 + 10 + 15


# ---------------------------------------------------------------- facts from rows


def test_ads_count_only_inside_the_window(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_ad(db, obj, NOW - timedelta(days=31), hits=DEPOSIT)
    assert factor(recalc(db, obj), engine.R3)["triggered"] is False
    add_ad(db, obj, NOW - timedelta(days=29, hours=23))
    result = recalc(db, obj)
    assert factor(result, engine.R3)["triggered"] is True
    assert factor(result, engine.R2)["triggered"] is False  # the deposit ad is outside the window


def test_window_follows_the_setting(db: Session, world: World) -> None:
    save_settings(db, {"ad_window_days": 7})
    obj = make_object(db, world.ust)
    add_ad(db, obj, NOW - timedelta(days=10), hits=DEPOSIT)
    assert factor(recalc(db, obj), engine.R2)["triggered"] is False
    save_settings(db, {"ad_window_days": 14})
    assert factor(recalc(db, obj), engine.R2)["triggered"] is True


def test_ads_of_other_objects_are_ignored(db: Session, world: World) -> None:
    obj, other = make_object(db, world.ust), make_object(db, world.ust, "ЖК Другой")
    add_ad(db, other, hits=DEPOSIT)
    assert factor(recalc(db, obj), engine.R3)["triggered"] is False


def test_completed_object_has_no_active_ads_factor(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, construction_status=ConstructionStatus.completed)
    add_ad(db, obj)
    assert factor(recalc(db, obj), engine.R3)["triggered"] is False


@pytest.mark.parametrize(
    ("detected_by", "confirmed", "r2", "pending"),
    [
        (DetectedBy.dictionary, None, True, False),
        (DetectedBy.dictionary, True, True, False),
        (DetectedBy.dictionary, False, False, False),  # rejected by an analyst
        (DetectedBy.llm, None, False, True),  # an AI hypothesis: not a fact, but worth a look
        (DetectedBy.llm, False, False, False),
        (DetectedBy.llm, True, True, False),
    ],
)
def test_phrase_hits_count_by_origin_and_confirmation(
    db: Session, world: World, detected_by: DetectedBy, confirmed: bool | None, r2: bool, pending: bool
) -> None:
    obj = make_object(db, world.ust)
    add_document(db, obj, DocType.guarantee, CheckStatus.confirmed)
    add_ad(db, obj, hits=((PhraseCategory.deposit, detected_by, confirmed),))
    result = recalc(db, obj)
    assert factor(result, engine.R2)["triggered"] is r2
    assert ("ai_hypotheses_pending" in flags(result)) is pending


def test_confirmed_payment_scheme_is_a_money_offer(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_ad(db, obj, payment_schemes=("installment",))
    result = recalc(db, obj)
    assert factor(result, engine.R2)["detail"]["payment_schemes"] == ["installment"]


def test_unverified_link_is_counted_but_flagged(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    confirmed_basis(db, obj)
    add_ad(db, obj, status=AdStatus.verification)
    result = recalc(db, obj)
    assert factor(result, engine.R3)["triggered"] is True
    assert flags(result) == ["link_unverified"]


def test_r2_evidence_quotes_the_phrase_of_the_publication(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    ad = add_ad(db, obj, hits=DEPOSIT)
    hit = db.scalars(select(PhraseHit).where(PhraseHit.ad_post_id == ad.id)).one()
    [ref] = factor(recalc(db, obj), engine.R2)["evidence"]
    assert ref == {"type": "ad_post", "id": ad.id, "phrase_hit_id": hit.id, "fragment": "бронь"}


def test_breakdown_evidence_refers_to_the_rows(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    guarantee = add_document(db, obj, DocType.guarantee, CheckStatus.not_found)
    permit = add_document(db, obj, DocType.dsu_permit, CheckStatus.not_found)
    ad = add_ad(db, obj, hits=DEPOSIT, claimed_readiness_pct=90)
    complaint = add_complaint(db, obj, collective=True, verified=True)
    inspection = add_inspection(db, obj, NOW.date() - timedelta(days=2), pct=40)
    obj.readiness_claimed_pct, obj.readiness_actual_pct = 90, 40
    db.flush()

    result = recalc(db, obj)

    assert factor(result, engine.R1)["evidence"] == [
        {"type": "document", "id": guarantee.id},
        {"type": "document", "id": permit.id},
    ]
    assert [ref["id"] for ref in factor(result, engine.R2)["evidence"]] == [ad.id]
    assert factor(result, engine.R3)["evidence"] == [{"type": "ad_post", "id": ad.id}]
    assert factor(result, engine.R4)["evidence"] == [{"type": "complaint", "id": complaint.id}]
    assert factor(result, engine.R5)["evidence"] == [
        {"type": "inspection", "id": inspection.id},
        {"type": "ad_post", "id": ad.id},
    ]
    assert factor(result, engine.R5)["detail"]["gap_pp"] == 50


# ---------------------------------------------------------------- R4, R5, R6 from rows


def test_collective_complaint_counts_once_verified_and_not_closed(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    confirmed_basis(db, obj)
    complaint = add_complaint(db, obj, collective=True)
    unverified = recalc(db, obj)
    assert factor(unverified, engine.R4)["triggered"] is False
    assert flags(unverified) == ["complaint_unverified"]

    complaint.is_verified = True
    db.flush()
    verified = recalc(db, obj)
    assert factor(verified, engine.R4)["triggered"] is True
    assert (verified.risk_score.score, verified.risk_score.zone) == (15, Zone.green)
    assert flags(verified) == [] and obj.key_status is KeyStatus.collective_complaint

    complaint.status = ComplaintStatus.closed
    db.flush()
    closed = recalc(db, obj)
    assert factor(closed, engine.R4)["triggered"] is False
    assert obj.key_status is KeyStatus.ok


def test_readiness_mismatch_needs_a_confirmed_publication_and_an_inspection(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, readiness_claimed_pct=90)
    confirmed_basis(db, obj)
    add_ad(db, obj, claimed_readiness_pct=90)
    # A claim without a photo inspection: a flag, no points.
    claim_only = recalc(db, obj)
    assert factor(claim_only, engine.R5)["triggered"] is False
    assert flags(claim_only) == ["readiness_unverified"]

    add_inspection(db, obj, NOW.date() - timedelta(days=1), pct=60)
    obj.readiness_actual_pct = 60
    db.flush()
    both = recalc(db, obj)
    assert factor(both, engine.R5)["triggered"] is True  # 30 points apart
    assert flags(both) == []
    assert obj.key_status is KeyStatus.readiness_mismatch


def test_readiness_values_without_a_source_are_not_enough(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, readiness_claimed_pct=95, readiness_actual_pct=10)
    confirmed_basis(db, obj)
    add_inspection(db, obj, NOW.date(), pct=10)  # the photo exists, but no publication carries the claim
    assert factor(recalc(db, obj), engine.R5)["triggered"] is False


def test_stalled_branch_of_r6(db: Session, world: World) -> None:
    obj = make_object(
        db, world.ust, construction_status=ConstructionStatus.stalled, stalled_since=NOW.date() - timedelta(days=45)
    )
    confirmed_basis(db, obj)
    result = recalc(db, obj)
    assert factor(result, engine.R6)["triggered"] is True
    assert (obj.key_status, result.evaluation.key_status_detail) == (KeyStatus.stalled, {"stalled_days": 45})
    obj.stalled_since = NOW.date() - timedelta(days=5)
    db.flush()
    assert factor(recalc(db, obj), engine.R6)["triggered"] is False  # a fresh stop is not yet a downtime


def test_delayed_branch_of_r6(db: Session, world: World) -> None:
    obj = make_object(
        db,
        world.ust,
        planned_completion=NOW.date() + timedelta(days=100),
        forecast_completion=NOW.date() + timedelta(days=200),
    )
    confirmed_basis(db, obj)
    result = recalc(db, obj)
    assert factor(result, engine.R6)["triggered"] is True  # the forecast is 100 days behind the plan
    assert obj.key_status is KeyStatus.delayed
    obj.forecast_completion = NOW.date() + timedelta(days=150)
    db.flush()
    assert factor(recalc(db, obj), engine.R6)["triggered"] is False  # 50 days: not significant


def test_object_dates_are_read_in_the_territory_time_zone(db: Session, world: World) -> None:
    # 20:00 UTC on 12 Oct is already 13 Oct in Almaty: a plan that passed 91 days before the 13th is delayed there only.
    late = datetime(2026, 10, 12, 20, 0, tzinfo=UTC)
    obj = make_object(db, world.ust, planned_completion=date(2026, 10, 13) - timedelta(days=91))
    confirmed_basis(db, obj)
    result = service.recalculate(db, obj.id, ScoreTrigger.event, late)
    assert result is not None
    assert factor(result, engine.R6)["triggered"] is True


# ---------------------------------------------------------------- weights and activity


def test_inactive_factor_is_left_out_of_the_score_and_cannot_make_the_zone_red(db: Session, world: World) -> None:
    obj = red_object(db, world.ust)
    assert recalc(db, obj).risk_score.zone is Zone.red
    db.get_one(RiskFactor, engine.R1).is_active = False
    db.flush()
    result = recalc(db, obj)
    assert "r1_no_legal_basis" not in {item["code"] for item in result.risk_score.breakdown["factors"]}
    assert (result.risk_score.score, result.risk_score.zone) == (35, Zone.yellow)  # R2 25 + R3 10


def test_changed_weight_is_used_by_the_next_calculation(db: Session, world: World) -> None:
    obj = red_object(db, world.ust)
    assert recalc(db, obj).risk_score.score == 70
    db.get_one(RiskFactor, engine.R3).weight = 20
    db.flush()
    assert recalc(db, obj).risk_score.score == 80


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
    permit = add_document(db, obj, DocType.dsu_permit)  # a confirmed permit: the basis is no longer absent
    left = recalc(db, obj)
    assert (left.risk_score.zone, left.entered_red) == (Zone.yellow, False)  # R2 25 + R3 10
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
