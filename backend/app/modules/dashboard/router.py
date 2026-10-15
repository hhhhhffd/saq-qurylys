from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.deps import ScopeDep, SessionDep, StaffUser
from app.models import ConstructionObject, Territory
from app.models.enums import Zone
from app.modules.dashboard.schemas import Dashboard, DashboardCounts
from app.modules.objects.router import to_row
from app.modules.objects.service import object_rows_stmt

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


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
