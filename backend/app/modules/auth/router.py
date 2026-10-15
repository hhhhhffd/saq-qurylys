from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import CurrentUser, SessionDep
from app.errors import api_error
from app.models import AppUser
from app.modules.users.schemas import UserOut
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105  (OAuth2 token type, not a secret)
    user: UserOut


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, session: SessionDep) -> LoginResponse:
    user = session.scalar(select(AppUser).where(AppUser.username == body.username.strip().lower()))
    password_ok = verify_password(body.password, user.password_hash if user else None)
    if user is None or not password_ok or not user.is_active:
        raise api_error(401, "invalid_credentials", "Неверный логин или пароль")
    return LoginResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
