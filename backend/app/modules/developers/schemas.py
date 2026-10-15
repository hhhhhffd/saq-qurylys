from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

from app.phones import normalize_phone
from app.schemas import ORMModel

Bin = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{12}$")]
Text255 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


def normalize_phones(values: list[str]) -> list[str]:
    result: list[str] = []
    for raw in values:
        phone = normalize_phone(raw)
        if phone is None:
            raise ValueError(f"invalid phone number: {raw!r}")
        if phone not in result:
            result.append(phone)
    return result


class DeveloperOut(ORMModel):
    id: int
    bin: str
    name: str
    director: str | None
    founders: list[str]
    authorized_company: str | None
    phones: list[str]


class DeveloperCreate(BaseModel):
    bin: Bin
    name: Text255
    director: str | None = None
    founders: list[str] = []
    authorized_company: str | None = None
    phones: list[str] = []

    _phones = field_validator("phones")(normalize_phones)


class DeveloperUpdate(BaseModel):
    name: Text255 | None = None
    director: str | None = None
    founders: list[str] | None = None
    authorized_company: str | None = None
    phones: list[str] | None = None

    @field_validator("phones")
    @classmethod
    def _phones(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalize_phones(value)
