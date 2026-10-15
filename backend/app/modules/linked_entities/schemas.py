from typing import Annotated, Self

from pydantic import BaseModel, StringConstraints, model_validator

from app.models.enums import LinkedEntityKind
from app.phones import normalize_phone
from app.schemas import ORMModel


class LinkedEntityOut(ORMModel):
    id: int
    object_id: int | None
    developer_id: int | None
    kind: LinkedEntityKind
    value: str
    note: str | None


class LinkedEntityCreate(BaseModel):
    kind: LinkedEntityKind
    value: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    note: str | None = None

    @model_validator(mode="after")
    def _normalize_phone(self) -> Self:
        if self.kind is LinkedEntityKind.phone:
            phone = normalize_phone(self.value)
            if phone is None:
                raise ValueError(f"invalid phone number: {self.value!r}")
            self.value = phone
        return self
