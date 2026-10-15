from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Developer(IdMixin, TimestampMixin, Base):
    __tablename__ = "developer"
    __table_args__ = (CheckConstraint("bin ~ '^[0-9]{12}$'", name="bin_format"),)

    bin: Mapped[str] = mapped_column(String(12), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    director: Mapped[str | None] = mapped_column(String(255))
    founders: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")
    authorized_company: Mapped[str | None] = mapped_column(String(255))
    phones: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
