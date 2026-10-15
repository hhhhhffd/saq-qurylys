"""Risk recalculation: load the facts of an object, evaluate them and persist the result (SPEC section 6)."""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AdPost,
    Complaint,
    ConstructionObject,
    Document,
    Inspection,
    Notification,
    PhraseHit,
    RiskFactor,
    RiskScore,
    Territory,
)
from app.models.enums import NotificationKind, Role, ScoreTrigger, SignalOrigin, Zone
from app.modules.risk import engine
from app.modules.risk.queries import AD_TIMESTAMP
from app.modules.settings.service import AppSettings, load_settings
from app.modules.signals import service as signals
from app.modules.signals.notifications import add_notifications, users_covering_territory
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

RED_CHECK_INTERVAL_DAYS = 1


@dataclass(frozen=True)
class RecalcResult:
    risk_score: RiskScore
    evaluation: engine.Evaluation
    entered_red: bool
    signal_card_id: int | None


def load_scoring_input(
    session: Session,
    obj: ConstructionObject,
    settings: AppSettings,
    now: datetime,
    today: date,
    as_of: bool = False,
) -> engine.ScoringInput:
    """The facts the rules read. `today` is `now` as a date in the territory of the object.

    With `as_of`, `now` is a moment in the past that is being reconstructed (SPEC 10.5): only what was dated
    on or before it is loaded. Ads are taken by their timestamp, complaints by `received_at` (a verification
    counts once `verified_at` has come), documents by the check date (`created_at` when it has none), inspections
    by their date. Everything else (ad status, phrase hits, complaint status, the passport of the object) is
    read as it is now: its history is not kept (OPEN_QUESTIONS 34).
    """
    documents_stmt = select(Document).where(
        Document.object_id == obj.id, Document.doc_type.in_(engine.LEGAL_BASIS_DOC_TYPES)
    )
    if as_of:
        documents_stmt = documents_stmt.where(func.coalesce(Document.checked_at, Document.created_at) <= now)
    documents = [
        engine.DocumentFact(id=row.id, doc_type=row.doc_type, check_status=row.check_status)
        for row in session.scalars(documents_stmt.order_by(Document.id))
    ]
    window_start = now - timedelta(days=settings.ad_window_days)
    in_window = AD_TIMESTAMP.between(window_start, now) if as_of else window_start <= AD_TIMESTAMP
    ad_rows = session.execute(
        select(AdPost.id, AdPost.payment_schemes, AdPost.status, AdPost.claimed_readiness_pct)
        .where(AdPost.object_id == obj.id, in_window)
        .order_by(AD_TIMESTAMP.desc(), AdPost.id.desc())
    ).all()
    hits_by_ad: dict[int, list[engine.HitFact]] = defaultdict(list)
    if ad_rows:
        # Ordered, so the evidence list of a breakdown is the same on every calculation.
        for hit in session.scalars(
            select(PhraseHit)
            .where(PhraseHit.ad_post_id.in_([row.id for row in ad_rows]))
            .order_by(PhraseHit.ad_post_id, PhraseHit.start, PhraseHit.id)
        ):
            hits_by_ad[hit.ad_post_id].append(
                engine.HitFact(
                    id=hit.id,
                    category=hit.category,
                    detected_by=hit.detected_by,
                    confirmed=hit.confirmed,
                    fragment=hit.matched_text,
                )
            )
    complaints_stmt = select(Complaint).where(Complaint.object_id == obj.id)
    if as_of:
        complaints_stmt = complaints_stmt.where(Complaint.received_at <= today)
    complaints = [
        engine.ComplaintFact(
            id=row.id,
            is_collective=row.is_collective,
            status=row.status,
            confirmed_payments=row.confirmed_payments,
            is_verified=row.is_verified and (not as_of or (row.verified_at or row.created_at) <= now),
        )
        for row in session.scalars(complaints_stmt.order_by(Complaint.id))
    ]
    inspection_stmt = select(Inspection.id, Inspection.inspected_at).where(Inspection.object_id == obj.id)
    if as_of:
        inspection_stmt = inspection_stmt.where(Inspection.inspected_at <= today)
    latest = session.execute(
        inspection_stmt.order_by(Inspection.inspected_at.desc(), Inspection.id.desc()).limit(1)
    ).first()
    return engine.ScoringInput(
        obj=engine.ObjectFact(
            construction_status=obj.construction_status,
            planned_completion=obj.planned_completion,
            forecast_completion=obj.forecast_completion,
            stalled_since=obj.stalled_since,
            readiness_actual_pct=obj.readiness_actual_pct,
        ),
        documents=documents,
        ads=[
            engine.AdFact(
                id=row.id,
                payment_schemes=tuple(row.payment_schemes),
                hits=tuple(hits_by_ad[row.id]),
                status=row.status,
                claimed_readiness_pct=row.claimed_readiness_pct,
            )
            for row in ad_rows
        ],
        complaints=complaints,
        latest_inspection=engine.InspectionFact(id=latest.id, inspected_at=latest.inspected_at) if latest else None,
    )


def next_check_delta(zone: Zone, settings: AppSettings) -> timedelta:
    days = {
        Zone.red: RED_CHECK_INTERVAL_DAYS,
        Zone.yellow: settings.yellow_interval_days,
        Zone.green: settings.green_interval_days,
    }[zone]
    return timedelta(days=days)


