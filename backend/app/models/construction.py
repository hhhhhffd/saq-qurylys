from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin, enum_type, fk, point
from app.models.enums import (
    CheckSource,
    CheckStatus,
    ComplaintSource,
    ComplaintStatus,
    ConstructionStatus,
    DocType,
    KeyStatus,
    LinkedEntityKind,
    Zone,
)

if TYPE_CHECKING:
    from app.models.evidence import Evidence

OBJECT_CODE_DEFAULT = text("'SQ-OBJ-' || lpad(nextval('object_code_seq')::text, 4, '0')")


class ConstructionObject(IdMixin, TimestampMixin, Base):
    __tablename__ = "construction_object"
    __table_args__ = (
        CheckConstraint("readiness_actual_pct BETWEEN 0 AND 100", name="readiness_actual_range"),
        CheckConstraint("readiness_claimed_pct BETWEEN 0 AND 100", name="readiness_claimed_range"),
        Index("ix_construction_object_location", "location", postgresql_using="gist"),
        Index(
            "ix_construction_object_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "ix_construction_object_address_trgm",
            "address",
            postgresql_using="gin",
            postgresql_ops={"address": "gin_trgm_ops"},
        ),
        Index("ix_construction_object_territory_zone_score", "territory_id", "zone", "score"),
        Index("ix_construction_object_next_check_at", "next_check_at"),
    )

    code: Mapped[str] = mapped_column(String(32), unique=True, server_default=OBJECT_CODE_DEFAULT)
    territory_id: Mapped[int] = fk("territory.id")
    district_id: Mapped[int | None] = fk("district.id", nullable=True, index=True)
    developer_id: Mapped[int | None] = fk("developer.id", nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    address: Mapped[str | None] = mapped_column(String(500))
    cadastral_number: Mapped[str | None] = mapped_column(String(64), index=True)
    land_purpose: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[Any] = mapped_column(point(), nullable=True)
    lat: Mapped[float | None] = column_property(func.ST_Y(location))
    lon: Mapped[float | None] = column_property(func.ST_X(location))
    planned_completion: Mapped[date | None]
    forecast_completion: Mapped[date | None]
    construction_status: Mapped[ConstructionStatus] = mapped_column(
        enum_type(ConstructionStatus, "construction_status"),
        server_default=ConstructionStatus.active.value,
    )
    stalled_since: Mapped[date | None]
    readiness_actual_pct: Mapped[int | None]
    readiness_claimed_pct: Mapped[int | None]
    prior_violations: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int | None]
    zone: Mapped[Zone | None] = mapped_column(enum_type(Zone, "zone"))
    key_status: Mapped[KeyStatus | None] = mapped_column(enum_type(KeyStatus, "key_status"))
    last_scored_at: Mapped[datetime | None]
    next_check_at: Mapped[datetime | None]
    is_demo: Mapped[bool] = mapped_column(server_default="false")

    # Read-only collections for the object card; loaded on access, not with list queries.
    documents: Mapped[list["Document"]] = relationship(viewonly=True, order_by="Document.id")
    inspections: Mapped[list["Inspection"]] = relationship(
        viewonly=True, order_by="Inspection.inspected_at.desc(), Inspection.id.desc()"
    )
    complaints: Mapped[list["Complaint"]] = relationship(
        viewonly=True, order_by="Complaint.received_at.desc(), Complaint.id.desc()"
    )
    linked_entities: Mapped[list["LinkedEntity"]] = relationship(viewonly=True, order_by="LinkedEntity.id")


class Document(IdMixin, TimestampMixin, Base):
    __tablename__ = "document"
    __table_args__ = (Index("ix_document_object_doc_type", "object_id", "doc_type"),)

    object_id: Mapped[int] = fk("construction_object.id")
    doc_type: Mapped[DocType] = mapped_column(enum_type(DocType, "doc_type"))
    number: Mapped[str | None] = mapped_column(String(128))
    issued_at: Mapped[date | None]
    issuer: Mapped[str | None] = mapped_column(String(255))
    check_status: Mapped[CheckStatus] = mapped_column(
        enum_type(CheckStatus, "check_status"), server_default=CheckStatus.checking.value
    )
    checked_at: Mapped[datetime | None]
    checked_by: Mapped[int | None] = fk("app_user.id", nullable=True)
    check_source: Mapped[CheckSource | None] = mapped_column(enum_type(CheckSource, "check_source"))
    note: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list["Evidence"]] = relationship(
        "Evidence", viewonly=True, lazy="selectin", order_by="Evidence.id"
    )


class Inspection(IdMixin, TimestampMixin, Base):
    __tablename__ = "inspection"
    __table_args__ = (
        CheckConstraint("readiness_pct BETWEEN 0 AND 100", name="readiness_range"),
        Index("ix_inspection_object_inspected_at", "object_id", "inspected_at"),
        Index("ix_inspection_location", "location", postgresql_using="gist"),
    )

    object_id: Mapped[int] = fk("construction_object.id")
    inspected_at: Mapped[date]
    readiness_pct: Mapped[int]
    location: Mapped[Any] = mapped_column(point(), nullable=True)
    lat: Mapped[float | None] = column_property(func.ST_Y(location))
    lon: Mapped[float | None] = column_property(func.ST_X(location))
    inspector_id: Mapped[int | None] = fk("app_user.id", nullable=True)
    note: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list["Evidence"]] = relationship(
        "Evidence", viewonly=True, lazy="selectin", order_by="Evidence.id"
    )


class Complaint(IdMixin, TimestampMixin, Base):
    __tablename__ = "complaint"
    __table_args__ = (
        CheckConstraint("signatories_count >= 1", name="signatories_positive"),
        Index("ix_complaint_object_status", "object_id", "status"),
        Index(
            "uq_complaint_source_external_id",
            "source",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
    )

    object_id: Mapped[int] = fk("construction_object.id")
    received_at: Mapped[date]
    source: Mapped[ComplaintSource] = mapped_column(
        enum_type(ComplaintSource, "complaint_source"), server_default=ComplaintSource.manual.value
    )
    external_id: Mapped[str | None] = mapped_column(String(128))
    is_collective: Mapped[bool] = mapped_column(server_default="false")
    signatories_count: Mapped[int] = mapped_column(server_default="1")
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ComplaintStatus] = mapped_column(
        enum_type(ComplaintStatus, "complaint_status"), server_default=ComplaintStatus.new.value
    )
    confirmed_payments: Mapped[bool] = mapped_column(server_default="false")


class LinkedEntity(IdMixin, TimestampMixin, Base):
    __tablename__ = "linked_entity"
    __table_args__ = (
        CheckConstraint("num_nonnulls(object_id, developer_id) = 1", name="exactly_one_owner"),
        UniqueConstraint("object_id", "kind", "value"),
        UniqueConstraint("developer_id", "kind", "value"),
        Index("ix_linked_entity_kind_value", "kind", "value"),
    )

    object_id: Mapped[int | None] = fk("construction_object.id", nullable=True)
    developer_id: Mapped[int | None] = fk("developer.id", nullable=True)
    kind: Mapped[LinkedEntityKind] = mapped_column(enum_type(LinkedEntityKind, "linked_entity_kind"))
    value: Mapped[str] = mapped_column(String(500))
    note: Mapped[str | None] = mapped_column(Text)
