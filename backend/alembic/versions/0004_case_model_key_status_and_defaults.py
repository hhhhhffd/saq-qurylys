"""key_status codes of the case risk model and the new setting defaults

SPEC 6.4 replaces the key status codes (`no_permit*`, `permit_checking`, `overdue`, `complaints`,
`readiness_overstated` give way to `no_legal_basis*`, `legal_basis_unknown`, `delayed`, `collective_complaint`,
`readiness_mismatch`, `active_ads`). The column is a VARCHAR with a CHECK constraint, so it is widened and the
constraint recreated. Stored objects keep their old score until the next calculation: their key status is cleared
(the old codes are not valid any more) and `next_check_at` is emptied so that `risk.sweep_due` rescores them.

The case model also changes two defaults (ad window 7 -> 30 days, readiness gap 10 -> 20 points); a stored
value is replaced only when it still equals the old default, i.e. was never customised.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-13 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_construction_object_key_status"
OLD_CODES = (
    "no_permit_with_offer",
    "no_permit",
    "permit_checking",
    "money_offer",
    "stalled",
    "overdue",
    "complaints",
    "readiness_overstated",
    "ok",
)
NEW_CODES = (
    "no_legal_basis_with_offer",
    "no_legal_basis",
    "money_offer",
    "legal_basis_unknown",
    "stalled",
    "delayed",
    "collective_complaint",
    "readiness_mismatch",
    "active_ads",
    "ok",
)
# key -> (old default, new default)
CHANGED_DEFAULTS = {"ad_window_days": (7, 30), "readiness_gap_pp": (10, 20)}

_REPLACE_DEFAULT = sa.text(
    "UPDATE app_setting SET value = to_jsonb(CAST(:new AS integer)) "
    "WHERE key = :key AND value = to_jsonb(CAST(:old AS integer))"
)


def _check(codes: Sequence[str]) -> str:
    return "key_status IN (" + ", ".join(f"'{code}'" for code in codes) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "construction_object", type_="check")
    op.execute("UPDATE construction_object SET key_status = NULL, next_check_at = NULL")
    op.alter_column("construction_object", "key_status", existing_type=sa.String(length=20), type_=sa.String(length=25))
    op.create_check_constraint(op.f(CONSTRAINT), "construction_object", _check(NEW_CODES))
    for key, (old, new) in CHANGED_DEFAULTS.items():
        op.execute(_REPLACE_DEFAULT.bindparams(key=key, old=old, new=new))


def downgrade() -> None:
    for key, (old, new) in CHANGED_DEFAULTS.items():
        op.execute(_REPLACE_DEFAULT.bindparams(key=key, old=new, new=old))
    op.drop_constraint(op.f(CONSTRAINT), "construction_object", type_="check")
    op.execute("UPDATE construction_object SET key_status = NULL, next_check_at = NULL")
    op.alter_column("construction_object", "key_status", existing_type=sa.String(length=25), type_=sa.String(length=20))
    op.create_check_constraint(op.f(CONSTRAINT), "construction_object", _check(OLD_CODES))
