"""automatic collection, OCR, citizen reports, publication versions, replayed score history (SPEC 10)

- ad_post.origin: how a publication entered the system. No collector existed before this revision, so an existing
  row with a capture status was added by URL and the rest were entered by hand.
- ad_post.ocr_status: state of text recognition on the post's photos (NULL: nothing to read).
- source_account.last_error / last_error_at: the last failed collection run of the account.
- dismissed_source_suggestion: accounts staff declined to watch, so that they are not suggested again.
- ad_post_version: later texts of a publication that differ from the saved original; append-only like evidence.
- score trigger `replay`: risk history reconstructed afterwards from dated facts.
- notification kinds `citizen_report` and `collector_failed`; complaint source `telegram`; score trigger
  `replay`. The columns are VARCHAR with a CHECK constraint and already wide enough, so only the constraints are
  recreated.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-13 23:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_NOTIFICATION_KINDS = (
    "red_zone",
    "signal_returned",
    "signal_sent",
    "signal_due_soon",
    "signal_overdue",
    "signal_responded",
    "capture_failed",
)
NEW_NOTIFICATION_KINDS = (*OLD_NOTIFICATION_KINDS, "citizen_report", "collector_failed")
OLD_COMPLAINT_SOURCES = ("eotinish", "manual", "other")
NEW_COMPLAINT_SOURCES = ("eotinish", "manual", "telegram", "other")
OLD_SCORE_TRIGGERS = ("event", "schedule", "manual")
NEW_SCORE_TRIGGERS = (*OLD_SCORE_TRIGGERS, "replay")
PLATFORMS = ("instagram", "tiktok", "telegram", "website", "aggregator", "outdoor", "other")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def _replace_check(table: str, constraint: str, column: str, values: Sequence[str]) -> None:
    op.drop_constraint(op.f(constraint), table, type_="check")
    op.create_check_constraint(op.f(constraint), table, _in(column, values))


def upgrade() -> None:
    op.add_column(
        "ad_post",
        sa.Column("origin", sa.String(length=9), server_default="manual", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_ad_post_ad_origin"), "ad_post", _in("origin", ("manual", "capture", "collector", "citizen"))
    )
    op.execute("UPDATE ad_post SET origin = 'capture' WHERE capture_status IS NOT NULL")
    op.add_column("ad_post", sa.Column("ocr_status", sa.String(length=7), nullable=True))
    op.create_check_constraint(
        op.f("ck_ad_post_ocr_status"), "ad_post", _in("ocr_status", ("pending", "done", "failed"))
    )

    op.add_column("source_account", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("source_account", sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "dismissed_source_suggestion",
        sa.Column("platform", sa.String(length=10), nullable=False),
        sa.Column("handle", sa.String(length=255), nullable=False),
        sa.Column("dismissed_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.CheckConstraint(_in("platform", PLATFORMS), name=op.f("ck_dismissed_source_suggestion_platform")),
        sa.ForeignKeyConstraint(
            ["dismissed_by"], ["app_user.id"], name=op.f("fk_dismissed_source_suggestion_dismissed_by_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dismissed_source_suggestion")),
        sa.UniqueConstraint("platform", "handle", name=op.f("uq_dismissed_source_suggestion_platform")),
    )

    op.create_table(
        "ad_post_version",
        sa.Column("ad_post_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=9), nullable=False),
        sa.Column("evidence_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.CheckConstraint(
            _in("source", ("capture", "collector", "recheck")), name=op.f("ck_ad_post_version_ad_version_source")
        ),
        sa.ForeignKeyConstraint(["ad_post_id"], ["ad_post.id"], name=op.f("fk_ad_post_version_ad_post_id_ad_post")),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], name=op.f("fk_ad_post_version_evidence_id_evidence")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ad_post_version")),
    )
    op.create_index("ix_ad_post_version_ad_post_observed", "ad_post_version", ["ad_post_id", "observed_at"])
    # forbid_modification() comes from 0001.
    op.execute(
        "CREATE TRIGGER ad_post_version_append_only BEFORE UPDATE OR DELETE ON ad_post_version "
        "FOR EACH ROW EXECUTE FUNCTION forbid_modification()"
    )
    op.execute(
        "CREATE TRIGGER ad_post_version_no_truncate BEFORE TRUNCATE ON ad_post_version "
        "FOR EACH STATEMENT EXECUTE FUNCTION forbid_modification()"
    )

    _replace_check("notification", "ck_notification_notification_kind", "kind", NEW_NOTIFICATION_KINDS)
    _replace_check("complaint", "ck_complaint_complaint_source", "source", NEW_COMPLAINT_SOURCES)
    _replace_check("risk_score", "ck_risk_score_score_trigger", "trigger", NEW_SCORE_TRIGGERS)


def downgrade() -> None:
    # Fails while rows use the new codes; they have no equivalent among the old ones.
    _replace_check("risk_score", "ck_risk_score_score_trigger", "trigger", OLD_SCORE_TRIGGERS)
    _replace_check("complaint", "ck_complaint_complaint_source", "source", OLD_COMPLAINT_SOURCES)
    _replace_check("notification", "ck_notification_notification_kind", "kind", OLD_NOTIFICATION_KINDS)

    # Dropping the table drops its triggers; the append-only rows go with it.
    op.drop_index("ix_ad_post_version_ad_post_observed", table_name="ad_post_version")
    op.drop_table("ad_post_version")
    op.drop_table("dismissed_source_suggestion")

    op.drop_column("source_account", "last_error_at")
    op.drop_column("source_account", "last_error")

    op.drop_constraint(op.f("ck_ad_post_ocr_status"), "ad_post", type_="check")
    op.drop_column("ad_post", "ocr_status")
    op.drop_constraint(op.f("ck_ad_post_ad_origin"), "ad_post", type_="check")
    op.drop_column("ad_post", "origin")
