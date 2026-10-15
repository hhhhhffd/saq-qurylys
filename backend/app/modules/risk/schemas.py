from datetime import datetime
from typing import Annotated, Any, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.models.enums import ScoreTrigger, Zone
from app.schemas import ORMModel


class RiskFactorOut(ORMModel):
    code: str
    description: str
    weight: int
    is_active: bool
    sort_order: int


class RiskFactorUpdate(BaseModel):
    """Partial update; send only the fields to change."""

    weight: int | None = Field(default=None, ge=-100, le=100)
    is_active: bool | None = None
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)] | None = None

    @model_validator(mode="after")
    def _no_nulls(self) -> Self:
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        return self


class RiskFactorChangeOut(ORMModel):
    id: int
    code: str
    old_weight: int
    new_weight: int
    old_active: bool
    new_active: bool
    changed_by: int | None
    changed_by_name: str | None
    changed_at: datetime


class ScoreHistoryItem(ORMModel):
    id: int
    object_id: int
    score: int
    zone: Zone
    zone_reasons: list[str]
    breakdown: Any
    trigger: ScoreTrigger
    calculated_at: datetime
