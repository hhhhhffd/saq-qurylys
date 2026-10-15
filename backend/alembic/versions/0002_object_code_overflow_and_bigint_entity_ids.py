"""object code beyond 9999 and bigint entity ids

lpad(n, 4, '0') truncates numbers longer than four digits, so code 10000 would become SQ-OBJ-1000.
The default now calls a function that pads to at least four digits without truncating.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION next_object_code() RETURNS text AS $$
            SELECT 'SQ-OBJ-' || lpad(n::text, greatest(4, length(n::text)), '0')
            FROM (SELECT nextval('object_code_seq') AS n) AS next_value
        $$ LANGUAGE sql
        """
    )
    op.execute("ALTER TABLE construction_object ALTER COLUMN code SET DEFAULT next_object_code()")
    # ALTER TYPE rewrites the table without firing the append-only row triggers.
    op.alter_column("audit_log", "entity_id", existing_type=sa.Integer(), type_=sa.BigInteger())
    op.alter_column("notification", "entity_id", existing_type=sa.Integer(), type_=sa.BigInteger())


def downgrade() -> None:
    op.alter_column("notification", "entity_id", existing_type=sa.BigInteger(), type_=sa.Integer())
    op.alter_column("audit_log", "entity_id", existing_type=sa.BigInteger(), type_=sa.Integer())
    op.execute(
        "ALTER TABLE construction_object ALTER COLUMN code SET DEFAULT "
        "'SQ-OBJ-' || lpad(nextval('object_code_seq')::text, 4, '0')"
    )
    op.execute("DROP FUNCTION next_object_code()")
