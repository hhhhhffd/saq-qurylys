from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, enum_type, fk
from app.models.enums import HolidayKind, NotificationKind


class AuditLog(IdMixin, Base):
    """Append-only: UPDATE and DELETE are rejected by a database trigger."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_user_at", "user_id", "at"),
    )

    user_id: Mapped[int | None] = fk("app_user.id", nullable=True)
    at: Mapped[datetime] = mapped_column(server_default=func.now())
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    before: Mapped[Any] = mapped_column(JSONB, nullable=True)
    after: Mapped[Any] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64))


class Notification(IdMixin, Base):
    __tablename__ = "notification"
    __table_args__ = (Index("ix_notification_user_read_created", "user_id", "read_at", "created_at"),)

    user_id: Mapped[int] = fk("app_user.id")
    kind: Mapped[NotificationKind] = mapped_column(enum_type(NotificationKind, "notification_kind"))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    payload: Mapped[Any] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    read_at: Mapped[datetime | None]


class Holiday(TimestampMixin, Base):
    __tablename__ = "holiday"

    day: Mapped[date] = mapped_column(primary_key=True)
    kind: Mapped[HolidayKind] = mapped_column(enum_type(HolidayKind, "holiday_kind"))
    name: Mapped[str] = mapped_column(String(255))


class AppSetting(TimestampMixin, Base):
    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
