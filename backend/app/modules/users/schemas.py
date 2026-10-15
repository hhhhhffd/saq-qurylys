from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.models.enums import Locale, Role
from app.schemas import ORMModel

Username = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[A-Za-z0-9._@-]{3,64}$")]
Password = Annotated[str, Field(min_length=8, max_length=128)]


class UserOut(ORMModel):
    id: int
    username: str
    full_name: str
    role: Role
    territory_id: int | None
    locale: Locale


class UserDetail(UserOut):
    is_active: bool


class UserCreate(BaseModel):
    username: Username
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    password: Password
    role: Role
    territory_id: int | None = None
    locale: Locale = Locale.ru
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] | None = None
    password: Password | None = None
    role: Role | None = None
    territory_id: int | None = None
    locale: Locale | None = None
    is_active: bool | None = None

    @field_validator("role", "locale", "is_active", "full_name", "password")
    @classmethod
    def _not_null(cls, value: object) -> object:
        # Explicit null is meaningful only for territory_id (= whole country).
        if value is None:
            raise ValueError("value must not be null")
        return value
