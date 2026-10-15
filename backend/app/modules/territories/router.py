import json
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app import audit
from app.deps import AdminUser, CurrentUser, ScopeDep, SessionDep
from app.errors import api_error, forbidden
from app.geo import make_point
from app.models import District, Territory
from app.models.enums import TerritoryLevel
from app.modules.territories.schemas import TerritoryCreate, TerritoryNode, TerritoryUpdate

router = APIRouter(prefix="/territories", tags=["territories"])


def _tree(territories: list[Territory]) -> list[TerritoryNode]:
    nodes = {t.id: TerritoryNode.model_validate(t) for t in territories}
    roots: list[TerritoryNode] = []
    for node in nodes.values():
        parent = nodes.get(node.parent_id) if node.parent_id is not None else None
        (parent.children if parent else roots).append(node)
    return roots


def _get_in_scope(session: SessionDep, scope: ScopeDep, territory_id: int) -> Territory:
    territory = session.get(Territory, territory_id)
    if territory is None or not scope.contains(territory.id):
        raise api_error(404, "territory_not_found", "Территория не найдена")
    return territory


@router.get("", response_model=list[TerritoryNode])
def list_territories(session: SessionDep, user: CurrentUser, scope: ScopeDep) -> list[TerritoryNode]:
    stmt = scope.restrict(select(Territory), Territory.id).order_by(Territory.level.desc(), Territory.name)
    return _tree(list(session.scalars(stmt)))


@router.post("", response_model=TerritoryNode, status_code=201)
def create_territory(
    body: TerritoryCreate, session: SessionDep, admin: AdminUser, scope: ScopeDep, request: Request
) -> TerritoryNode:
    if body.level is TerritoryLevel.region:
        if body.parent_id is not None:
            raise api_error(422, "invalid_parent", "У области не может быть родителя")
        if not scope.is_unrestricted:
            raise forbidden()
    else:
        parent = session.get(Territory, body.parent_id) if body.parent_id is not None else None
        if parent is None or parent.level is not TerritoryLevel.region:
            raise api_error(422, "invalid_parent", "Родителем города должна быть область")
        if not scope.contains(parent.id):
            raise forbidden("Территория вне вашей зоны ответственности")
    if session.scalar(select(Territory.id).where(Territory.code == body.code)):
        raise api_error(409, "territory_code_taken", "Территория с таким кодом уже существует")
    territory = Territory(
        parent_id=body.parent_id,
        level=body.level,
        code=body.code,
        name=body.name,
        timezone=body.timezone,
        center=make_point(body.lat, body.lon),
    )
    session.add(territory)
    session.flush()
    session.refresh(territory)
    audit.record(
        session, admin, "territory.create", "territory", territory.id, None, audit.snapshot(territory), request
    )
    session.commit()
    return TerritoryNode.model_validate(territory)


@router.patch("/{territory_id}", response_model=TerritoryNode)
def update_territory(
    territory_id: int, body: TerritoryUpdate, session: SessionDep, admin: AdminUser, scope: ScopeDep, request: Request
) -> TerritoryNode:
    territory = _get_in_scope(session, scope, territory_id)
    before = audit.snapshot(territory)
    changes = body.model_dump(exclude_unset=True)
    for field in ("name", "timezone"):
        if changes.get(field) is not None:
            setattr(territory, field, changes[field])
    if changes.get("lat") is not None:
        territory.center = make_point(changes["lat"], changes["lon"])
    session.flush()
    session.refresh(territory)
    audit.record(
        session, admin, "territory.update", "territory", territory.id, before, audit.snapshot(territory), request
    )
    session.commit()
    return TerritoryNode.model_validate(territory)


@router.get("/{territory_id}/districts")
def list_districts(territory_id: int, session: SessionDep, user: CurrentUser, scope: ScopeDep) -> dict[str, Any]:
    """Districts of a city as a GeoJSON FeatureCollection."""
    _get_in_scope(session, scope, territory_id)
    rows = session.execute(
        select(District.id, District.name, District.territory_id, func.ST_AsGeoJSON(District.boundary))
        .where(District.territory_id == territory_id)
        .order_by(District.name)
    )
    features = [
        {
            "type": "Feature",
            "id": district_id,
            "properties": {"id": district_id, "name": name, "territory_id": owner_id},
            "geometry": json.loads(geometry) if geometry else None,
        }
        for district_id, name, owner_id, geometry in rows
    ]
    return {"type": "FeatureCollection", "features": features}
