"""Replayed history of the risk score (SPEC 10.5): the same engine, run over the facts known at past moments.

A slice is stored as a `RiskScore` with `trigger=replay` dated at the moment it reconstructs. Replay is a
read-only reconstruction: it neither touches the object (zone, key status, next check) nor notifies anyone.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import ConstructionObject, RiskScore
from app.models.enums import ScoreTrigger
from app.modules.risk.service import active_factor_weights, evaluate_object
from app.modules.settings.service import load_settings
from app.modules.signals import service as signals


def replay_history(session: Session, obj: ConstructionObject, start: datetime, end: datetime, step: timedelta) -> int:
    """Score `obj` as of `start`, `start + step`, ... up to `end` and store the slices (flushed, not committed).
    Returns how many were stored.

    Idempotent: the object's earlier replay rows between `start` and `end` are replaced; rows of any other
    trigger are never touched. A slice is not stored at or after the first real score of the object nor in the
    future, so the current score stays the latest row. Facts, weights and settings are the current ones
    except that the facts are limited to what was dated by the slice (`as_of`).
    """
    if step <= timedelta(0):
        raise ValueError("step must be positive")
    # Real calculations take this lock before they read the clock, so none can be stored later with a date
    # earlier than the slices written here.
    if signals.lock_object(session, obj.id) is None:
        raise ValueError(f"object {obj.id} does not exist")
    end = min(end, datetime.now(UTC))
    first_real = session.scalar(
        select(func.min(RiskScore.calculated_at)).where(
            RiskScore.object_id == obj.id, RiskScore.trigger != ScoreTrigger.replay
        )
    )
    session.execute(
        delete(RiskScore).where(
            RiskScore.object_id == obj.id,
            RiskScore.trigger == ScoreTrigger.replay,
            RiskScore.calculated_at.between(start, end),
        )
    )
    settings = load_settings(session)
    factors = active_factor_weights(session)
    stored = 0
    moment = start
    while moment <= end and (first_real is None or moment < first_real):
        evaluation = evaluate_object(session, obj, settings, factors, moment, as_of=True)
        session.add(
            RiskScore(
                object_id=obj.id,
                score=evaluation.score,
                zone=evaluation.zone,
                zone_reasons=evaluation.zone_reasons,
                breakdown=evaluation.breakdown,
                trigger=ScoreTrigger.replay,
                calculated_at=moment,
            )
        )
        stored += 1
        moment += step
    session.flush()
    return stored
