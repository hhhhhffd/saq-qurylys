"""In-app notifications addressed by role and territory (shared by the signals and risk modules)."""

from collections.abc import Collection
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import AppUser, Notification, Territory
from app.models.enums import NotificationKind, Role


def users_covering_territory(
    session: Session, territory_id: int, roles: Collection[Role], exclude_user_id: int | None = None
) -> list[AppUser]:
    """Active users of the given roles whose territory scope includes `territory_id`
    (users without a territory see everything)."""
    chain = select(Territory.id, Territory.parent_id).where(Territory.id == territory_id).cte("chain", recursive=True)
    chain = chain.union_all(select(Territory.id, Territory.parent_id).join(chain, Territory.id == chain.c.parent_id))
    stmt = select(AppUser).where(
        AppUser.role.in_(roles),
        AppUser.is_active.is_(True),
        or_(AppUser.territory_id.is_(None), AppUser.territory_id.in_(select(chain.c.id))),
    )
    if exclude_user_id is not None:
        stmt = stmt.where(AppUser.id != exclude_user_id)
    return list(session.scalars(stmt.order_by(AppUser.id)))


def add_notifications(
    session: Session,
    users: Collection[AppUser],
    kind: NotificationKind,
    entity_type: str,
    entity_id: int,
    payload: dict[str, Any],
) -> int:
    for user in users:
        session.add(
            Notification(user_id=user.id, kind=kind, entity_type=entity_type, entity_id=entity_id, payload=payload)
        )
    session.flush()
    return len(users)
