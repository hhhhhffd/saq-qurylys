"""Queries shared by the risk and signals modules."""

from sqlalchemy import Select, func, select

from app.models import AdPost, RiskScore
from app.models.enums import ScoreTrigger

# A publication is dated by when it was published, else when it was captured, else when it was entered.
AD_TIMESTAMP = func.coalesce(AdPost.published_at, AdPost.captured_at, AdPost.created_at)


def latest_score_stmt(object_id: int) -> Select[RiskScore]:
    """The current score of the object: replayed history (SPEC 10.5) reconstructs the past and is never current,
    also when its slices are dated after the last real calculation."""
    # `id` breaks ties between scores calculated in the same instant.
    return (
        select(RiskScore)
        .where(RiskScore.object_id == object_id, RiskScore.trigger != ScoreTrigger.replay)
        .order_by(RiskScore.calculated_at.desc(), RiskScore.id.desc())
        .limit(1)
    )
