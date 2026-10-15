"""Risk recalculation: load the facts of an object, evaluate them and persist the result (SPEC section 6)."""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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
    session: Session, obj: ConstructionObject, settings: AppSettings, now: datetime
) -> engine.ScoringInput:
    documents = [
        engine.DocumentFact(id=row.id, doc_type=row.doc_type, check_status=row.check_status)
        for row in session.scalars(
            select(Document)
            .where(Document.object_id == obj.id, Document.doc_type.in_(engine.PERMIT_DOC_TYPES))
            .order_by(Document.id)
        )
    ]
    window_start = now - timedelta(days=settings.ad_window_days)
    ad_rows = session.execute(
        select(AdPost.id, AdPost.payment_schemes, AdPost.price_before_completion)
        .where(AdPost.object_id == obj.id, window_start <= AD_TIMESTAMP)
        .order_by(AD_TIMESTAMP.desc(), AdPost.id.desc())
    ).all()
    hits_by_ad: dict[int, list[engine.HitFact]] = defaultdict(list)
    if ad_rows:
        for hit in session.scalars(select(PhraseHit).where(PhraseHit.ad_post_id.in_([row.id for row in ad_rows]))):
            hits_by_ad[hit.ad_post_id].append(
                engine.HitFact(category=hit.category, detected_by=hit.detected_by, confirmed=hit.confirmed)
            )
    complaints = [
        engine.ComplaintFact(
            id=row.id, is_collective=row.is_collective, status=row.status, confirmed_payments=row.confirmed_payments
        )
        for row in session.scalars(select(Complaint).where(Complaint.object_id == obj.id).order_by(Complaint.id))
    ]
    latest = session.execute(
        select(Inspection.id, Inspection.inspected_at)
        .where(Inspection.object_id == obj.id)
        .order_by(Inspection.inspected_at.desc(), Inspection.id.desc())
        .limit(1)
    ).first()
    return engine.ScoringInput(
        obj=engine.ObjectFact(
            construction_status=obj.construction_status,
            planned_completion=obj.planned_completion,
            forecast_completion=obj.forecast_completion,
            stalled_since=obj.stalled_since,
            readiness_actual_pct=obj.readiness_actual_pct,
            readiness_claimed_pct=obj.readiness_claimed_pct,
        ),
        documents=documents,
        ads=[
            engine.AdFact(
                id=row.id,
                payment_schemes=tuple(row.payment_schemes),
                price_before_completion=row.price_before_completion,
                hits=tuple(hits_by_ad[row.id]),
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


def recalculate(
    session: Session, object_id: int, trigger: ScoreTrigger = ScoreTrigger.event, now: datetime | None = None
) -> RecalcResult | None:
    """Score one object and store the result (flushed, not committed). None if the object does not exist.

    The object row is locked for the duration of the transaction, so two recalculations of the same object
    run one after another and the "entered red" decision is made once. `FOR NO KEY UPDATE` is enough for
    that and, unlike `FOR UPDATE`, does not block other transactions adding documents or complaints.
    """
    obj = session.scalar(
        select(ConstructionObject)
        .where(ConstructionObject.id == object_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if obj is None:
        return None
    # Taken after the lock: a calculation that waited for another one must not look older than its result.
    now = now or datetime.now(UTC)
    settings = load_settings(session)
    factors = [
        engine.FactorWeight(code=factor.code, weight=factor.weight)
        for factor in session.scalars(
            select(RiskFactor).where(RiskFactor.is_active.is_(True)).order_by(RiskFactor.sort_order, RiskFactor.code)
        )
    ]
    territory = session.get(Territory, obj.territory_id)
    if territory is None:
        raise ValueError(f"object {obj.id} has no territory")
    evaluation = engine.evaluate(
        load_scoring_input(session, obj, settings, now),
        factors,
        settings,
        signals.local_today(territory.timezone, now),
    )

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
    last_non_red = (
        select(func.max(RiskScore.id))
        .where(RiskScore.object_id == obj.id, RiskScore.zone != Zone.red)
        .scalar_subquery()
    )
    # The first red score of the current streak identifies this entry into the red zone.
    entry_score_id = session.scalar(
        select(func.min(RiskScore.id)).where(
            RiskScore.object_id == obj.id, RiskScore.zone == Zone.red, RiskScore.id > func.coalesce(last_non_red, 0)
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
