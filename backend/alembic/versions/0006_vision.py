"""SAQ VISION: sessions, uploaded originals, processing jobs, frames, findings and their append-only reviews

- vision_review is append-only like evidence and ad_post_version (forbid_modification() comes from 0001).
- ad_post.origin gains `vision`: publications created from a confirmed outdoor-advertising finding.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-16 00:37:54
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_origin_check(values: Sequence[str]) -> None:
    op.drop_constraint(op.f("ck_ad_post_ad_origin"), "ad_post", type_="check")
    op.create_check_constraint(
        op.f("ck_ad_post_ad_origin"), "ad_post", "origin IN (" + ", ".join(f"'{value}'" for value in values) + ")"
    )


def upgrade() -> None:
    op.create_table(
        "vision_session",
        sa.Column("territory_id", sa.BigInteger(), nullable=False),
        sa.Column("object_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=6),
            nullable=False,
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=8),
            server_default="open",
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "source IN ('drone', 'camera', 'phone', 'other')", name=op.f("ck_vision_session_vision_source")
        ),
        sa.CheckConstraint("status IN ('open', 'reviewed')", name=op.f("ck_vision_session_vision_session_status")),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], name=op.f("fk_vision_session_created_by_app_user")),
        sa.ForeignKeyConstraint(
            ["object_id"], ["construction_object.id"], name=op.f("fk_vision_session_object_id_construction_object")
        ),
        sa.ForeignKeyConstraint(["reviewed_by"], ["app_user.id"], name=op.f("fk_vision_session_reviewed_by_app_user")),
        sa.ForeignKeyConstraint(
            ["territory_id"], ["territory.id"], name=op.f("fk_vision_session_territory_id_territory")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vision_session")),
    )
    op.create_index("ix_vision_session_object_captured", "vision_session", ["object_id", "captured_at"], unique=False)
    op.create_index(op.f("ix_vision_session_territory_id"), "vision_session", ["territory_id"], unique=False)
    op.create_table(
        "vision_asset",
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "kind",
            sa.String(length=5),
            nullable=False,
        ),
        sa.Column("original_name", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("bucket", sa.String(length=63), nullable=False),
        sa.Column("s3_key", sa.String(length=512), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
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
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=10),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("uploaded_by", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('photo', 'video')", name=op.f("ck_vision_asset_vision_asset_kind")),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'ready', 'failed')", name=op.f("ck_vision_asset_vision_asset_status")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["vision_session.id"], name=op.f("fk_vision_asset_session_id_vision_session")
        ),
        sa.ForeignKeyConstraint(["uploaded_by"], ["app_user.id"], name=op.f("fk_vision_asset_uploaded_by_app_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vision_asset")),
        sa.UniqueConstraint("session_id", "sha256", name=op.f("uq_vision_asset_session_id")),
    )
    op.create_index("ix_vision_asset_location", "vision_asset", ["location"], unique=False, postgresql_using="gist")
    op.create_index(op.f("ix_vision_asset_session_id"), "vision_asset", ["session_id"], unique=False)
    op.create_table(
        "vision_frame",
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("timestamp_ms", sa.Integer(), nullable=True),
        sa.Column("bucket", sa.String(length=63), nullable=False),
        sa.Column("s3_key", sa.String(length=512), nullable=False),
        sa.Column("preview_key", sa.String(length=512), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sharpness", sa.Float(), nullable=True),
        sa.Column("usable", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["vision_asset.id"], name=op.f("fk_vision_frame_asset_id_vision_asset")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vision_frame")),
        sa.UniqueConstraint("asset_id", "timestamp_ms", name=op.f("uq_vision_frame_asset_id")),
    )
    op.create_table(
        "vision_job",
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "kind",
            sa.String(length=14),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=9),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('extract_frames', 'ocr_region')", name=op.f("ck_vision_job_vision_job_kind")),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')", name=op.f("ck_vision_job_vision_job_status")
        ),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name=op.f("ck_vision_job_vision_job_progress_range")),
        sa.ForeignKeyConstraint(["asset_id"], ["vision_asset.id"], name=op.f("fk_vision_job_asset_id_vision_asset")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vision_job")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_vision_job_idempotency_key")),
    )
    op.create_index("ix_vision_job_asset_id", "vision_job", ["asset_id", "id"], unique=False)
    op.create_table(
        "vision_finding",
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("frame_id", sa.BigInteger(), nullable=True),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "category",
            sa.String(length=15),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=22),
            nullable=False,
        ),
        sa.Column(
            "origin",
            sa.String(length=6),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "review_state",
            sa.String(length=19),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "ocr_status",
            sa.String(length=7),
            nullable=True,
        ),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("ocr_engine", sa.String(length=100), nullable=True),
        sa.Column("confirmed_text", sa.Text(), nullable=True),
        sa.Column("ad_post_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "category IN ('outdoor_ad', 'fence', 'site_gate', 'waste_container', 'wheel_wash', 'other')",
            name=op.f("ck_vision_finding_vision_category"),
        ),
        sa.CheckConstraint("ocr_status IN ('pending', 'done', 'failed')", name=op.f("ck_vision_finding_ocr_status")),
        sa.CheckConstraint("origin IN ('manual', 'model')", name=op.f("ck_vision_finding_vision_finding_origin")),
        sa.CheckConstraint(
            "review_state IN ('pending', 'confirmed', 'rejected', 'needs_more_evidence')",
            name=op.f("ck_vision_finding_vision_review_state"),
        ),
        sa.CheckConstraint(
            "status IN ('observed', 'possible_noncompliance', 'insufficient_evidence', 'not_applicable')",
            name=op.f("ck_vision_finding_vision_finding_status"),
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1", name=op.f("ck_vision_finding_vision_finding_confidence_range")
        ),
        sa.ForeignKeyConstraint(["ad_post_id"], ["ad_post.id"], name=op.f("fk_vision_finding_ad_post_id_ad_post")),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], name=op.f("fk_vision_finding_created_by_app_user")),
        sa.ForeignKeyConstraint(
            ["frame_id"], ["vision_frame.id"], name=op.f("fk_vision_finding_frame_id_vision_frame")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["vision_session.id"], name=op.f("fk_vision_finding_session_id_vision_session")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vision_finding")),
        sa.UniqueConstraint("ad_post_id", name=op.f("uq_vision_finding_ad_post_id")),
    )
    op.create_index("ix_vision_finding_frame_id", "vision_finding", ["frame_id"], unique=False)
    op.create_index("ix_vision_finding_session_id", "vision_finding", ["session_id", "id"], unique=False)
    op.create_table(
        "vision_review",
        sa.Column("finding_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "action",
            sa.String(length=19),
            nullable=False,
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("reviewer_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.CheckConstraint(
            "action IN ('confirm', 'reject', 'needs_more_evidence', 'not_applicable', 'comment')",
            name=op.f("ck_vision_review_vision_review_action"),
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"], ["vision_finding.id"], name=op.f("fk_vision_review_finding_id_vision_finding")
        ),
        sa.ForeignKeyConstraint(["reviewer_id"], ["app_user.id"], name=op.f("fk_vision_review_reviewer_id_app_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vision_review")),
    )
    op.create_index("ix_vision_review_finding_id", "vision_review", ["finding_id", "id"], unique=False)
    op.execute(
        "CREATE TRIGGER vision_review_append_only BEFORE UPDATE OR DELETE ON vision_review "
        "FOR EACH ROW EXECUTE FUNCTION forbid_modification()"
    )
    op.execute(
        "CREATE TRIGGER vision_review_no_truncate BEFORE TRUNCATE ON vision_review "
        "FOR EACH STATEMENT EXECUTE FUNCTION forbid_modification()"
    )

    _replace_origin_check(("manual", "capture", "collector", "citizen", "vision"))


def downgrade() -> None:
    # Fails while publications with origin `vision` exist: they have no equivalent among the old codes.
    _replace_origin_check(("manual", "capture", "collector", "citizen"))

    # Dropping the tables drops the triggers of vision_review with it.
    op.drop_index("ix_vision_review_finding_id", table_name="vision_review")
    op.drop_table("vision_review")
    op.drop_index("ix_vision_finding_session_id", table_name="vision_finding")
    op.drop_index("ix_vision_finding_frame_id", table_name="vision_finding")
    op.drop_table("vision_finding")
    op.drop_index("ix_vision_job_asset_id", table_name="vision_job")
    op.drop_table("vision_job")
    op.drop_table("vision_frame")
    op.drop_index(op.f("ix_vision_asset_session_id"), table_name="vision_asset")
    op.drop_index("ix_vision_asset_location", table_name="vision_asset", postgresql_using="gist")
    op.drop_table("vision_asset")
    op.drop_index(op.f("ix_vision_session_territory_id"), table_name="vision_session")
    op.drop_index("ix_vision_session_object_captured", table_name="vision_session")
    op.drop_table("vision_session")
