from datetime import datetime
from enum import StrEnum
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Identity, MetaData, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedColumn, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
        list[str]: ARRAY(Text),
    }


class IdMixin:
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


def enum_type[E: StrEnum](enum_cls: type[E], name: str) -> Enum:
    """Enum stored as VARCHAR with a CHECK constraint (no native PG enum: easier to evolve)."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda members: [member.value for member in members],
    )


def fk(target: str, *, nullable: bool = False, ondelete: str | None = None, index: bool = False) -> MappedColumn[int]:
    return mapped_column(BigInteger, ForeignKey(target, ondelete=ondelete), nullable=nullable, index=index)


def point() -> Geometry:
    # GiST indexes are declared explicitly in __table_args__ (spatial_index=False) so that
    # Alembic autogenerate treats them like any other index.
    return Geometry("POINT", srid=4326, spatial_index=False)


def multipolygon() -> Geometry:
    return Geometry("MULTIPOLYGON", srid=4326, spatial_index=False)
