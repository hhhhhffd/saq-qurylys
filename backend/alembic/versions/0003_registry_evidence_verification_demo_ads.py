"""registry evidence kind, complaint verification, demo marker on publications

- evidence kind `registry_response`: raw JSON answers of the housing portal registry are stored as evidence of a
  document check. The kind is a VARCHAR(14) with a CHECK constraint, so the column is widened and the constraint
  recreated.
- complaint.is_verified / verified_by / verified_at: a collective complaint counts for R4 only once verified.
- ad_post.is_demo: demo publications are marked like demo objects.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_evidence_evidence_kind"
OLD_KINDS = ("screenshot_png", "archive_mhtml", "photo", "document_scan", "pdf")
NEW_KINDS = (*OLD_KINDS, "registry_response")


def _kind_check(kinds: Sequence[str]) -> str:
    return "kind IN (" + ", ".join(f"'{kind}'" for kind in kinds) + ")"


def upgrade() -> None:
    # Changing the column type of an append-only table does not fire its row triggers (no row is rewritten
    # when a VARCHAR only gets longer).
    op.drop_constraint(op.f(CONSTRAINT), "evidence", type_="check")
    op.alter_column("evidence", "kind", existing_type=sa.String(length=14), type_=sa.String(length=17))
    op.create_check_constraint(op.f(CONSTRAINT), "evidence", _kind_check(NEW_KINDS))

    op.add_column("complaint", sa.Column("is_verified", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("complaint", sa.Column("verified_by", sa.BigInteger(), nullable=True))
    op.add_column("complaint", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(op.f("fk_complaint_verified_by_app_user"), "complaint", "app_user", ["verified_by"], ["id"])

    op.add_column("ad_post", sa.Column("is_demo", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("ad_post", "is_demo")

    op.drop_constraint(op.f("fk_complaint_verified_by_app_user"), "complaint", type_="foreignkey")
    op.drop_column("complaint", "verified_at")
    op.drop_column("complaint", "verified_by")
    op.drop_column("complaint", "is_verified")

    # Fails while registry_response evidence exists: evidence is append-only and cannot be removed.
    op.drop_constraint(op.f(CONSTRAINT), "evidence", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "evidence", _kind_check(OLD_KINDS))
    op.alter_column("evidence", "kind", existing_type=sa.String(length=17), type_=sa.String(length=14))
