from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_session
from app.errors import api_error, forbidden
from app.models import AppUser
from app.models.enums import Role
from app.scope import TerritoryScope, build_scope
from app.security import decode_access_token

SessionDep = Annotated[Session, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: SessionDep,
) -> AppUser:
    if credentials is None:
        raise api_error(401, "not_authenticated", "Требуется авторизация")
    try:
        user_id, token_version = decode_access_token(credentials.credentials)
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise api_error(401, "invalid_token", "Недействительный или просроченный токен") from exc
    user = session.get(AppUser, user_id)
    if user is None or not user.is_active or user.token_version != token_version:
        raise api_error(401, "invalid_token", "Недействительный или просроченный токен")
    return user


CurrentUser = Annotated[AppUser, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[[AppUser], AppUser]:
    allowed = frozenset(roles)

    def dependency(user: CurrentUser) -> AppUser:
        if user.role not in allowed:
            raise forbidden()
        return user

    return dependency


def get_scope(user: CurrentUser, session: SessionDep) -> TerritoryScope:
    return build_scope(session, user)


ScopeDep = Annotated[TerritoryScope, Depends(get_scope)]

# Users allowed to work with objects, documents, ads and the other registry data.
StaffUser = Annotated[AppUser, Depends(require_roles(Role.admin, Role.mio_officer))]
AdminUser = Annotated[AppUser, Depends(require_roles(Role.admin))]


def require_global_admin(user: AdminUser, scope: ScopeDep) -> AppUser:
    """Admin without a territory. Settings and the calendar are shared by the whole country."""
    if not scope.is_unrestricted:
        raise forbidden("Действие доступно только администратору без территориальных ограничений")
    return user


GlobalAdmin = Annotated[AppUser, Depends(require_global_admin)]


@dataclass(frozen=True)
class PageParams:
    limit: int
    offset: int


def page_params(limit: Annotated[int, Query(ge=1, le=500)] = 50, offset: Annotated[int, Query(ge=0)] = 0) -> PageParams:
    return PageParams(limit=limit, offset=offset)


PageDep = Annotated[PageParams, Depends(page_params)]
