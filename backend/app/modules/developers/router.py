import re
from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app import audit
from app.deps import PageDep, ScopeDep, SessionDep, StaffUser
from app.errors import api_error
from app.models import Developer
from app.modules.developers.schemas import DeveloperCreate, DeveloperOut, DeveloperUpdate
from app.modules.developers.service import get_visible_developer, visible_developers
from app.schemas import Page

router = APIRouter(prefix="/developers", tags=["developers"])

BIN_PATTERN = re.compile(r"[0-9]{12}")


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("", response_model=Page[DeveloperOut])
def list_developers(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    page: PageDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[DeveloperOut]:
    """Developers of the user's territory. A full 12-digit BIN finds any developer: BINs are public and
    this is how an officer links a developer that is registered elsewhere."""
    stmt = select(Developer)
    if q and BIN_PATTERN.fullmatch(q.strip()):
        stmt = stmt.where(Developer.bin == q.strip())
    else:
        stmt = stmt.where(visible_developers(scope))
        if q:
            pattern = f"%{_escape_like(q.lower())}%"
            stmt = stmt.where(
                func.lower(Developer.name).like(pattern, escape="\\") | Developer.bin.like(pattern, escape="\\")
            )
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(stmt.order_by(Developer.name, Developer.id).limit(page.limit).offset(page.offset)).all()
    return Page(items=[DeveloperOut.model_validate(row) for row in rows], total=total)


@router.post("", response_model=DeveloperOut, status_code=201)
def create_developer(body: DeveloperCreate, session: SessionDep, user: StaffUser, request: Request) -> DeveloperOut:
    if session.scalar(select(Developer.id).where(Developer.bin == body.bin)):
        raise api_error(409, "developer_bin_taken", "Застройщик с таким БИН уже существует")
    developer = Developer(**body.model_dump())
    session.add(developer)
    session.flush()
    audit.record(session, user, "developer.create", "developer", developer.id, None, audit.snapshot(developer), request)
    session.commit()
    return DeveloperOut.model_validate(developer)


@router.patch("/{developer_id}", response_model=DeveloperOut)
def update_developer(
    developer_id: int, body: DeveloperUpdate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> DeveloperOut:
    developer = get_visible_developer(session, scope, developer_id)
    before = audit.snapshot(developer)
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None and field in {"name", "founders", "phones"}:
            raise api_error(422, "validation_error", "Поле не может быть пустым")
        setattr(developer, field, value)
    session.flush()
    audit.record(
        session, user, "developer.update", "developer", developer.id, before, audit.snapshot(developer), request
    )
    session.commit()
    return DeveloperOut.model_validate(developer)
