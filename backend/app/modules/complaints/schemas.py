from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models.enums import ComplaintSource, ComplaintStatus
from app.schemas import ORMModel

ExternalId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


class ComplaintOut(ORMModel):
    id: int
    object_id: int
    received_at: date
    source: ComplaintSource
    external_id: str | None
    is_collective: bool
    signatories_count: int
    summary: str | None
    status: ComplaintStatus
    confirmed_payments: bool
    is_verified: bool
    verified_by: int | None
    verified_at: datetime | None


class ComplaintCreate(BaseModel):
    received_at: date
    source: ComplaintSource = ComplaintSource.manual
    external_id: ExternalId | None = None
    is_collective: bool = False
    signatories_count: Annotated[int, Field(ge=1, le=100000)] = 1
    summary: str | None = None
    status: ComplaintStatus = ComplaintStatus.new
    confirmed_payments: bool = False
    # Checked by an analyst; a collective complaint counts for R4 only once verified.
    is_verified: bool = False


class ComplaintUpdate(BaseModel):
    received_at: date | None = None
    source: ComplaintSource | None = None
    external_id: ExternalId | None = None
    is_collective: bool | None = None
    signatories_count: Annotated[int, Field(ge=1, le=100000)] | None = None
    summary: str | None = None
    status: ComplaintStatus | None = None
    confirmed_payments: bool | None = None
    is_verified: bool | None = None
