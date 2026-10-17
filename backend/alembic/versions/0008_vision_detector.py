"""SAQ VISION: object detector runs, raw detections, `debris` category

- vision_run: one pass of the detector over the usable frames of an asset (or of the whole session).
- vision_detection: the raw boxes; findings made by a run point to their run and to the representative box.
- The category CHECK of vision_finding gains `debris`.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-16 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_CATEGORIES = "'outdoor_ad', 'fence', 'site_gate', 'waste_container', 'wheel_wash', 'other'"
NEW_CATEGORIES = "'outdoor_ad', 'fence', 'site_gate', 'waste_container', 'wheel_wash', 'debris', 'other'"


def _replace_category_check(values: str) -> None:
    op.drop_constraint(op.f("ck_vision_finding_vision_category"), "vision_finding", type_="check")
    op.create_check_constraint(op.f("ck_vision_finding_vision_category"), "vision_finding", f"category IN ({values})")


def upgrade() -> None:
    _replace_category_check(NEW_CATEGORIES)
    op.create_table(
        "vision_run",
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=9), server_default="queued", nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("frames_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("frames_done", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')", name=op.f("ck_vision_run_vision_run_status")
        ),
        sa.CheckConstraint(
            "frames_done BETWEEN 0 AND frames_total", name=op.f("ck_vision_run_vision_run_frames_range")
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["vision_asset.id"], name=op.f("fk_vision_run_asset_id_vision_asset")),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], name=op.f("fk_vision_run_created_by_app_user")),
        sa.ForeignKeyConstraint(
            ["session_id"], ["vision_session.id"], name=op.f("fk_vision_run_session_id_vision_session")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vision_run")),
    )
    op.create_index("ix_vision_run_session_id", "vision_run", ["session_id", "id"], unique=False)
    op.create_table(
        "vision_detection",
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("frame_id", sa.BigInteger(), nullable=False),
        sa.Column("category", sa.String(length=15), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("group_key", sa.Integer(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            f"category IN ({NEW_CATEGORIES})", name=op.f("ck_vision_detection_vision_detection_category")
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1", name=op.f("ck_vision_detection_vision_detection_confidence_range")
        ),
        sa.ForeignKeyConstraint(
            ["frame_id"], ["vision_frame.id"], name=op.f("fk_vision_detection_frame_id_vision_frame")
        ),
        sa.ForeignKeyConstraint(["run_id"], ["vision_run.id"], name=op.f("fk_vision_detection_run_id_vision_run")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vision_detection")),
    )
    op.create_index("ix_vision_detection_run_id", "vision_detection", ["run_id", "group_key"], unique=False)
    op.create_index("ix_vision_detection_frame_id", "vision_detection", ["frame_id"], unique=False)
    op.add_column("vision_finding", sa.Column("run_id", sa.BigInteger(), nullable=True))
    op.add_column("vision_finding", sa.Column("detection_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_vision_finding_run_id_vision_run"), "vision_finding", "vision_run", ["run_id"], ["id"]
    )
    op.create_foreign_key(
        op.f("fk_vision_finding_detection_id_vision_detection"),
        "vision_finding",
        "vision_detection",
        ["detection_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_vision_finding_detection_id_vision_detection"), "vision_finding", type_="foreignkey")
    op.drop_constraint(op.f("fk_vision_finding_run_id_vision_run"), "vision_finding", type_="foreignkey")
    op.drop_column("vision_finding", "detection_id")
    op.drop_column("vision_finding", "run_id")
    op.drop_table("vision_detection")
    op.drop_table("vision_run")
    # vision_review is append-only, so findings cannot be deleted; the new category is folded into `other`.
    op.execute("UPDATE vision_finding SET category = 'other' WHERE category = 'debris'")
    _replace_category_check(OLD_CATEGORIES)
