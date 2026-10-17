from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Float, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, column_property, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, enum_type, fk, point
from app.models.enums import (
    OcrStatus,
    VisionAssetKind,
    VisionAssetStatus,
    VisionCategory,
    VisionFindingOrigin,
    VisionFindingStatus,
    VisionJobKind,
    VisionJobStatus,
    VisionReviewAction,
    VisionReviewState,
    VisionRunStatus,
    VisionSessionStatus,
    VisionSource,
)

# Nothing here is deleted: a session keeps its history, so foreign keys restrict deletion (no ON DELETE).


class VisionSession(IdMixin, TimestampMixin, Base):
    """One survey of a site (drone flight, camera recording, phone photos). Never changes readiness or risk."""

    __tablename__ = "vision_session"
    __table_args__ = (Index("ix_vision_session_object_captured", "object_id", "captured_at"),)

    territory_id: Mapped[int] = fk("territory.id", index=True)
    object_id: Mapped[int | None] = fk("construction_object.id", nullable=True)
    source: Mapped[VisionSource] = mapped_column(enum_type(VisionSource, "vision_source"))
    captured_at: Mapped[datetime | None]
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[VisionSessionStatus] = mapped_column(
        enum_type(VisionSessionStatus, "vision_session_status"), server_default=VisionSessionStatus.open.value
    )
    reviewed_by: Mapped[int | None] = fk("app_user.id", nullable=True)
    reviewed_at: Mapped[datetime | None]
    created_by: Mapped[int] = fk("app_user.id")
    is_demo: Mapped[bool] = mapped_column(server_default="false")


