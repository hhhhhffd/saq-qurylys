"""The application role: full access to ordinary tables, append-only tables cannot be changed even bypassing the
triggers, and the triggers themselves are out of its reach."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.db_role import app_role_credentials, ensure_app_role
from tests.conftest import World, make_object

ROLE = "saq_app_test_role"
APPEND_ONLY = ("evidence", "audit_log", "risk_factor_change", "ad_post_version", "vision_review")


@pytest.fixture
def as_app_role(db: Session, world: World) -> Session:
    # CREATE ROLE is transactional: the test's rollback removes the role again.
    ensure_app_role(db.connection(), ROLE, "app-role-test-password")
    make_object(db, world.ust)
    db.execute(text(f"SET LOCAL ROLE {ROLE}"))
    return db


def _denied(db: Session, sql: str) -> str:
    with pytest.raises(ProgrammingError) as error, db.begin_nested():
        db.execute(text(sql))
    return str(error.value.orig)


def test_app_role_reads_and_writes_ordinary_tables(as_app_role: Session) -> None:
    db = as_app_role
    assert db.scalar(text("SELECT count(*) FROM construction_object")) >= 1
    db.execute(text("UPDATE construction_object SET name = name || ' (тест)'"))
    db.execute(text("INSERT INTO audit_log (action, entity_type) VALUES ('test.insert', 'test')"))
    assert db.scalar(text("SELECT nextval('object_code_seq')")) is not None


@pytest.mark.parametrize("table", APPEND_ONLY)
def test_app_role_cannot_change_append_only_tables(as_app_role: Session, table: str) -> None:
    # The table names are the constants above, not input.
    statements = (f"UPDATE {table} SET id = id", f"DELETE FROM {table}", f"TRUNCATE {table}")  # noqa: S608
    for statement in statements:
        assert "permission denied" in _denied(as_app_role, statement)


def test_app_role_cannot_disable_triggers(as_app_role: Session) -> None:
    assert "must be owner" in _denied(as_app_role, "ALTER TABLE evidence DISABLE TRIGGER evidence_append_only")


def test_role_credentials_come_from_the_urls() -> None:
    owner = "postgresql+psycopg://saq:owner-pw@db:5432/saq"
    assert app_role_credentials(owner, owner) is None
    assert app_role_credentials("postgresql+psycopg://saq_app:app-pw@db:5432/saq", owner) == ("saq_app", "app-pw")
    with pytest.raises(ValueError, match="password"):
        app_role_credentials("postgresql+psycopg://saq_app@db:5432/saq", owner)
