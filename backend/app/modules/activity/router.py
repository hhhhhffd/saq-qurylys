from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import ScopeDep, SessionDep, StaffUser
from app.modules.activity import service
from app.modules.activity.schemas import ActivityFeed

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("", response_model=ActivityFeed)
def activity(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    after: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ActivityFeed:
    """Events in the user's territory over the last 7 days. Without `after` the latest 5 and a cursor; with
    `after` (a cursor from an earlier response) the events that followed it, at most `limit`, oldest ones first
    so none are skipped, and the events of the 2 minutes before it again (a row can become visible after a newer
    one: the client skips ids it has). A cursor issued more than 10 minutes ago gets the latest 5 and `reset`.
    Items are newest first."""
    return service.load_feed(session, scope, after, limit)
