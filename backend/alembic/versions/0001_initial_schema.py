"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-13 17:07:59.122941
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


APPEND_ONLY_TABLES = ("evidence", "audit_log", "risk_factor_change")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE SEQUENCE object_code_seq START 1")
    op.create_table(
        "app_setting",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_setting")),
    )
    op.create_table(
        "developer",
        sa.Column("bin", sa.String(length=12), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("director", sa.String(length=255), nullable=True),
        sa.Column(
            "founders",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("authorized_company", sa.String(length=255), nullable=True),
        sa.Column("phones", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("bin ~ '^[0-9]{12}$'", name=op.f("ck_developer_bin_format")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_developer")),
        sa.UniqueConstraint("bin", name=op.f("uq_developer_bin")),
    )
    op.create_table(
        "holiday",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "holiday",
                "workday",
                name="holiday_kind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('holiday', 'workday')", name=op.f("ck_holiday_holiday_kind")),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_holiday")),
    )
    op.create_table(
        "phrase",
        sa.Column("text", sa.String(length=255), nullable=False),
        sa.Column("variants", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "booking",
                "down_payment",
                "installment",
                "sales_start",
                "preliminary_contract",
                "deposit",
                "price_before_completion",
                "covert_contract",
                name="phrase_category",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('booking', 'down_payment', 'installment', 'sales_start', 'preliminary_contract', 'deposit', 'price_before_completion', 'covert_contract')",
            name=op.f("ck_phrase_phrase_category"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_phrase")),
        sa.UniqueConstraint("category", "text", name=op.f("uq_phrase_category")),
    )
    op.create_table(
        "risk_factor",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_risk_factor")),
    )
    op.create_table(
        "signal_counter",
        sa.Column("year", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("last_number", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("year", name=op.f("pk_signal_counter")),
    )
    op.create_table(
        "territory",
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "level",
            sa.Enum(
                "region",
                "city",
                name="territory_level",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default="Asia/Almaty",
            nullable=False,
        ),
        sa.Column(
            "center",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column(
            "boundary",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("level IN ('region', 'city')", name=op.f("ck_territory_territory_level")),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["territory.id"],
            name=op.f("fk_territory_parent_id_territory"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_territory")),
        sa.UniqueConstraint("code", name=op.f("uq_territory_code")),
    )
    op.create_index(
        "ix_territory_boundary",
        "territory",
        ["boundary"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_territory_center",
        "territory",
        ["center"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(op.f("ix_territory_parent_id"), "territory", ["parent_id"], unique=False)
    op.create_table(
        "app_user",
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "admin",
                "mio_officer",
                "gask",
                "law_enforcement",
                name="role",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("territory_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "locale",
            sa.Enum("ru", "kk", name="locale", native_enum=False),
            server_default="ru",
            nullable=False,
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("locale IN ('ru', 'kk')", name=op.f("ck_app_user_locale")),
        sa.CheckConstraint(
            "role IN ('admin', 'mio_officer', 'gask', 'law_enforcement')",
            name=op.f("ck_app_user_role"),
        ),
        sa.ForeignKeyConstraint(
            ["territory_id"],
            ["territory.id"],
            name=op.f("fk_app_user_territory_id_territory"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_user")),
        sa.UniqueConstraint("username", name=op.f("uq_app_user_username")),
    )
    op.create_index(op.f("ix_app_user_territory_id"), "app_user", ["territory_id"], unique=False)
    op.create_table(
        "district",
        sa.Column("territory_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "boundary",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["territory_id"],
            ["territory.id"],
            name=op.f("fk_district_territory_id_territory"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_district")),
        sa.UniqueConstraint("territory_id", "name", name=op.f("uq_district_territory_id")),
    )
    op.create_index(
        "ix_district_boundary",
        "district",
        ["boundary"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(op.f("ix_district_territory_id"), "district", ["territory_id"], unique=False)
    op.create_table(
        "audit_log",
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], name=op.f("fk_audit_log_user_id_app_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"], unique=False)
    op.create_index("ix_audit_log_user_at", "audit_log", ["user_id", "at"], unique=False)
    op.create_table(
        "construction_object",
        sa.Column(
            "code",
            sa.String(length=32),
            server_default=sa.text("'SQ-OBJ-' || lpad(nextval('object_code_seq')::text, 4, '0')"),
            nullable=False,
        ),
        sa.Column("territory_id", sa.BigInteger(), nullable=False),
        sa.Column("district_id", sa.BigInteger(), nullable=True),
        sa.Column("developer_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("cadastral_number", sa.String(length=64), nullable=True),
        sa.Column("land_purpose", sa.String(length=255), nullable=True),
        sa.Column(
            "location",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("planned_completion", sa.Date(), nullable=True),
        sa.Column("forecast_completion", sa.Date(), nullable=True),
        sa.Column(
            "construction_status",
            sa.Enum(
                "not_started",
                "active",
                "stalled",
                "completed",
                name="construction_status",
                native_enum=False,
            ),
            server_default="active",
            nullable=False,
        ),
        sa.Column("stalled_since", sa.Date(), nullable=True),
        sa.Column("readiness_actual_pct", sa.Integer(), nullable=True),
        sa.Column("readiness_claimed_pct", sa.Integer(), nullable=True),
        sa.Column("prior_violations", sa.Text(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column(
            "zone",
            sa.Enum(
                "green",
                "yellow",
                "red",
                name="zone",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "key_status",
            sa.Enum(
                "no_permit_with_offer",
                "no_permit",
                "permit_checking",
                "money_offer",
                "stalled",
                "overdue",
                "complaints",
                "readiness_overstated",
                "ok",
                name="key_status",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("last_scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_demo", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "construction_status IN ('not_started', 'active', 'stalled', 'completed')",
            name=op.f("ck_construction_object_construction_status"),
        ),
        sa.CheckConstraint(
            "key_status IN ('no_permit_with_offer', 'no_permit', 'permit_checking', 'money_offer', 'stalled', 'overdue', 'complaints', 'readiness_overstated', 'ok')",
            name=op.f("ck_construction_object_key_status"),
        ),
        sa.CheckConstraint(
            "zone IN ('green', 'yellow', 'red')",
            name=op.f("ck_construction_object_zone"),
        ),
        sa.CheckConstraint(
            "readiness_actual_pct BETWEEN 0 AND 100",
            name=op.f("ck_construction_object_readiness_actual_range"),
        ),
        sa.CheckConstraint(
            "readiness_claimed_pct BETWEEN 0 AND 100",
            name=op.f("ck_construction_object_readiness_claimed_range"),
        ),
        sa.ForeignKeyConstraint(
            ["developer_id"],
            ["developer.id"],
            name=op.f("fk_construction_object_developer_id_developer"),
        ),
        sa.ForeignKeyConstraint(
            ["district_id"],
            ["district.id"],
            name=op.f("fk_construction_object_district_id_district"),
        ),
        sa.ForeignKeyConstraint(
            ["territory_id"],
            ["territory.id"],
            name=op.f("fk_construction_object_territory_id_territory"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_construction_object")),
        sa.UniqueConstraint("code", name=op.f("uq_construction_object_code")),
    )
    op.create_index(
        "ix_construction_object_address_trgm",
        "construction_object",
        ["address"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"address": "gin_trgm_ops"},
    )
    op.create_index(
        op.f("ix_construction_object_cadastral_number"),
        "construction_object",
        ["cadastral_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_construction_object_developer_id"),
        "construction_object",
        ["developer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_construction_object_district_id"),
        "construction_object",
        ["district_id"],
        unique=False,
    )
    op.create_index(
        "ix_construction_object_location",
        "construction_object",
        ["location"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_construction_object_name_trgm",
        "construction_object",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_construction_object_next_check_at",
        "construction_object",
        ["next_check_at"],
        unique=False,
    )
    op.create_index(
        "ix_construction_object_territory_zone_score",
        "construction_object",
        ["territory_id", "zone", "score"],
        unique=False,
    )
    op.create_table(
        "notification",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "red_zone",
                "signal_returned",
                "signal_sent",
                "signal_due_soon",
                "signal_overdue",
                "signal_responded",
                "capture_failed",
                name="notification_kind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.CheckConstraint(
            "kind IN ('red_zone', 'signal_returned', 'signal_sent', 'signal_due_soon', 'signal_overdue', 'signal_responded', 'capture_failed')",
            name=op.f("ck_notification_notification_kind"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], name=op.f("fk_notification_user_id_app_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification")),
    )
    op.create_index(
        "ix_notification_user_read_created",
        "notification",
        ["user_id", "read_at", "created_at"],
        unique=False,
    )
    op.create_table(
        "risk_factor_change",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("old_weight", sa.Integer(), nullable=False),
        sa.Column("new_weight", sa.Integer(), nullable=False),
        sa.Column("old_active", sa.Boolean(), nullable=False),
        sa.Column("new_active", sa.Boolean(), nullable=False),
        sa.Column("changed_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["app_user.id"],
            name=op.f("fk_risk_factor_change_changed_by_app_user"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_factor_change")),
    )
    op.create_index(op.f("ix_risk_factor_change_code"), "risk_factor_change", ["code"], unique=False)
    op.create_table(
        "complaint",
        sa.Column("object_id", sa.BigInteger(), nullable=False),
        sa.Column("received_at", sa.Date(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "eotinish",
                "manual",
                "other",
                name="complaint_source",
                native_enum=False,
            ),
            server_default="manual",
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("is_collective", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("signatories_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "in_review",
                "closed",
                name="complaint_status",
                native_enum=False,
            ),
            server_default="new",
            nullable=False,
        ),
        sa.Column("confirmed_payments", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('eotinish', 'manual', 'other')",
            name=op.f("ck_complaint_complaint_source"),
        ),
        sa.CheckConstraint(
            "status IN ('new', 'in_review', 'closed')",
            name=op.f("ck_complaint_complaint_status"),
        ),
        sa.CheckConstraint("signatories_count >= 1", name=op.f("ck_complaint_signatories_positive")),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["construction_object.id"],
            name=op.f("fk_complaint_object_id_construction_object"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_complaint")),
    )
    op.create_index("ix_complaint_object_status", "complaint", ["object_id", "status"], unique=False)
    op.create_index(
        "uq_complaint_source_external_id",
        "complaint",
        ["source", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.create_table(
        "document",
        sa.Column("object_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "doc_type",
            sa.Enum(
                "smr_notice",
                "psd",
                "expertise",
                "dsu_permit",
                "guarantee",
                "ddu_registration",
                "land_title",
                name="doc_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("number", sa.String(length=128), nullable=True),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("issuer", sa.String(length=255), nullable=True),
        sa.Column(
            "check_status",
            sa.Enum(
                "confirmed",
                "not_found",
                "checking",
                name="check_status",
                native_enum=False,
            ),
            server_default="checking",
            nullable=False,
        ),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "check_source",
            sa.Enum(
                "housing_portal",
                "kazreestr",
                "mio_registry",
                "cadastre",
                "eotinish",
                "manual",
                "other",
                name="check_source",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "check_source IN ('housing_portal', 'kazreestr', 'mio_registry', 'cadastre', 'eotinish', 'manual', 'other')",
            name=op.f("ck_document_check_source"),
        ),
        sa.CheckConstraint(
            "check_status IN ('confirmed', 'not_found', 'checking')",
            name=op.f("ck_document_check_status"),
        ),
        sa.CheckConstraint(
            "doc_type IN ('smr_notice', 'psd', 'expertise', 'dsu_permit', 'guarantee', 'ddu_registration', 'land_title')",
            name=op.f("ck_document_doc_type"),
        ),
        sa.ForeignKeyConstraint(
            ["checked_by"],
            ["app_user.id"],
            name=op.f("fk_document_checked_by_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["construction_object.id"],
            name=op.f("fk_document_object_id_construction_object"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document")),
    )
    op.create_index(
        "ix_document_object_doc_type",
        "document",
        ["object_id", "doc_type"],
        unique=False,
    )
    op.create_table(
        "inspection",
        sa.Column("object_id", sa.BigInteger(), nullable=False),
        sa.Column("inspected_at", sa.Date(), nullable=False),
        sa.Column("readiness_pct", sa.Integer(), nullable=False),
        sa.Column(
            "location",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("inspector_id", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "readiness_pct BETWEEN 0 AND 100",
            name=op.f("ck_inspection_readiness_range"),
        ),
        sa.ForeignKeyConstraint(
            ["inspector_id"],
            ["app_user.id"],
            name=op.f("fk_inspection_inspector_id_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["construction_object.id"],
            name=op.f("fk_inspection_object_id_construction_object"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inspection")),
    )
    op.create_index(
        "ix_inspection_location",
        "inspection",
        ["location"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_inspection_object_inspected_at",
        "inspection",
        ["object_id", "inspected_at"],
        unique=False,
    )
    op.create_table(
        "linked_entity",
        sa.Column("object_id", sa.BigInteger(), nullable=True),
        sa.Column("developer_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "kind",
            sa.Enum(
                "ad_account",
                "sales_office",
                "phone",
                "website",
                "bank_details",
                name="linked_entity_kind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('ad_account', 'sales_office', 'phone', 'website', 'bank_details')",
            name=op.f("ck_linked_entity_linked_entity_kind"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(object_id, developer_id) = 1",
            name=op.f("ck_linked_entity_exactly_one_owner"),
        ),
        sa.ForeignKeyConstraint(
            ["developer_id"],
            ["developer.id"],
            name=op.f("fk_linked_entity_developer_id_developer"),
        ),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["construction_object.id"],
            name=op.f("fk_linked_entity_object_id_construction_object"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_linked_entity")),
        sa.UniqueConstraint("developer_id", "kind", "value", name=op.f("uq_linked_entity_developer_id")),
        sa.UniqueConstraint("object_id", "kind", "value", name=op.f("uq_linked_entity_object_id")),
    )
    op.create_index("ix_linked_entity_kind_value", "linked_entity", ["kind", "value"], unique=False)
    op.create_table(
        "risk_score",
        sa.Column("object_id", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column(
            "zone",
            sa.Enum(
                "green",
                "yellow",
                "red",
                name="zone",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "zone_reasons",
            postgresql.ARRAY(sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "trigger",
            sa.Enum(
                "event",
                "schedule",
                "manual",
                name="score_trigger",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.CheckConstraint(
            "trigger IN ('event', 'schedule', 'manual')",
            name=op.f("ck_risk_score_score_trigger"),
        ),
        sa.CheckConstraint("zone IN ('green', 'yellow', 'red')", name=op.f("ck_risk_score_zone")),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["construction_object.id"],
            name=op.f("fk_risk_score_object_id_construction_object"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_score")),
    )
    op.create_index(
        "ix_risk_score_object_calculated",
        "risk_score",
        ["object_id", "calculated_at"],
        unique=False,
    )
    op.create_table(
        "signal_card",
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("object_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "requires_confirmation",
                "returned",
                "sent",
                "responded",
                "closed",
                name="signal_status",
                native_enum=False,
            ),
            server_default="requires_confirmation",
            nullable=False,
        ),
        sa.Column(
            "origin",
            sa.Enum(
                "auto",
                "manual",
                name="signal_origin",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "sections",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "recipient",
            sa.Enum(
                "mio",
                "gask",
                "law_enforcement",
                name="recipient",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("review_days", sa.Integer(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_by", sa.BigInteger(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("return_comment", sa.Text(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_by", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("origin IN ('auto', 'manual')", name=op.f("ck_signal_card_signal_origin")),
        sa.CheckConstraint(
            "recipient IN ('mio', 'gask', 'law_enforcement')",
            name=op.f("ck_signal_card_recipient"),
        ),
        sa.CheckConstraint(
            "status IN ('requires_confirmation', 'returned', 'sent', 'responded', 'closed')",
            name=op.f("ck_signal_card_signal_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_signal_card_created_by_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["construction_object.id"],
            name=op.f("fk_signal_card_object_id_construction_object"),
        ),
        sa.ForeignKeyConstraint(
            ["responded_by"],
            ["app_user.id"],
            name=op.f("fk_signal_card_responded_by_app_user"),
        ),
        sa.ForeignKeyConstraint(["sent_by"], ["app_user.id"], name=op.f("fk_signal_card_sent_by_app_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signal_card")),
        sa.UniqueConstraint("number", name=op.f("uq_signal_card_number")),
    )
    op.create_index(
        "ix_signal_card_object_status",
        "signal_card",
        ["object_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_signal_card_status_due_date",
        "signal_card",
        ["status", "due_date"],
        unique=False,
    )
    op.create_table(
        "source_account",
        sa.Column(
            "platform",
            sa.Enum(
                "instagram",
                "tiktok",
                "telegram",
                "website",
                "aggregator",
                "outdoor",
                "other",
                name="platform",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("handle", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("object_id", sa.BigInteger(), nullable=True),
        sa.Column("developer_id", sa.BigInteger(), nullable=True),
        sa.Column("territory_id", sa.BigInteger(), nullable=True),
        sa.Column("is_watched", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "platform IN ('instagram', 'tiktok', 'telegram', 'website', 'aggregator', 'outdoor', 'other')",
            name=op.f("ck_source_account_platform"),
        ),
        sa.ForeignKeyConstraint(
            ["developer_id"],
            ["developer.id"],
            name=op.f("fk_source_account_developer_id_developer"),
        ),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["construction_object.id"],
            name=op.f("fk_source_account_object_id_construction_object"),
        ),
        sa.ForeignKeyConstraint(
            ["territory_id"],
            ["territory.id"],
            name=op.f("fk_source_account_territory_id_territory"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_account")),
        sa.UniqueConstraint("platform", "handle", name=op.f("uq_source_account_platform")),
    )
    op.create_index(
        op.f("ix_source_account_developer_id"),
        "source_account",
        ["developer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_source_account_object_id"),
        "source_account",
        ["object_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_source_account_territory_id"),
        "source_account",
        ["territory_id"],
        unique=False,
    )
    op.create_table(
        "ad_post",
        sa.Column("territory_id", sa.BigInteger(), nullable=True),
        sa.Column("source_account_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "platform",
            sa.Enum(
                "instagram",
                "tiktok",
                "telegram",
                "website",
                "aggregator",
                "outdoor",
                "other",
                name="platform",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("phones", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("links", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("object_id", sa.BigInteger(), nullable=True),
        sa.Column("link_confidence", sa.Float(), nullable=True),
        sa.Column(
            "link_method",
            sa.Enum(
                "account",
                "phone",
                "name",
                "manual",
                name="link_method",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "payment_schemes",
            postgresql.ARRAY(sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("claimed_readiness_pct", sa.Integer(), nullable=True),
        sa.Column(
            "price_before_completion",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("llm_extraction", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "llm_status",
            sa.Enum(
                "none",
                "pending",
                "done",
                "failed",
                "disabled",
                name="llm_status",
                native_enum=False,
            ),
            server_default="none",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "captured",
                "verification",
                "removed_saved",
                name="ad_status",
                native_enum=False,
            ),
            server_default="captured",
            nullable=False,
        ),
        sa.Column("max_phrase_weight", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_phrase_weight", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_outdoor", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "location",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "capture_status",
            sa.Enum(
                "pending",
                "done",
                "failed",
                name="capture_status",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("capture_error", sa.Text(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "capture_status IN ('pending', 'done', 'failed')",
            name=op.f("ck_ad_post_capture_status"),
        ),
        sa.CheckConstraint(
            "link_method IN ('account', 'phone', 'name', 'manual')",
            name=op.f("ck_ad_post_link_method"),
        ),
        sa.CheckConstraint(
            "llm_status IN ('none', 'pending', 'done', 'failed', 'disabled')",
            name=op.f("ck_ad_post_llm_status"),
        ),
        sa.CheckConstraint(
            "platform IN ('instagram', 'tiktok', 'telegram', 'website', 'aggregator', 'outdoor', 'other')",
            name=op.f("ck_ad_post_platform"),
        ),
        sa.CheckConstraint(
            "status IN ('captured', 'verification', 'removed_saved')",
            name=op.f("ck_ad_post_ad_status"),
        ),
        sa.CheckConstraint(
            "link_confidence BETWEEN 0 AND 1",
            name=op.f("ck_ad_post_link_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["construction_object.id"],
            name=op.f("fk_ad_post_object_id_construction_object"),
        ),
        sa.ForeignKeyConstraint(
            ["source_account_id"],
            ["source_account.id"],
            name=op.f("fk_ad_post_source_account_id_source_account"),
        ),
        sa.ForeignKeyConstraint(
            ["territory_id"],
            ["territory.id"],
            name=op.f("fk_ad_post_territory_id_territory"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ad_post")),
        sa.UniqueConstraint("platform", "external_id", name=op.f("uq_ad_post_platform")),
    )
    op.create_index("ix_ad_post_last_checked_at", "ad_post", ["last_checked_at"], unique=False)
    op.create_index(
        "ix_ad_post_location",
        "ad_post",
        ["location"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_ad_post_object_published",
        "ad_post",
        ["object_id", "published_at"],
        unique=False,
    )
    op.create_index(
        "ix_ad_post_sort",
        "ad_post",
        ["max_phrase_weight", "published_at"],
        unique=False,
    )
    op.create_index("ix_ad_post_status", "ad_post", ["status"], unique=False)
    op.create_index(op.f("ix_ad_post_territory_id"), "ad_post", ["territory_id"], unique=False)
    op.create_table(
        "evidence",
        sa.Column(
            "kind",
            sa.Enum(
                "screenshot_png",
                "archive_mhtml",
                "photo",
                "document_scan",
                "pdf",
                name="evidence_kind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("s3_key", sa.String(length=1024), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "lock_mode",
            sa.Enum(
                "GOVERNANCE",
                "COMPLIANCE",
                name="lock_mode",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("tsa_token", sa.LargeBinary(), nullable=True),
        sa.Column("ad_post_id", sa.BigInteger(), nullable=True),
        sa.Column("document_id", sa.BigInteger(), nullable=True),
        sa.Column("inspection_id", sa.BigInteger(), nullable=True),
        sa.Column("signal_card_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.CheckConstraint(
            "kind IN ('screenshot_png', 'archive_mhtml', 'photo', 'document_scan', 'pdf')",
            name=op.f("ck_evidence_evidence_kind"),
        ),
        sa.CheckConstraint(
            "lock_mode IN ('GOVERNANCE', 'COMPLIANCE')",
            name=op.f("ck_evidence_lock_mode"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(ad_post_id, document_id, inspection_id, signal_card_id) = 1",
            name=op.f("ck_evidence_exactly_one_owner"),
        ),
        sa.ForeignKeyConstraint(["ad_post_id"], ["ad_post.id"], name=op.f("fk_evidence_ad_post_id_ad_post")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_evidence_created_by_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_evidence_document_id_document"),
        ),
        sa.ForeignKeyConstraint(
            ["inspection_id"],
            ["inspection.id"],
            name=op.f("fk_evidence_inspection_id_inspection"),
        ),
        sa.ForeignKeyConstraint(
            ["signal_card_id"],
            ["signal_card.id"],
            name=op.f("fk_evidence_signal_card_id_signal_card"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence")),
        sa.UniqueConstraint("bucket", "s3_key", name=op.f("uq_evidence_bucket")),
    )
    op.create_index(op.f("ix_evidence_ad_post_id"), "evidence", ["ad_post_id"], unique=False)
    op.create_index(op.f("ix_evidence_document_id"), "evidence", ["document_id"], unique=False)
    op.create_index(op.f("ix_evidence_inspection_id"), "evidence", ["inspection_id"], unique=False)
    op.create_index("ix_evidence_sha256", "evidence", ["sha256"], unique=False)
    op.create_index(op.f("ix_evidence_signal_card_id"), "evidence", ["signal_card_id"], unique=False)
    op.create_table(
        "phrase_hit",
        sa.Column("ad_post_id", sa.BigInteger(), nullable=False),
        sa.Column("phrase_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "category",
            sa.Enum(
                "booking",
                "down_payment",
                "installment",
                "sales_start",
                "preliminary_contract",
                "deposit",
                "price_before_completion",
                "covert_contract",
                name="phrase_category",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("matched_text", sa.Text(), nullable=False),
        sa.Column("start", sa.Integer(), nullable=False),
        sa.Column("end", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column(
            "detected_by",
            sa.Enum(
                "dictionary",
                "llm",
                name="detected_by",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("confirmed", sa.Boolean(), nullable=True),
        sa.Column("confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('booking', 'down_payment', 'installment', 'sales_start', 'preliminary_contract', 'deposit', 'price_before_completion', 'covert_contract')",
            name=op.f("ck_phrase_hit_phrase_category"),
        ),
        sa.CheckConstraint(
            "detected_by IN ('dictionary', 'llm')",
            name=op.f("ck_phrase_hit_detected_by"),
        ),
        sa.ForeignKeyConstraint(
            ["ad_post_id"],
            ["ad_post.id"],
            name=op.f("fk_phrase_hit_ad_post_id_ad_post"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["app_user.id"],
            name=op.f("fk_phrase_hit_confirmed_by_app_user"),
        ),
        sa.ForeignKeyConstraint(["phrase_id"], ["phrase.id"], name=op.f("fk_phrase_hit_phrase_id_phrase")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_phrase_hit")),
    )
    op.create_index("ix_phrase_hit_ad_post", "phrase_hit", ["ad_post_id"], unique=False)

    op.execute(
        """
        CREATE FUNCTION forbid_modification() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% on table % is forbidden: the table is append-only', TG_OP, TG_TABLE_NAME
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION forbid_modification()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION forbid_modification()"
        )


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER {table}_no_truncate ON {table}")
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.execute("DROP FUNCTION forbid_modification()")
    op.drop_index("ix_phrase_hit_ad_post", table_name="phrase_hit")
    op.drop_table("phrase_hit")
    op.drop_index(op.f("ix_evidence_signal_card_id"), table_name="evidence")
    op.drop_index("ix_evidence_sha256", table_name="evidence")
    op.drop_index(op.f("ix_evidence_inspection_id"), table_name="evidence")
    op.drop_index(op.f("ix_evidence_document_id"), table_name="evidence")
    op.drop_index(op.f("ix_evidence_ad_post_id"), table_name="evidence")
    op.drop_table("evidence")
    op.drop_index(op.f("ix_ad_post_territory_id"), table_name="ad_post")
    op.drop_index("ix_ad_post_status", table_name="ad_post")
    op.drop_index("ix_ad_post_sort", table_name="ad_post")
    op.drop_index("ix_ad_post_object_published", table_name="ad_post")
    op.drop_index("ix_ad_post_location", table_name="ad_post", postgresql_using="gist")
    op.drop_index("ix_ad_post_last_checked_at", table_name="ad_post")
    op.drop_table("ad_post")
    op.drop_index(op.f("ix_source_account_territory_id"), table_name="source_account")
    op.drop_index(op.f("ix_source_account_object_id"), table_name="source_account")
    op.drop_index(op.f("ix_source_account_developer_id"), table_name="source_account")
    op.drop_table("source_account")
    op.drop_index("ix_signal_card_status_due_date", table_name="signal_card")
    op.drop_index("ix_signal_card_object_status", table_name="signal_card")
    op.drop_table("signal_card")
    op.drop_index("ix_risk_score_object_calculated", table_name="risk_score")
    op.drop_table("risk_score")
    op.drop_index("ix_linked_entity_kind_value", table_name="linked_entity")
    op.drop_table("linked_entity")
    op.drop_index("ix_inspection_object_inspected_at", table_name="inspection")
    op.drop_index("ix_inspection_location", table_name="inspection", postgresql_using="gist")
    op.drop_table("inspection")
    op.drop_index("ix_document_object_doc_type", table_name="document")
    op.drop_table("document")
    op.drop_index(
        "uq_complaint_source_external_id",
        table_name="complaint",
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.drop_index("ix_complaint_object_status", table_name="complaint")
    op.drop_table("complaint")
    op.drop_index(op.f("ix_risk_factor_change_code"), table_name="risk_factor_change")
    op.drop_table("risk_factor_change")
    op.drop_index("ix_notification_user_read_created", table_name="notification")
    op.drop_table("notification")
    op.drop_index("ix_construction_object_territory_zone_score", table_name="construction_object")
    op.drop_index("ix_construction_object_next_check_at", table_name="construction_object")
    op.drop_index(
        "ix_construction_object_name_trgm",
        table_name="construction_object",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.drop_index(
        "ix_construction_object_location",
        table_name="construction_object",
        postgresql_using="gist",
    )
    op.drop_index(op.f("ix_construction_object_district_id"), table_name="construction_object")
    op.drop_index(op.f("ix_construction_object_developer_id"), table_name="construction_object")
    op.drop_index(
        op.f("ix_construction_object_cadastral_number"),
        table_name="construction_object",
    )
    op.drop_index(
        "ix_construction_object_address_trgm",
        table_name="construction_object",
        postgresql_using="gin",
        postgresql_ops={"address": "gin_trgm_ops"},
    )
    op.drop_table("construction_object")
    op.drop_index("ix_audit_log_user_at", table_name="audit_log")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index(op.f("ix_district_territory_id"), table_name="district")
    op.drop_index("ix_district_boundary", table_name="district", postgresql_using="gist")
    op.drop_table("district")
    op.drop_index(op.f("ix_app_user_territory_id"), table_name="app_user")
    op.drop_table("app_user")
    op.drop_index(op.f("ix_territory_parent_id"), table_name="territory")
    op.drop_index("ix_territory_center", table_name="territory", postgresql_using="gist")
    op.drop_index("ix_territory_boundary", table_name="territory", postgresql_using="gist")
    op.drop_table("territory")
    op.drop_table("signal_counter")
    op.drop_table("risk_factor")
    op.drop_table("phrase")
    op.drop_table("holiday")
    op.drop_table("developer")
    op.drop_table("app_setting")
    op.execute("DROP SEQUENCE object_code_seq")
