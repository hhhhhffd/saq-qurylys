from datetime import datetime, timedelta

from sqlalchemy import DateTime, column, select, true, values
from sqlalchemy.orm import Session

from app.models import ConstructionObject, RiskScore
from app.modules.dashboard.schemas import (
    Timeline,
    TimelineFrame,
    TimelineObject,
    TimelineObjectZone,
)
from app.scope import TerritoryScope


def frame_times(start: datetime, end: datetime, step: timedelta) -> list[datetime]:
    """`end`, `end - step`, ... down to `start`, oldest first: the last frame is always `end` ("today")."""
    times = [end - step * index for index in range((end - start) // step + 1)]
    times.reverse()
    return times


def build_timeline(session: Session, scope: TerritoryScope, times: list[datetime]) -> Timeline:
    """For every moment, the latest score (of any trigger) each object in scope had by then. One indexed
    lookup per object and moment (`ix_risk_score_object_calculated`), not a scan of the whole history."""
    moments = values(column("at", DateTime(timezone=True)), name="moment").data([(at,) for at in times])
    latest = (
        select(RiskScore.score, RiskScore.zone)
        .where(RiskScore.object_id == ConstructionObject.id, RiskScore.calculated_at <= moments.c.at)
        .order_by(RiskScore.calculated_at.desc(), RiskScore.id.desc())
        .limit(1)
        .lateral("latest")
    )
    stmt = (
        select(moments.c.at, ConstructionObject.id, latest.c.score, latest.c.zone)
        .select_from(moments)
        .join(ConstructionObject, true())
        .join(latest, true())
        .order_by(moments.c.at, ConstructionObject.id)
    )
    rows = session.execute(scope.restrict(stmt, ConstructionObject.territory_id)).all()

    by_moment: dict[datetime, list[TimelineObjectZone]] = {at: [] for at in times}
    for at, object_id, score, zone in rows:
        by_moment[at].append(TimelineObjectZone(object_id=object_id, score=score, zone=zone))
    object_ids = {object_id for _, object_id, _, _ in rows}
    objects = session.execute(
        select(
            ConstructionObject.id,
            ConstructionObject.name,
            ConstructionObject.lat,
            ConstructionObject.lon,
            ConstructionObject.is_demo,
        )
        .where(ConstructionObject.id.in_(object_ids))
        .order_by(ConstructionObject.id)
    ).all()
    return Timeline(
        frames=[TimelineFrame(at=at, objects=by_moment[at]) for at in times],
        objects=[
            TimelineObject(object_id=row.id, name=row.name, lat=row.lat, lon=row.lon, is_demo=row.is_demo)
            for row in objects
        ],
    )
