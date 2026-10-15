from sqlalchemy import ColumnElement, exists, or_, select, true
from sqlalchemy.orm import Session

from app.errors import api_error
from app.models import ConstructionObject, Developer
from app.scope import TerritoryScope


def visible_developers(scope: TerritoryScope) -> ColumnElement[bool]:
    """Developers have no territory of their own. A developer is visible when it has an object in the
    user's scope, or no objects at all (a freshly registered one)."""
    if scope.is_unrestricted:
        return true()
    has_in_scope = exists().where(
        ConstructionObject.developer_id == Developer.id,
        ConstructionObject.territory_id.in_(scope.ids or ()),
    )
    has_any = exists().where(ConstructionObject.developer_id == Developer.id)
    return or_(has_in_scope, ~has_any)


def get_visible_developer(session: Session, scope: TerritoryScope, developer_id: int) -> Developer:
    developer = session.scalar(select(Developer).where(Developer.id == developer_id, visible_developers(scope)))
    if developer is None:
        raise api_error(404, "developer_not_found", "Застройщик не найден")
    return developer
