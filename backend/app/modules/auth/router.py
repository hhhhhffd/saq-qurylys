import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from redis.exceptions import RedisError
from sqlalchemy import select

from app import audit
from app.deps import CurrentUser, SessionDep
from app.errors import api_error
from app.models import AppUser
from app.modules.auth import throttle
from app.modules.users.schemas import UserOut
from app.security import create_access_token, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(max_length=128)
    password: str = Field(max_length=1024)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105  (OAuth2 token type, not a secret)
    user: UserOut


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, session: SessionDep, request: Request) -> LoginResponse:
    username = body.username.strip().lower()
    ip = audit.client_ip(request)
    try:
        wait_s = throttle.blocked_for(username, ip)
    except RedisError as exc:
        # Without the counters the guessing protection is off: refuse rather than let logins through unchecked.
        logger.exception("Login throttle unavailable")
        raise api_error(503, "login_unavailable", "Вход временно недоступен, попробуйте позже") from exc
    if wait_s:
        error = api_error(
            429, "too_many_attempts", f"Слишком много неудачных попыток входа. Повторите через {-(-wait_s // 60)} мин."
        )
        error.headers = {"Retry-After": str(wait_s)}
        raise error

    user = session.scalar(select(AppUser).where(AppUser.username == username))
    password_ok = verify_password(body.password, user.password_hash if user else None)
    if user is None or not password_ok or not user.is_active:
        throttle.record_failure(username, ip)
        audit.record(
            session, None, "auth.login_failed", "user", user.id if user else None, None, {"username": username}, request
        )
        session.commit()
        logger.warning("Failed login for %r from %s", username, ip)
        raise api_error(401, "invalid_credentials", "Неверный логин или пароль")
    throttle.record_success(username)
    return LoginResponse(
        access_token=create_access_token(user.id, user.token_version), user=UserOut.model_validate(user)
    )


@router.post("/logout", status_code=204)
def logout(user: CurrentUser, session: SessionDep, request: Request) -> None:
    """Revoke every token of the user, on all devices: a token cannot be withdrawn one by one."""
    user.token_version += 1
    audit.record(session, user, "auth.logout", "user", user.id, None, None, request)
    session.commit()


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
