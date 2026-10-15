from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import PaymentScheme, Recipient, SignalOrigin, SignalStatus, Zone
from app.schemas import ORMModel

MAX_REVIEW_DAYS = 60
MAX_TEXT_LENGTH = 10_000

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TEXT_LENGTH)]


class ProposedMeasure(StrEnum):
    request_documents = "request_documents"
    site_inspection = "site_inspection"
    interview_complainants = "interview_complainants"
    request_payments_info = "request_payments_info"


class SchemePayments(BaseModel):
    payment_schemes: list[PaymentScheme]
    contract_types: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]] = (
        Field(max_length=20)
    )
    confirmed_payments_note: Annotated[str, StringConstraints(max_length=MAX_TEXT_LENGTH)]


class SectionsPatch(BaseModel):
    """The sections an officer may edit. The rest of `sections` (object, permits, publications, risk factors)
    is a snapshot of the registry and the route mirrors the card columns, so the client's copies are ignored."""

    model_config = ConfigDict(extra="ignore")

    scheme_payments: SchemePayments | None = None
    proposed_measures: list[ProposedMeasure] | None = None
    note: Annotated[str, StringConstraints(max_length=MAX_TEXT_LENGTH)] | None = None


class SignalPatch(BaseModel):
    sections: SectionsPatch | None = None
    recipient: Recipient | None = None
    review_days: int | None = Field(default=None, ge=1, le=MAX_REVIEW_DAYS)


class ConfirmAndSend(BaseModel):
    recipient: Recipient


class ReturnBody(BaseModel):
    comment: Text


class ResponseBody(BaseModel):
    response_text: Text


class CreateSignal(BaseModel):
    object_id: int


class SignalRow(BaseModel):
    id: int
    number: str
    object_id: int
    object_name: str
    zone: Zone | None
    status: SignalStatus
    recipient: Recipient | None
    due_date: date | None
    is_overdue: bool
    created_at: datetime


class SignalAuditEntry(ORMModel):
    id: int
    user_id: int | None
    username: str | None
    at: datetime
    action: str
    entity_type: str
    entity_id: int | None
    before: Any
    after: Any


class SignalDetail(SignalRow):
    origin: SignalOrigin
    sections: dict[str, Any]
    review_days: int
    sent_at: datetime | None
    sent_by: int | None
    return_comment: str | None
    response_text: str | None
    response_at: datetime | None
    responded_by: int | None
    created_by: int | None
    audit: list[SignalAuditEntry]
