from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.models import PhraseHit
from app.models.enums import (
    AdStatus,
    CaptureStatus,
    DetectedBy,
    LinkMethod,
    LlmStatus,
    PaymentScheme,
    PhraseCategory,
    Platform,
)
from app.modules.evidence.schemas import EvidenceOut
from app.modules.nlp.llm import UNCERTAIN_BELOW, Extraction, Finding
from app.modules.nlp.text import to_utf16_offsets
from app.schemas import ORMModel

Url = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Lat = Annotated[float, Field(ge=-90, le=90)]
Lon = Annotated[float, Field(ge=-180, le=180)]


class AdRow(ORMModel):
    id: int
    territory_id: int | None
    source_account_id: int | None
    platform: Platform
    url: str | None
    author: str | None
    published_at: datetime | None
    captured_at: datetime | None
    text: str | None
    phones: list[str]
    links: list[str]
    object_id: int | None
    object_name: str | None = None
    link_confidence: float | None
    link_method: LinkMethod | None
    payment_schemes: list[PaymentScheme]
    claimed_readiness_pct: int | None
    price_before_completion: bool
    llm_status: LlmStatus
    status: AdStatus
    max_phrase_weight: int
    total_phrase_weight: int
    is_outdoor: bool
    is_demo: bool
    lat: float | None
    lon: float | None
    last_checked_at: datetime | None
    removed_detected_at: datetime | None
    # NULL when no capture applies (a manual publication has no capture).
    capture_status: CaptureStatus | None
    capture_error: str | None


class PhraseHitOut(ORMModel):
    """`start` / `end` are UTF-16 code unit offsets into `AdRow.text` (JavaScript string indices, end exclusive);
    the database keeps Unicode code point offsets."""

    id: int
    ad_post_id: int
    phrase_id: int | None
    category: PhraseCategory
    matched_text: str
    start: int
    end: int
    weight: int
    detected_by: DetectedBy
    confirmed: bool | None
    confirmed_by: int | None
    # Of an LLM hit: the confidence the model gave its finding. Dictionary hits have none.
    confidence: float | None = None
    uncertain: bool = False

    @classmethod
    def from_hit(cls, hit: PhraseHit, text: str, finding: Finding | None = None) -> Self:
        start, end = to_utf16_offsets(text, [hit.start, hit.end])
        update: dict[str, object] = {"start": start, "end": end}
        if finding is not None:
            update |= {"confidence": finding.confidence, "uncertain": finding.confidence < UNCERTAIN_BELOW}
        return cls.model_validate(hit).model_copy(update=update)


class LinkedObject(ORMModel):
    id: int
    code: str
    name: str


class AdDetail(AdRow):
    phrase_hits: list[PhraseHitOut]
    evidence: list[EvidenceOut]
    llm_extraction: Extraction | None
    linked_object: LinkedObject | None


class CaptureRequest(BaseModel):
    url: Url
    object_id: int | None = None
    platform: Platform | None = None


class AdPatch(BaseModel):
    """Partial update; send only the fields to change. `object_id: null` removes the link."""

    object_id: int | None = None
    status: AdStatus | None = None
    payment_schemes: list[PaymentScheme] | None = None
    claimed_readiness_pct: Annotated[int, Field(ge=0, le=100)] | None = None
    price_before_completion: bool | None = None

    @field_validator("payment_schemes")
    @classmethod
    def _unique_schemes(cls, value: list[PaymentScheme] | None) -> list[PaymentScheme] | None:
        return None if value is None else list(dict.fromkeys(value))

    @model_validator(mode="after")
    def _check_required(self) -> Self:
        for field in ("status", "payment_schemes", "price_before_completion"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        return self


class HitConfirm(BaseModel):
    confirmed: bool


Handle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class SourceAccountOut(ORMModel):
    id: int
    platform: Platform
    handle: str
    url: str | None
    object_id: int | None
    developer_id: int | None
    territory_id: int | None
    is_watched: bool
    last_collected_at: datetime | None


class SourceAccountCreate(BaseModel):
    platform: Platform
    handle: Handle | None = None
    url: Url | None = None
    object_id: int | None = None
    developer_id: int | None = None
    territory_id: int | None = None
    is_watched: bool = True

    @model_validator(mode="after")
    def _handle_or_url(self) -> Self:
        if self.handle is None and self.url is None:
            raise ValueError("handle or url is required")
        return self


class SourceAccountUpdate(BaseModel):
    """Partial update; send only the fields to change."""

    handle: Handle | None = None
    url: Url | None = None
    object_id: int | None = None
    developer_id: int | None = None
    territory_id: int | None = None
    is_watched: bool | None = None

    @model_validator(mode="after")
    def _check_required(self) -> Self:
        if "handle" in self.model_fields_set and self.handle is None:
            raise ValueError("handle must not be null")
        if "is_watched" in self.model_fields_set and self.is_watched is None:
            raise ValueError("is_watched must not be null")
        return self
