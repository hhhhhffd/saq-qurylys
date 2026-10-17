"""Assignments: a manager asks an employee to check an object by a date

- assignment: object, author, assignee, task text, calendar due date, status open|done|cancelled, result.
- The kind CHECK of notification gains `assignment_new`.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-16 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
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
    "citizen_report",
    "collector_failed",
)
NEW_NOTIFICATION_KINDS = (*OLD_NOTIFICATION_KINDS, "assignment_new")


def _replace_notification_kinds(values: Sequence[str]) -> None:
    op.drop_constraint(op.f("ck_notification_notification_kind"), "notification", type_="check")
    op.create_check_constraint(
        op.f("ck_notification_notification_kind"),
        "notification",
        "kind IN (" + ", ".join(f"'{value}'" for value in values) + ")",
    )


def upgrade() -> None:
    _replace_notification_kinds(NEW_NOTIFICATION_KINDS)
    op.create_table(
        "assignment",
        sa.Column("object_id", sa.BigInteger(), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column("assignee_id", sa.BigInteger(), nullable=False),
        sa.Column("task", sa.String(length=2000), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=9), server_default="open", nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.CheckConstraint("status IN ('open', 'done', 'cancelled')", name=op.f("ck_assignment_assignment_status")),
        sa.ForeignKeyConstraint(
            ["object_id"], ["construction_object.id"], name=op.f("fk_assignment_object_id_construction_object")
        ),
        sa.ForeignKeyConstraint(["author_id"], ["app_user.id"], name=op.f("fk_assignment_author_id_app_user")),
        sa.ForeignKeyConstraint(["assignee_id"], ["app_user.id"], name=op.f("fk_assignment_assignee_id_app_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment")),
    )
    op.create_index("ix_assignment_assignee_status", "assignment", ["assignee_id", "status"])
    op.create_index("ix_assignment_object_id", "assignment", ["object_id"])


def downgrade() -> None:
    op.drop_index("ix_assignment_object_id", table_name="assignment")
    op.drop_index("ix_assignment_assignee_status", table_name="assignment")
    op.drop_table("assignment")
    # Fails while notifications of the new kind exist; they have no equivalent among the old ones.
    _replace_notification_kinds(OLD_NOTIFICATION_KINDS)
