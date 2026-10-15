from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.deps import PageDep, ScopeDep, SessionDep, require_roles
from app.models import AppUser, AuditLog, ConstructionObject, SignalCard
from app.models.enums import Role
from app.schemas import ORMModel, Page

router = APIRouter(prefix="/audit", tags=["audit"])

AuditReader = Annotated[AppUser, Depends(require_roles(Role.admin, Role.mio_officer))]


class AuditOut(ORMModel):
    id: int
    user_id: int | None
    username: str | None
    at: datetime
    action: str
    entity_type: str
    entity_id: int | None
    before: Any
    after: Any
    ip: str | None


@router.get("", response_model=Page[AuditOut])
def list_audit(
    session: SessionDep,
    user: AuditReader,
    scope: ScopeDep,
    page: PageDep,
    entity_type: Annotated[str | None, Query(max_length=64)] = None,
    entity_id: Annotated[int | None, Query()] = None,
) -> Page[AuditOut]:
    stmt = select(AuditLog, AppUser.username).outerjoin(AppUser, AppUser.id == AuditLog.user_id)
    if user.role is Role.mio_officer:
        # An officer reads the history of signal cards in their own territory only.
        cards = select(SignalCard.id).join(ConstructionObject, ConstructionObject.id == SignalCard.object_id)
        cards = scope.restrict(cards, ConstructionObject.territory_id)
        stmt = stmt.where(AuditLog.entity_type == "signal_card", AuditLog.entity_id.in_(cards))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.execute(stmt.order_by(AuditLog.at.desc(), AuditLog.id.desc()).limit(page.limit).offset(page.offset))
    items = [
        AuditOut.model_validate(
            {**{c: getattr(entry, c) for c in AuditOut.model_fields if c != "username"}, "username": username}
        )
        for entry, username in rows
    ]
    return Page(items=items, total=total)
