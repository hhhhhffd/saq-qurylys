from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app import audit
from app.deps import AdminUser, PageDep, ScopeDep, SessionDep
from app.errors import api_error, forbidden
from app.models import AppUser, Territory
from app.models.enums import Role
from app.modules.users.schemas import UserCreate, UserDetail, UserUpdate
from app.schemas import Page
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserDetail])
def list_users(
    session: SessionDep,
    admin: AdminUser,
    scope: ScopeDep,
    page: PageDep,
    role: Annotated[Role | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[UserDetail]:
    stmt = select(AppUser)
    if not scope.is_unrestricted:
        stmt = stmt.where(AppUser.territory_id.in_(scope.ids or ()))
    if role:
        stmt = stmt.where(AppUser.role == role)
    if q:
        pattern = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(AppUser.username).like(pattern) | func.lower(AppUser.full_name).like(pattern))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(stmt.order_by(AppUser.id).limit(page.limit).offset(page.offset)).all()
    return Page(items=[UserDetail.model_validate(row) for row in rows], total=total)


def _check_territory(session: SessionDep, scope: ScopeDep, territory_id: int | None) -> None:
    if territory_id is not None and session.get(Territory, territory_id) is None:
        raise api_error(422, "territory_not_found", "Территория не найдена")
    if not scope.contains(territory_id):
        raise forbidden("Территория вне вашей зоны ответственности")


@router.post("", response_model=UserDetail, status_code=201)
def create_user(
    body: UserCreate, session: SessionDep, admin: AdminUser, scope: ScopeDep, request: Request
) -> UserDetail:
    _check_territory(session, scope, body.territory_id)
    if session.scalar(select(AppUser.id).where(AppUser.username == body.username)):
        raise api_error(409, "username_taken", "Пользователь с таким логином уже существует")
    user = AppUser(
        username=body.username,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=body.role,
        territory_id=body.territory_id,
        locale=body.locale,
        is_active=body.is_active,
    )
    session.add(user)
    session.flush()
    audit.record(session, admin, "user.create", "user", user.id, None, audit.snapshot(user), request)
    session.commit()
    return UserDetail.model_validate(user)


@router.patch("/{user_id}", response_model=UserDetail)
def update_user(
    user_id: int, body: UserUpdate, session: SessionDep, admin: AdminUser, scope: ScopeDep, request: Request
) -> UserDetail:
    user = session.get(AppUser, user_id)
    if user is None or not scope.contains(user.territory_id):
        raise api_error(404, "user_not_found", "Пользователь не найден")
    changes = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (changes.get("is_active") is False or changes.get("role", admin.role) != admin.role):
        raise api_error(409, "cannot_demote_self", "Нельзя отключить или понизить собственную учётную запись")
    if "territory_id" in changes:
        _check_territory(session, scope, changes["territory_id"])
    before = audit.snapshot(user)
    password = changes.pop("password", None)
    for field, value in changes.items():
        setattr(user, field, value)
    if password is not None:
        user.password_hash = hash_password(password)
    session.flush()
    audit.record(session, admin, "user.update", "user", user.id, before, audit.snapshot(user), request)
    session.commit()
    return UserDetail.model_validate(user)
