from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, enum_type, fk
from app.models.enums import ScoreTrigger, Zone


class RiskFactor(TimestampMixin, Base):
    __tablename__ = "risk_factor"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(Text)
    weight: Mapped[int]
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    sort_order: Mapped[int] = mapped_column(server_default="0")


class RiskFactorChange(IdMixin, Base):
    """Append-only history of weight/activity changes."""

    __tablename__ = "risk_factor_change"

    code: Mapped[str] = mapped_column(String(64), index=True)
    old_weight: Mapped[int]
    new_weight: Mapped[int]
    old_active: Mapped[bool]
    new_active: Mapped[bool]
    changed_by: Mapped[int | None] = fk("app_user.id", nullable=True)
    changed_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RiskScore(IdMixin, Base):
    __tablename__ = "risk_score"
    __table_args__ = (Index("ix_risk_score_object_calculated", "object_id", "calculated_at"),)

    object_id: Mapped[int] = fk("construction_object.id")
    score: Mapped[int]
    zone: Mapped[Zone] = mapped_column(enum_type(Zone, "zone"))
    zone_reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    breakdown: Mapped[Any] = mapped_column(JSONB)
    trigger: Mapped[ScoreTrigger] = mapped_column(enum_type(ScoreTrigger, "score_trigger"))
    calculated_at: Mapped[datetime] = mapped_column(server_default=func.now())
