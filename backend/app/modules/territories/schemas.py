from typing import Annotated, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.models.enums import TerritoryLevel
from app.schemas import ORMModel

Code = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


def _check_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown IANA time zone: {value}") from exc
    return value


class TerritoryNode(ORMModel):
    id: int
    parent_id: int | None
    level: TerritoryLevel
    code: str
    name: str
    timezone: str
    center_lat: float | None
    center_lon: float | None
    children: list["TerritoryNode"] = Field(default_factory=list)


class TerritoryCreate(BaseModel):
    parent_id: int | None = None
    level: TerritoryLevel
    code: Code
    name: Name
    timezone: str = "Asia/Almaty"
    lat: Annotated[float, Field(ge=-90, le=90)] | None = None
    lon: Annotated[float, Field(ge=-180, le=180)] | None = None

    _tz = field_validator("timezone")(_check_timezone)

    @model_validator(mode="after")
    def _check_point(self) -> Self:
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must be given together")
        return self


class TerritoryUpdate(BaseModel):
    name: Name | None = None
    timezone: str | None = None
    lat: Annotated[float, Field(ge=-90, le=90)] | None = None
    lon: Annotated[float, Field(ge=-180, le=180)] | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str | None) -> str | None:
        return None if value is None else _check_timezone(value)

    @model_validator(mode="after")
    def _check_point(self) -> Self:
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must be given together")
        return self
