from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Float, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, column_property, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, enum_type, fk, point
from app.models.enums import (
    AdOrigin,
    AdStatus,
    AdVersionSource,
    CaptureStatus,
    DetectedBy,
    LinkMethod,
    LlmStatus,
    OcrStatus,
    PhraseCategory,
    Platform,
)


class SourceAccount(IdMixin, TimestampMixin, Base):
    __tablename__ = "source_account"
    __table_args__ = (UniqueConstraint("platform", "handle"),)

    platform: Mapped[Platform] = mapped_column(enum_type(Platform, "platform"))
    handle: Mapped[str] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(1000))
    object_id: Mapped[int | None] = fk("construction_object.id", nullable=True, index=True)
    developer_id: Mapped[int | None] = fk("developer.id", nullable=True, index=True)
    territory_id: Mapped[int | None] = fk("territory.id", nullable=True, index=True)
    is_watched: Mapped[bool] = mapped_column(server_default="true")
    last_collected_at: Mapped[datetime | None]
    # The last failed collection run; cleared by the next successful one.
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None]


class AdPost(IdMixin, TimestampMixin, Base):
    """Advertising publication. `capture_status` is NULL when no capture is applicable (no URL)."""

    __tablename__ = "ad_post"
    __table_args__ = (
        UniqueConstraint("platform", "external_id"),
        CheckConstraint("link_confidence BETWEEN 0 AND 1", name="link_confidence_range"),
        Index("ix_ad_post_object_published", "object_id", "published_at"),
        Index("ix_ad_post_sort", "max_phrase_weight", "published_at"),
        Index("ix_ad_post_status", "status"),
        Index("ix_ad_post_last_checked_at", "last_checked_at"),
        Index("ix_ad_post_location", "location", postgresql_using="gist"),
    )

    territory_id: Mapped[int | None] = fk("territory.id", nullable=True, index=True)
    source_account_id: Mapped[int | None] = fk("source_account.id", nullable=True)
    platform: Mapped[Platform] = mapped_column(enum_type(Platform, "platform"))
    url: Mapped[str | None] = mapped_column(String(2000))
    external_id: Mapped[str | None] = mapped_column(String(255))
    author: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime | None]
    captured_at: Mapped[datetime | None]
    text: Mapped[str | None] = mapped_column(Text)
    phones: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    links: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    object_id: Mapped[int | None] = fk("construction_object.id", nullable=True)
    link_confidence: Mapped[float | None] = mapped_column(Float)
    link_method: Mapped[LinkMethod | None] = mapped_column(enum_type(LinkMethod, "link_method"))
    payment_schemes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    claimed_readiness_pct: Mapped[int | None]
    price_before_completion: Mapped[bool] = mapped_column(server_default="false")
    llm_extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    llm_status: Mapped[LlmStatus] = mapped_column(
        enum_type(LlmStatus, "llm_status"), server_default=LlmStatus.none.value
    )
    status: Mapped[AdStatus] = mapped_column(enum_type(AdStatus, "ad_status"), server_default=AdStatus.captured.value)
    max_phrase_weight: Mapped[int] = mapped_column(server_default="0")
    total_phrase_weight: Mapped[int] = mapped_column(server_default="0")
    is_outdoor: Mapped[bool] = mapped_column(server_default="false")
    location: Mapped[Any] = mapped_column(point(), nullable=True)
    lat: Mapped[float | None] = column_property(func.ST_Y(location))
    lon: Mapped[float | None] = column_property(func.ST_X(location))
    last_checked_at: Mapped[datetime | None]
    removed_detected_at: Mapped[datetime | None]
    capture_status: Mapped[CaptureStatus | None] = mapped_column(enum_type(CaptureStatus, "capture_status"))
    capture_error: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(server_default="false")
    origin: Mapped[AdOrigin] = mapped_column(enum_type(AdOrigin, "ad_origin"), server_default=AdOrigin.manual.value)
    # NULL when the post has no photos to read; recognised text is appended to `text` (SPEC 10.2).
    ocr_status: Mapped[OcrStatus | None] = mapped_column(enum_type(OcrStatus, "ocr_status"))


class AdPostVersion(IdMixin, Base):
    """A later text of a publication that differs from the saved original (`ad_post.text`): the source was edited
    after the capture. Append-only (SPEC 10.6)."""

    __tablename__ = "ad_post_version"
    __table_args__ = (Index("ix_ad_post_version_ad_post_observed", "ad_post_id", "observed_at"),)

    ad_post_id: Mapped[int] = fk("ad_post.id")
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime]
    source: Mapped[AdVersionSource] = mapped_column(enum_type(AdVersionSource, "ad_version_source"))
    # The capture of the page showing this text, when one was taken.
    evidence_id: Mapped[int | None] = fk("evidence.id", nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DismissedSourceSuggestion(IdMixin, Base):
    """An account suggested for watching that staff declined; it is not suggested again (SPEC 10.3)."""

    __tablename__ = "dismissed_source_suggestion"
    __table_args__ = (UniqueConstraint("platform", "handle"),)

    platform: Mapped[Platform] = mapped_column(enum_type(Platform, "platform"))
    handle: Mapped[str] = mapped_column(String(255))
    dismissed_by: Mapped[int | None] = fk("app_user.id", nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Phrase(IdMixin, TimestampMixin, Base):
    __tablename__ = "phrase"
    __table_args__ = (UniqueConstraint("category", "text"),)

    text: Mapped[str] = mapped_column(String(255))
    variants: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    category: Mapped[PhraseCategory] = mapped_column(enum_type(PhraseCategory, "phrase_category"))
    weight: Mapped[int]
    is_active: Mapped[bool] = mapped_column(server_default="true")


class PhraseHit(IdMixin, TimestampMixin, Base):
    __tablename__ = "phrase_hit"
    __table_args__ = (Index("ix_phrase_hit_ad_post", "ad_post_id"),)

    ad_post_id: Mapped[int] = fk("ad_post.id", ondelete="CASCADE")
    phrase_id: Mapped[int | None] = fk("phrase.id", nullable=True)
    category: Mapped[PhraseCategory] = mapped_column(enum_type(PhraseCategory, "phrase_category"))
    matched_text: Mapped[str] = mapped_column(Text)
    start: Mapped[int]
    end: Mapped[int]
    weight: Mapped[int]
    detected_by: Mapped[DetectedBy] = mapped_column(enum_type(DetectedBy, "detected_by"))
    confirmed: Mapped[bool | None]
    confirmed_by: Mapped[int | None] = fk("app_user.id", nullable=True)
