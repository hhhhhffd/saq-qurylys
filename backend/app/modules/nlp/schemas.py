from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.models.enums import PhraseCategory
from app.schemas import ORMModel

PhraseText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Weight = Annotated[int, Field(ge=0, le=1000)]


class PhraseOut(ORMModel):
    id: int
    text: str
    variants: list[str]
    category: PhraseCategory
    weight: int
    is_active: bool


def _clean_variants(values: list[str]) -> list[str]:
    cleaned = (value.strip() for value in values)
    return list(dict.fromkeys(value for value in cleaned if value))


class PhraseCreate(BaseModel):
    text: PhraseText
    variants: list[str] = []
    category: PhraseCategory
    weight: Weight
    is_active: bool = True

    _variants = field_validator("variants")(_clean_variants)


class PhraseUpdate(BaseModel):
    """Partial update; send only the fields to change."""

    text: PhraseText | None = None
    variants: list[str] | None = None
    category: PhraseCategory | None = None
    weight: Weight | None = None
    is_active: bool | None = None

    @field_validator("variants")
    @classmethod
    def _variants(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _clean_variants(value)

    @model_validator(mode="after")
    def _no_nulls(self) -> Self:
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        return self
