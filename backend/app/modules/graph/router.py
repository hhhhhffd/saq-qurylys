from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy.dialects.postgresql import insert

from app import audit
from app.deps import ScopeDep, SessionDep, StaffUser
from app.errors import api_error
from app.models import DismissedSourceSuggestion
from app.modules.developers.service import get_visible_developer
from app.modules.graph import service, suggestions
from app.modules.graph.schemas import Graph, SourceSuggestion, SuggestionDismiss
from app.modules.objects.service import get_object_in_scope

router = APIRouter(tags=["graph"])


@router.get("/graph", response_model=Graph)
def get_graph(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    object_id: Annotated[int | None, Query()] = None,
    developer_id: Annotated[int | None, Query()] = None,
    territory_id: Annotated[int | None, Query()] = None,
) -> Graph:
    """Links between developers, objects, phones, accounts and publications. One of `object_id`, `developer_id`
    (their two-hop neighbourhood) or `territory_id` narrows the view; without any, it is the whole scope."""
    if sum(param is not None for param in (object_id, developer_id, territory_id)) > 1:
        raise api_error(
            422, "validation_error", "Укажите не более одного из параметров: object_id, developer_id, territory_id"
        )
    if object_id is not None:
        get_object_in_scope(session, scope, object_id)
    if developer_id is not None:
        get_visible_developer(session, scope, developer_id)
    if territory_id is not None:
        scope = service.territory_scope(session, scope, territory_id)
    return service.build_graph(session, scope, object_id=object_id, developer_id=developer_id)


@router.get("/source-suggestions", response_model=list[SourceSuggestion])
def list_source_suggestions(session: SessionDep, user: StaffUser, scope: ScopeDep) -> list[SourceSuggestion]:
    return suggestions.list_suggestions(session, scope)


@router.post("/source-suggestions/dismiss", status_code=204)
def dismiss_source_suggestion(
    body: SuggestionDismiss, session: SessionDep, user: StaffUser, request: Request
) -> Response:
    """Stop suggesting an account. Repeating the call changes nothing."""
    # Deliberately global, not per territory or per user: an account belongs to its platform, not to a territory,
    # so «не предлагать» holds for everybody who could be offered it.
    handle = body.handle.removeprefix("@").lower()
    if not handle:
        raise api_error(422, "validation_error", "Укажите имя аккаунта")
    dismissed_id = session.scalar(
        insert(DismissedSourceSuggestion)
        .values(platform=body.platform, handle=handle, dismissed_by=user.id)
        .on_conflict_do_nothing(index_elements=["platform", "handle"])
        .returning(DismissedSourceSuggestion.id)
    )
    if dismissed_id is not None:
        audit.record(
            session,
            user,
            "source_suggestion.dismiss",
            "source_suggestion",
            dismissed_id,
            None,
            {"platform": body.platform, "handle": handle},
            request,
        )
    session.commit()
    return Response(status_code=204)
