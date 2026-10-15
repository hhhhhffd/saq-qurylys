from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.deps import ScopeDep, SessionDep, StaffUser
from app.errors import api_error
from app.models import ConstructionObject, Territory
from app.models.enums import Zone
from app.modules.dashboard import service
from app.modules.dashboard.schemas import Dashboard, DashboardCounts, Timeline, TimelineStep
from app.modules.objects.router import to_row
from app.modules.objects.service import object_rows_stmt

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DEFAULT_TIMELINE_WEEKS = 26
MAX_TIMELINE_FRAMES = 120
TIMELINE_STEPS = {TimelineStep.week: timedelta(weeks=1), TimelineStep.day: timedelta(days=1)}


@router.get("", response_model=Dashboard)
def dashboard(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    territory_id: Annotated[int | None, Query()] = None,
    district_id: Annotated[int | None, Query()] = None,
) -> Dashboard:
    """Every object in the user's territory (optionally narrowed to a territory subtree or a district),
    most dangerous first, with the zone counters of that same set."""
    stmt = object_rows_stmt(scope, district_id=district_id)
    if territory_id is not None:
        # A region filters by all its cities; objects belong to cities.
        subtree = select(Territory.id).where(Territory.id == territory_id).cte("subtree", recursive=True)
        subtree = subtree.union_all(select(Territory.id).join(subtree, Territory.parent_id == subtree.c.id))
        stmt = stmt.where(ConstructionObject.territory_id.in_(select(subtree.c.id)))
    rows = session.execute(stmt.order_by(ConstructionObject.score.desc().nulls_last(), ConstructionObject.id)).all()

    zones = Counter(obj.zone for obj, _, _ in rows)
    scored_at = [obj.last_scored_at for obj, _, _ in rows if obj.last_scored_at is not None]
    return Dashboard(
        counts=DashboardCounts(
            green=zones[Zone.green],
            yellow=zones[Zone.yellow],
            red=zones[Zone.red],
            unscored=zones[None],
            total=len(rows),
        ),
        last_updated_at=max(scored_at, default=None),
        objects=[to_row(obj, developer_name, district_name) for obj, developer_name, district_name in rows],
    )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@router.get("/timeline", response_model=Timeline)
def timeline(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    step: Annotated[TimelineStep, Query()] = TimelineStep.week,
) -> Timeline:
    """Zones of the objects in scope at past moments (the "time machine" of the map): one frame per step, the
    last one at `to`. Each object has in a frame the latest score it had by then, replayed history included
    (SPEC 10.5). Naive datetimes are UTC; by default the last 26 weeks up to now."""
    end = _utc(end) if end else datetime.now(UTC)
    start = _utc(start) if start else end - timedelta(weeks=DEFAULT_TIMELINE_WEEKS)
    if start > end:
        raise api_error(422, "timeline_range_invalid", "Начало периода позже его конца")
    delta = TIMELINE_STEPS[step]
    if (end - start) // delta + 1 > MAX_TIMELINE_FRAMES:
        raise api_error(
            422, "timeline_too_long", f"Период содержит больше {MAX_TIMELINE_FRAMES} срезов, выберите период короче"
        )
    return service.build_timeline(session, scope, service.frame_times(start, end, delta))
