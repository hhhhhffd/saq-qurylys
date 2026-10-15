from datetime import date, datetime
from typing import Any

from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, enum_type, fk
from app.models.enums import Recipient, SignalOrigin, SignalStatus


class SignalCounter(Base):
    """Per-year counter for signal card numbers SQ-YYYY-NNNN."""

    __tablename__ = "signal_counter"

    year: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    last_number: Mapped[int] = mapped_column(server_default="0")


class SignalCard(IdMixin, TimestampMixin, Base):
    __tablename__ = "signal_card"
    __table_args__ = (
        Index("ix_signal_card_object_status", "object_id", "status"),
        Index("ix_signal_card_status_due_date", "status", "due_date"),
    )

    number: Mapped[str] = mapped_column(String(32), unique=True)
    object_id: Mapped[int] = fk("construction_object.id")
    status: Mapped[SignalStatus] = mapped_column(
        enum_type(SignalStatus, "signal_status"), server_default=SignalStatus.requires_confirmation.value
    )
    origin: Mapped[SignalOrigin] = mapped_column(enum_type(SignalOrigin, "signal_origin"))
    sections: Mapped[Any] = mapped_column(JSONB, server_default="{}")
    recipient: Mapped[Recipient | None] = mapped_column(enum_type(Recipient, "recipient"))
    review_days: Mapped[int | None]
    sent_at: Mapped[datetime | None]
    sent_by: Mapped[int | None] = fk("app_user.id", nullable=True)
    due_date: Mapped[date | None]
    return_comment: Mapped[str | None] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text)
    response_at: Mapped[datetime | None]
    responded_by: Mapped[int | None] = fk("app_user.id", nullable=True)
    created_by: Mapped[int | None] = fk("app_user.id", nullable=True)
