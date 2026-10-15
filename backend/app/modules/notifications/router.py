from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update

from app.deps import CurrentUser, PageDep, SessionDep
from app.errors import api_error
from app.models import Notification
from app.models.enums import NotificationKind
from app.schemas import ORMModel, Page

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(ORMModel):
    id: int
    kind: NotificationKind
    entity_type: str | None
    entity_id: int | None
    payload: Any
    created_at: datetime
    read_at: datetime | None


class ReadAllResult(BaseModel):
    updated: int


@router.get("", response_model=Page[NotificationOut])
def list_notifications(
    session: SessionDep,
    user: CurrentUser,
    page: PageDep,
    unread: Annotated[bool, Query()] = False,
) -> Page[NotificationOut]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(
        stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(page.limit).offset(page.offset)
    ).all()
    return Page(items=[NotificationOut.model_validate(row) for row in rows], total=total)


@router.post("/read-all", response_model=ReadAllResult)
def read_all(session: SessionDep, user: CurrentUser) -> ReadAllResult:
    result = session.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    session.commit()
    return ReadAllResult(updated=result.rowcount)  # type: ignore[attr-defined]


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, session: SessionDep, user: CurrentUser) -> Notification:
    notification = session.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise api_error(404, "notification_not_found", "Уведомление не найдено")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        session.commit()
    return notification
