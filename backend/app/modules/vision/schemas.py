from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.models.enums import (
    OcrStatus,
    VisionAssetKind,
    VisionAssetStatus,
    VisionCategory,
    VisionFindingOrigin,
    VisionFindingStatus,
    VisionReviewAction,
    VisionReviewState,
    VisionRunStatus,
    VisionSessionStatus,
    VisionSource,
)

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]


class VisionConfig(BaseModel):
    enabled: bool
    detector_mode: Literal["disabled", "experimental_pretrained"]
    detector_model: str | None
    ocr_enabled: bool
    max_photo_mb: int
    max_video_mb: int
    max_duration_seconds: int


class ObjectRef(BaseModel):
    id: int
    code: str
    name: str


class SessionCreate(BaseModel):
    object_id: int | None = None
    territory_id: int | None = None
    source: VisionSource
    captured_at: datetime | None = None
    note: Note | None = None


class SessionPatch(BaseModel):
    """Only the fields that are sent change; `object_id: null` detaches the session from its object."""

    object_id: int | None = None
    note: Note | None = None
    source: VisionSource | None = None
    captured_at: datetime | None = None

    @model_validator(mode="after")
    def _source_is_not_cleared(self) -> Self:
        if "source" in self.model_fields_set and self.source is None:
            raise ValueError("source cannot be null")
        return self


class SessionListItem(BaseModel):
    id: int
    object: ObjectRef | None
    territory_id: int
    source: VisionSource
    captured_at: datetime | None
    status: VisionSessionStatus
    is_demo: bool
    note: str | None
    created_at: datetime
    created_by_name: str | None
    reviewed_at: datetime | None
    reviewed_by_name: str | None
    assets_count: int
    frames_count: int
    findings_count: int
    processing: bool
    failed: bool


class AssetOut(BaseModel):
    id: int
    session_id: int
    kind: VisionAssetKind
    original_name: str | None
    content_type: str
    size_bytes: int
    sha256: str
    width: int | None
    height: int | None
    duration_ms: int | None
    lat: float | None
    lon: float | None
    taken_at: datetime | None
    status: VisionAssetStatus
    error_code: str | None
    progress: int
    frames_count: int
    created_at: datetime


class FrameOut(BaseModel):
    id: int
    asset_id: int
    timestamp_ms: int | None
    width: int
    height: int
    sharpness: float | None
    usable: bool


class BBox(BaseModel):
    """A rectangle in fractions of the source frame, origin at the top-left corner."""

    x: Annotated[float, Field(ge=0, le=1)]
    y: Annotated[float, Field(ge=0, le=1)]
    w: Annotated[float, Field(gt=0, le=1)]
    h: Annotated[float, Field(gt=0, le=1)]

    @model_validator(mode="after")
    def _inside_frame(self) -> Self:
        # A tolerance keeps boxes drawn to the very edge from failing on float rounding.
        if self.x + self.w > 1 + 1e-9 or self.y + self.h > 1 + 1e-9:
            raise ValueError("bbox must lie inside the frame")
        return self


class FindingCreate(BaseModel):
    frame_id: int | None = None
    bbox: BBox | None = None
    category: VisionCategory
    status: VisionFindingStatus
    note: Note | None = None

    @model_validator(mode="after")
    def _bbox_needs_frame(self) -> Self:
        if self.bbox is not None and self.frame_id is None:
            raise ValueError("bbox needs frame_id")
        return self


class ReviewCreate(BaseModel):
    action: VisionReviewAction
    comment: Comment | None = None
    status: VisionFindingStatus | None = None


class ReviewOut(BaseModel):
    id: int
    action: VisionReviewAction
    comment: str | None
    status: VisionFindingStatus | None = None
    reviewer_name: str | None
    created_at: datetime


class FindingOut(BaseModel):
    id: int
    session_id: int
    frame_id: int | None
    bbox: BBox | None
    category: VisionCategory
    status: VisionFindingStatus
    origin: VisionFindingOrigin
    confidence: float | None
    model_version: str | None
    note: str | None
    review_state: VisionReviewState
    ocr_status: OcrStatus | None
    ocr_text: str | None
    ocr_confidence: float | None
    ocr_engine: str | None
    confirmed_text: str | None
    ad_post_id: int | None
    run_id: int | None
    created_at: datetime
    created_by_name: str | None
    reviews: list[ReviewOut]


class RunOut(BaseModel):
    id: int
    asset_id: int | None
    status: VisionRunStatus
    model_version: str | None
    frames_total: int
    frames_done: int
    error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None
    # Objects found per category (groups of boxes, not boxes). Filled once the run is completed; a category with 0
    # means "not found" - which is never evidence that it is absent from the site.
    summary: dict[str, int]


class SessionDetail(SessionListItem):
    assets: list[AssetOut]
    findings: list[FindingOut]
    runs: list[RunOut]


class PublishAdBody(BaseModel):
    """The text is what a person confirmed (OCR output is only a suggestion)."""

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50_000)]
    object_id: int | None = None


class PublishAdOut(BaseModel):
    ad_id: int
