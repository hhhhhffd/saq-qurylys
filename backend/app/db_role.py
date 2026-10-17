"""The database role the application runs as, separate from the owner that runs the migrations.

The owner can drop or disable the append-only triggers, so the application must not connect as the owner. The
application role gets read and write access to the tables, but no UPDATE, DELETE or TRUNCATE on the append-only ones
(evidence, audit trail, risk factor history, ...): their immutability then holds even if the triggers were bypassed,
and the role cannot touch the triggers, which needs ownership. Applied after every migration, so new tables are
covered.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection, make_url

# Every table protected by the append-only trigger of migration 0001, whichever migration created it.
_APPEND_ONLY_TABLES = text(
    """
    SELECT DISTINCT c.relname
    FROM pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_proc p ON p.oid = t.tgfoid
    WHERE p.proname = 'forbid_modification' AND n.nspname = 'public' AND NOT t.tgisinternal
    ORDER BY c.relname
    """
)


def app_role_credentials(app_url: str, migration_url: str) -> tuple[str, str] | None:
    """(role, password) of the application when it connects as a role other than the migration's; None otherwise."""
    app, owner = make_url(app_url), make_url(migration_url)
    if not app.username or app.username == owner.username:
        return None
    if not app.password:
        raise ValueError("DATABASE_URL of a separate application role must contain its password")
    return app.username, str(app.password)


def ensure_app_role(connection: Connection, role: str, password: str) -> None:
    """Create the login role (or reset its password to the configured one) and grant it the application rights."""
    exists = connection.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role})
    # DDL takes no bind parameters; format() quotes the name and the password on the server.
    statement = connection.scalar(
        text("SELECT format(CAST(:template AS text), CAST(:role AS text), CAST(:password AS text))"),
        {
            "template": "ALTER ROLE %I LOGIN PASSWORD %L" if exists else "CREATE ROLE %I LOGIN PASSWORD %L",
            "role": role,
            "password": password,
        },
    )
    connection.execute(text(statement))
    grant_app_rights(connection, role)


def grant_app_rights(connection: Connection, role: str) -> None:
    quoted = connection.scalar(text("SELECT quote_ident(:role)"), {"role": role})
    database = connection.scalar(text("SELECT quote_ident(current_database())"))
    connection.execute(text(f"GRANT CONNECT, TEMPORARY ON DATABASE {database} TO {quoted}"))
    connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {quoted}"))
    connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {quoted}"))
    connection.execute(text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {quoted}"))
    for table in connection.scalars(_APPEND_ONLY_TABLES):
        connection.execute(text(f'REVOKE UPDATE, DELETE, TRUNCATE ON public."{table}" FROM {quoted}'))
