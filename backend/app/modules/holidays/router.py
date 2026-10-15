from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, StringConstraints
from sqlalchemy import select

from app import audit
from app.deps import AdminUser, CurrentUser, SessionDep
from app.errors import api_error
from app.models import Holiday
from app.models.enums import HolidayKind
from app.schemas import ORMModel

router = APIRouter(prefix="/holidays", tags=["holidays"])


class HolidayOut(ORMModel):
    day: date
    kind: HolidayKind
    name: str


class HolidayCreate(BaseModel):
    day: date
    kind: HolidayKind
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


@router.get("", response_model=list[HolidayOut])
def list_holidays(
    session: SessionDep, user: CurrentUser, year: Annotated[int | None, Query(ge=2000, le=2100)] = None
) -> list[Holiday]:
    stmt = select(Holiday).order_by(Holiday.day)
    if year is not None:
        stmt = stmt.where(Holiday.day >= date(year, 1, 1), Holiday.day <= date(year, 12, 31))
    return list(session.scalars(stmt))


@router.post("", response_model=HolidayOut, status_code=201)
def create_holiday(body: HolidayCreate, session: SessionDep, admin: AdminUser, request: Request) -> Holiday:
    if session.get(Holiday, body.day) is not None:
        raise api_error(409, "holiday_exists", "Для этой даты запись календаря уже существует")
    holiday = Holiday(day=body.day, kind=body.kind, name=body.name)
    session.add(holiday)
    session.flush()
    audit.record(session, admin, "holiday.create", "holiday", None, None, audit.snapshot(holiday), request)
    session.commit()
    return holiday


@router.delete("/{day}", status_code=204)
def delete_holiday(day: date, session: SessionDep, admin: AdminUser, request: Request) -> Response:
    holiday = session.get(Holiday, day)
    if holiday is None:
        raise api_error(404, "holiday_not_found", "Запись календаря не найдена")
    audit.record(session, admin, "holiday.delete", "holiday", None, audit.snapshot(holiday), None, request)
    session.delete(holiday)
    session.commit()
    return Response(status_code=204)
