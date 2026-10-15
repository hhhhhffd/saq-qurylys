from datetime import date, datetime
from typing import Annotated, Any, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.models.enums import ConstructionStatus, KeyStatus, Zone
from app.modules.complaints.schemas import ComplaintOut
from app.modules.developers.schemas import DeveloperOut
from app.modules.documents.schemas import DocumentOut
from app.modules.inspections.schemas import InspectionOut
from app.modules.linked_entities.schemas import LinkedEntityOut
from app.schemas import ORMModel

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Lat = Annotated[float, Field(ge=-90, le=90)]
Lon = Annotated[float, Field(ge=-180, le=180)]


class ObjectRow(BaseModel):
    id: int
    code: str
    name: str
    developer_name: str | None
    score: int | None
    zone: Zone | None
    key_status: KeyStatus | None
    key_status_detail: dict[str, Any] | None
    district_name: str | None
    lat: float | None
    lon: float | None


class LatestScore(ORMModel):
    score: int
    zone: Zone
    zone_reasons: list[str]
    breakdown: Any
    calculated_at: datetime


class ObjectPassport(ORMModel):
    id: int
    code: str
    territory_id: int
    district_id: int | None
    developer_id: int | None
    name: str
    aliases: list[str]
    address: str | None
    cadastral_number: str | None
    land_purpose: str | None
    lat: float | None
    lon: float | None
    planned_completion: date | None
    forecast_completion: date | None
    construction_status: ConstructionStatus
    stalled_since: date | None
    readiness_actual_pct: int | None
    readiness_claimed_pct: int | None
    prior_violations: str | None
    score: int | None
    zone: Zone | None
    key_status: KeyStatus | None
    last_scored_at: datetime | None
    next_check_at: datetime | None
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class ObjectDetail(ObjectPassport):
    district_name: str | None
    key_status_detail: dict[str, Any] | None
    developer: DeveloperOut | None
    documents: list[DocumentOut]
    inspections: list[InspectionOut]
    complaints: list[ComplaintOut]
    linked_entities: list[LinkedEntityOut]
    ads_7d_count: int
    readiness_gap_pp: int | None
    latest_score: LatestScore | None


class ObjectBase(BaseModel):
    district_id: int | None = None
    developer_id: int | None = None
    aliases: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]] = []
    address: str | None = None
    cadastral_number: str | None = None
    land_purpose: str | None = None
    lat: Lat | None = None
    lon: Lon | None = None
    planned_completion: date | None = None
    forecast_completion: date | None = None
    construction_status: ConstructionStatus = ConstructionStatus.active
    stalled_since: date | None = None
    prior_violations: str | None = None

    @model_validator(mode="after")
    def _check_point(self) -> Self:
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must be given together")
        return self


class ObjectCreate(ObjectBase):
    name: Name
    territory_id: int


class ObjectUpdate(BaseModel):
    """Partial update; send only the fields to change. `null` clears an optional field."""

    name: Name | None = None
    territory_id: int | None = None
    district_id: int | None = None
    developer_id: int | None = None
    aliases: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]] | None = None
    address: str | None = None
    cadastral_number: str | None = None
    land_purpose: str | None = None
    lat: Lat | None = None
    lon: Lon | None = None
    planned_completion: date | None = None
    forecast_completion: date | None = None
    construction_status: ConstructionStatus | None = None
    stalled_since: date | None = None
    prior_violations: str | None = None

    @model_validator(mode="after")
    def _check_required(self) -> Self:
        for field in ("name", "territory_id", "aliases", "construction_status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        if ("lat" in self.model_fields_set or "lon" in self.model_fields_set) and (self.lat is None) != (
            self.lon is None
        ):
            raise ValueError("lat and lon must be given together")
        return self
