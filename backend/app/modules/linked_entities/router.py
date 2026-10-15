from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app import audit
from app.deps import ScopeDep, SessionDep, StaffUser
from app.errors import api_error
from app.events import object_changed
from app.models import LinkedEntity
from app.modules.developers.service import get_visible_developer
from app.modules.linked_entities.schemas import LinkedEntityCreate, LinkedEntityOut
from app.modules.objects.service import get_object_in_scope

router = APIRouter(tags=["linked-entities"])


def _create(
    session: SessionDep,
    user: StaffUser,
    request: Request,
    body: LinkedEntityCreate,
    *,
    object_id: int | None,
    developer_id: int | None,
) -> LinkedEntity:
    owner = LinkedEntity.object_id == object_id if object_id is not None else LinkedEntity.developer_id == developer_id
    if session.scalar(
        select(LinkedEntity.id).where(owner, LinkedEntity.kind == body.kind, LinkedEntity.value == body.value)
    ):
        raise api_error(409, "linked_entity_exists", "Такая связь уже добавлена")
    entity = LinkedEntity(object_id=object_id, developer_id=developer_id, **body.model_dump())
    session.add(entity)
    session.flush()
    audit.record(
        session, user, "linked_entity.create", "linked_entity", entity.id, None, audit.snapshot(entity), request
    )
    return entity


@router.post("/objects/{object_id}/linked-entities", response_model=LinkedEntityOut, status_code=201)
def create_object_linked_entity(
    object_id: int, body: LinkedEntityCreate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> LinkedEntity:
    obj = get_object_in_scope(session, scope, object_id)
    entity = _create(session, user, request, body, object_id=obj.id, developer_id=None)
    session.commit()
    object_changed(obj.id)
    return entity


@router.post("/developers/{developer_id}/linked-entities", response_model=LinkedEntityOut, status_code=201)
def create_developer_linked_entity(
    developer_id: int, body: LinkedEntityCreate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> LinkedEntity:
    get_visible_developer(session, scope, developer_id)
    entity = _create(session, user, request, body, object_id=None, developer_id=developer_id)
    session.commit()
    return entity


@router.delete("/linked-entities/{entity_id}", status_code=204)
def delete_linked_entity(
    entity_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> Response:
    entity = session.get(LinkedEntity, entity_id)
    if entity is None:
        raise api_error(404, "linked_entity_not_found", "Связь не найдена")
    if entity.object_id is not None:
        get_object_in_scope(session, scope, entity.object_id)
    elif entity.developer_id is not None:
        get_visible_developer(session, scope, entity.developer_id)
    audit.record(
        session, user, "linked_entity.delete", "linked_entity", entity.id, audit.snapshot(entity), None, request
    )
    session.delete(entity)
    session.commit()
    if entity.object_id is not None:
        object_changed(entity.object_id)
    return Response(status_code=204)