def active_factor_weights(session: Session) -> list[engine.FactorWeight]:
    return [
        engine.FactorWeight(code=factor.code, weight=factor.weight)
        for factor in session.scalars(
            select(RiskFactor).where(RiskFactor.is_active.is_(True)).order_by(RiskFactor.sort_order, RiskFactor.code)
        )
    ]


def evaluate_object(
    session: Session,
    obj: ConstructionObject,
    settings: AppSettings,
    factors: list[engine.FactorWeight],
    now: datetime,
    as_of: bool = False,
) -> engine.Evaluation:
    """Run the rules over the facts of the object at `now` (see `load_scoring_input` for `as_of`)."""
    territory = session.get(Territory, obj.territory_id)
    if territory is None:
        raise ValueError(f"object {obj.id} has no territory")
    today = signals.local_today(territory.timezone, now)
    return engine.evaluate(load_scoring_input(session, obj, settings, now, today, as_of), factors, settings, today)


def recalculate(
    session: Session, object_id: int, trigger: ScoreTrigger = ScoreTrigger.event, now: datetime | None = None
) -> RecalcResult | None:
    """Score one object and store the result (flushed, not committed). None if the object does not exist.

    The object row is locked for the duration of the transaction, so two recalculations of the same object
    run one after another and the "entered red" decision is made once. `FOR NO KEY UPDATE` is enough for
    that and, unlike `FOR UPDATE`, does not block other transactions adding documents or complaints.
    """
    obj = signals.lock_object(session, object_id)
    if obj is None:
        return None
    # Taken after the lock: a calculation that waited for another one must not look older than its result.
    now = now or datetime.now(UTC)
    settings = load_settings(session)
    evaluation = evaluate_object(session, obj, settings, active_factor_weights(session), now)

    risk_score = RiskScore(
        object_id=obj.id,
        score=evaluation.score,
        zone=evaluation.zone,
        zone_reasons=evaluation.zone_reasons,
        breakdown=evaluation.breakdown,
        trigger=trigger,
        calculated_at=now,
    )
    session.add(risk_score)
    entered_red = evaluation.zone is Zone.red and obj.zone is not Zone.red
    obj.score = evaluation.score
    obj.zone = evaluation.zone
    obj.key_status = evaluation.key_status
    obj.last_scored_at = now
    obj.next_check_at = now + next_check_delta(evaluation.zone, settings)
    session.flush()

    card_id = None
    if entered_red and not signals.has_open_card(session, obj.id):
        card_id = signals.create_card(session, obj, SignalOrigin.auto, None, now=now).id
    return RecalcResult(risk_score=risk_score, evaluation=evaluation, entered_red=entered_red, signal_card_id=card_id)


def dispatch_red_zone(object_id: int) -> None:
    """Queue the red-zone notification. Call after the transaction that entered red is committed."""
    if not get_settings().events_enabled:
        return
    try:
        celery_app.send_task("notify.red_zone", args=[object_id], queue="notify", retry=False, ignore_result=True)
    except Exception:
        logger.exception("Failed to enqueue notify.red_zone for object %s", object_id)


@dataclass(frozen=True)
class RedZoneNotice:
    object_code: str
    object_name: str
    address: str | None
    score: int
    notified: int


def notify_red_zone(session: Session, object_id: int) -> RedZoneNotice | None:
    """In-app `red_zone` notifications for the mio officers whose territory covers the object (flushed, not
    committed). Idempotent per stay in red: a redelivered task adds nothing. None if there is nothing to
    announce (the object is gone or has left the red zone since the task was queued)."""
    obj = session.get(ConstructionObject, object_id)
    if obj is None or obj.zone is not Zone.red or obj.score is None:
        return None
    # Replayed history (SPEC 10.5) is stored after the real scores but dated before them: it is not a streak.
    calculated = RiskScore.trigger != ScoreTrigger.replay
    last_non_red = (
        select(func.max(RiskScore.id))
        .where(RiskScore.object_id == obj.id, RiskScore.zone != Zone.red, calculated)
        .scalar_subquery()
    )
    # The first red score of the current streak identifies this entry into the red zone.
    entry_score_id = session.scalar(
        select(func.min(RiskScore.id)).where(
            RiskScore.object_id == obj.id,
            RiskScore.zone == Zone.red,
            RiskScore.id > func.coalesce(last_non_red, 0),
            calculated,
        )
    )
    already = set(
        session.scalars(
            select(Notification.user_id).where(
                Notification.kind == NotificationKind.red_zone,
                Notification.entity_type == "object",
                Notification.entity_id == obj.id,
                Notification.payload["risk_score_id"].as_integer() == entry_score_id,
            )
        )
    )
    addressees = [
        user
        for user in users_covering_territory(session, obj.territory_id, {Role.mio_officer})
        if user.id not in already
    ]
    payload = {
        "object_id": obj.id,
        "object_code": obj.code,
        "object_name": obj.name,
        "score": obj.score,
        "risk_score_id": entry_score_id,
    }
    notified = add_notifications(session, addressees, NotificationKind.red_zone, "object", obj.id, payload)
    return RedZoneNotice(
        object_code=obj.code, object_name=obj.name, address=obj.address, score=obj.score, notified=notified
    )