class VisionAsset(IdMixin, TimestampMixin, Base):
    """An uploaded original (photo or video), stored in the vision bucket. sha256 is computed by the server."""

    __tablename__ = "vision_asset"
    __table_args__ = (
        UniqueConstraint("session_id", "sha256"),
        Index("ix_vision_asset_location", "location", postgresql_using="gist"),
    )

    session_id: Mapped[int] = fk("vision_session.id", index=True)
    kind: Mapped[VisionAssetKind] = mapped_column(enum_type(VisionAssetKind, "vision_asset_kind"))
    original_name: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    bucket: Mapped[str] = mapped_column(String(63))
    s3_key: Mapped[str] = mapped_column(String(512))
    width: Mapped[int | None]
    height: Mapped[int | None]
    duration_ms: Mapped[int | None]
    location: Mapped[Any] = mapped_column(point(), nullable=True)
    lat: Mapped[float | None] = column_property(func.ST_Y(location))
    lon: Mapped[float | None] = column_property(func.ST_X(location))
    taken_at: Mapped[datetime | None]
    status: Mapped[VisionAssetStatus] = mapped_column(
        enum_type(VisionAssetStatus, "vision_asset_status"), server_default=VisionAssetStatus.queued.value
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    uploaded_by: Mapped[int] = fk("app_user.id")


class VisionJob(IdMixin, TimestampMixin, Base):
    __tablename__ = "vision_job"
    __table_args__ = (
        UniqueConstraint("idempotency_key"),
        CheckConstraint("progress BETWEEN 0 AND 100", name="vision_job_progress_range"),
        Index("ix_vision_job_asset_id", "asset_id", "id"),
    )

    asset_id: Mapped[int] = fk("vision_asset.id")
    kind: Mapped[VisionJobKind] = mapped_column(enum_type(VisionJobKind, "vision_job_kind"))
    status: Mapped[VisionJobStatus] = mapped_column(
        enum_type(VisionJobStatus, "vision_job_status"), server_default=VisionJobStatus.queued.value
    )
    progress: Mapped[int] = mapped_column(server_default="0")
    attempts: Mapped[int] = mapped_column(server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    idempotency_key: Mapped[str] = mapped_column(String(128))


class VisionFrame(IdMixin, Base):
    """A still: the photo itself (`timestamp_ms` NULL) or a frame extracted from a video."""

    __tablename__ = "vision_frame"
    __table_args__ = (UniqueConstraint("asset_id", "timestamp_ms"),)

    asset_id: Mapped[int] = fk("vision_asset.id")
    timestamp_ms: Mapped[int | None]
    bucket: Mapped[str] = mapped_column(String(63))
    s3_key: Mapped[str] = mapped_column(String(512))
    preview_key: Mapped[str] = mapped_column(String(512))
    width: Mapped[int]
    height: Mapped[int]
    sharpness: Mapped[float | None] = mapped_column(Float)
    usable: Mapped[bool] = mapped_column(server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class VisionRun(IdMixin, Base):
    """One pass of the object detector over the usable frames of an asset (or of the whole session)."""

    __tablename__ = "vision_run"
    __table_args__ = (
        CheckConstraint("frames_done BETWEEN 0 AND frames_total", name="vision_run_frames_range"),
        Index("ix_vision_run_session_id", "session_id", "id"),
    )

    session_id: Mapped[int] = fk("vision_session.id")
    asset_id: Mapped[int | None] = fk("vision_asset.id", nullable=True)
    status: Mapped[VisionRunStatus] = mapped_column(
        enum_type(VisionRunStatus, "vision_run_status"), server_default=VisionRunStatus.queued.value
    )
    model_version: Mapped[str | None] = mapped_column(String(100))
    # Thresholds, prompts, max side, device: what the run was made with.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    frames_total: Mapped[int] = mapped_column(server_default="0")
    frames_done: Mapped[int] = mapped_column(server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    created_by: Mapped[int | None] = fk("app_user.id", nullable=True)  # NULL: started automatically
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class VisionDetection(IdMixin, Base):
    """A raw box of the detector. Findings are made from groups of these; the boxes themselves are kept as evidence."""

    __tablename__ = "vision_detection"
    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0 AND 1", name="vision_detection_confidence_range"),
        Index("ix_vision_detection_run_id", "run_id", "group_key"),
        Index("ix_vision_detection_frame_id", "frame_id"),
    )

    run_id: Mapped[int] = fk("vision_run.id")
    frame_id: Mapped[int] = fk("vision_frame.id")
    category: Mapped[VisionCategory] = mapped_column(enum_type(VisionCategory, "vision_detection_category"))
    label: Mapped[str] = mapped_column(String(100))  # the matched phrase of the prompt
    bbox: Mapped[dict[str, Any]] = mapped_column(JSONB)  # fractions of the source frame: {"x", "y", "w", "h"}
    confidence: Mapped[float] = mapped_column(Float)
    # The same physical object on adjacent frames of one asset shares the key (unique within the run).
    group_key: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class VisionFinding(IdMixin, TimestampMixin, Base):
    """An observation on a frame. It is not a violation: `status` and `review_state` are decided by people."""

    __tablename__ = "vision_finding"
    __table_args__ = (
        UniqueConstraint("ad_post_id"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="vision_finding_confidence_range"),
        Index("ix_vision_finding_session_id", "session_id", "id"),
        Index("ix_vision_finding_frame_id", "frame_id"),
    )

    session_id: Mapped[int] = fk("vision_session.id")
    frame_id: Mapped[int | None] = fk("vision_frame.id", nullable=True)
    # Fractions of the source frame: {"x", "y", "w", "h"}.
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    category: Mapped[VisionCategory] = mapped_column(enum_type(VisionCategory, "vision_category"))
    status: Mapped[VisionFindingStatus] = mapped_column(enum_type(VisionFindingStatus, "vision_finding_status"))
    origin: Mapped[VisionFindingOrigin] = mapped_column(enum_type(VisionFindingOrigin, "vision_finding_origin"))
    confidence: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    review_state: Mapped[VisionReviewState] = mapped_column(
        enum_type(VisionReviewState, "vision_review_state"), server_default=VisionReviewState.pending.value
    )
    ocr_status: Mapped[OcrStatus | None] = mapped_column(enum_type(OcrStatus, "ocr_status"))
    ocr_text: Mapped[str | None] = mapped_column(Text)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    ocr_engine: Mapped[str | None] = mapped_column(String(100))
    confirmed_text: Mapped[str | None] = mapped_column(Text)
    ad_post_id: Mapped[int | None] = fk("ad_post.id", nullable=True)
    run_id: Mapped[int | None] = fk("vision_run.id", nullable=True)
    detection_id: Mapped[int | None] = fk("vision_detection.id", nullable=True)  # the representative box
    created_by: Mapped[int | None] = fk("app_user.id", nullable=True)


class VisionReview(IdMixin, Base):
    """A decision on a finding. Append-only; `vision_finding.review_state` holds only the latest state."""

    __tablename__ = "vision_review"
    __table_args__ = (Index("ix_vision_review_finding_id", "finding_id", "id"),)

    finding_id: Mapped[int] = fk("vision_finding.id")
    action: Mapped[VisionReviewAction] = mapped_column(enum_type(VisionReviewAction, "vision_review_action"))
    comment: Mapped[str | None] = mapped_column(Text)
    # The finding status the person set with this decision, if they changed it.
    status: Mapped[VisionFindingStatus | None] = mapped_column(enum_type(VisionFindingStatus, "vision_review_status"))
    reviewer_id: Mapped[int] = fk("app_user.id")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
