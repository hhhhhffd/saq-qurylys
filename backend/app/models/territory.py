from typing import Any

from sqlalchemy import Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, column_property, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, enum_type, fk, multipolygon, point
from app.models.enums import Locale, Role, TerritoryLevel


class Territory(IdMixin, TimestampMixin, Base):
    __tablename__ = "territory"
    __table_args__ = (
        Index("ix_territory_center", "center", postgresql_using="gist"),
        Index("ix_territory_boundary", "boundary", postgresql_using="gist"),
    )

    parent_id: Mapped[int | None] = fk("territory.id", nullable=True, index=True)
    level: Mapped[TerritoryLevel] = mapped_column(enum_type(TerritoryLevel, "territory_level"))
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), server_default="Asia/Almaty")
    center: Mapped[Any] = mapped_column(point(), nullable=True)
    center_lat: Mapped[float | None] = column_property(func.ST_Y(center))
    center_lon: Mapped[float | None] = column_property(func.ST_X(center))
    boundary: Mapped[Any] = mapped_column(multipolygon(), nullable=True)


class District(IdMixin, TimestampMixin, Base):
    __tablename__ = "district"
    __table_args__ = (
        UniqueConstraint("territory_id", "name"),
        Index("ix_district_boundary", "boundary", postgresql_using="gist"),
    )

    territory_id: Mapped[int] = fk("territory.id", index=True)
    name: Mapped[str] = mapped_column(String(255))
    boundary: Mapped[Any] = mapped_column(multipolygon(), nullable=True)


class AppUser(IdMixin, TimestampMixin, Base):
    __tablename__ = "app_user"

    username: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(enum_type(Role, "role"))
    territory_id: Mapped[int | None] = fk("territory.id", nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(server_default="true")
    locale: Mapped[Locale] = mapped_column(enum_type(Locale, "locale"), server_default=Locale.ru.value)
    # Part of every access token; raising it revokes all tokens issued before (logout, new password, deactivation).
    token_version: Mapped[int] = mapped_column(default=0, server_default="0")
