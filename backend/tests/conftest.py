"""Test fixtures. Tests run against a real PostGIS database and MinIO from `docker compose up -d db redis minio`.

A separate database is created for the session and migrated with Alembic. Each test runs inside a
transaction that is rolled back, so tests are isolated without truncating tables.
"""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# Environment must be set before `app` is imported: settings are read once and cached.
os.environ.setdefault("TEST_DATABASE_URL", "postgresql+psycopg://saq:saq_dev_password@localhost:5433/saq_test")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ.setdefault("S3_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "saq-minio-dev")
os.environ.setdefault("S3_SECRET_KEY", "saq-minio-dev-secret")
# Parallel test runs (separate worktrees) need their own database and bucket: the bucket is emptied at the end.
os.environ["S3_BUCKET_EVIDENCE"] = os.environ.get("TEST_S3_BUCKET", "evidence-test")
os.environ["VISION_ENABLED"] = "true"
os.environ["ASSISTANT_ENABLED"] = "true"
os.environ["S3_BUCKET_VISION"] = os.environ.get("TEST_S3_BUCKET_VISION", "vision-test")
os.environ["EVIDENCE_LOCK_MODE"] = "GOVERNANCE"
os.environ["EVIDENCE_RETENTION_DAYS"] = "1"
os.environ["TSA_URL"] = ""
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-0123456789"
os.environ["EVENTS_ENABLED"] = "false"
os.environ["LLM_ENABLED"] = "false"
# The developer's .env may switch real collectors on; tests register their own and never reach the network.
os.environ["HOMEPORTAL_SYNC_ENABLED"] = "false"
os.environ["COLLECT_TELEGRAM_ENABLED"] = "false"
os.environ["COLLECT_OLX_ENABLED"] = "false"
os.environ["COLLECT_KRISHA_ENABLED"] = "false"
os.environ["INSTAGRAM_GRAPH_TOKEN"] = ""
os.environ["TELEGRAM_API_ID"] = ""
os.environ["TELEGRAM_API_HASH"] = ""
os.environ["INITIAL_ADMIN_USERNAME"] = "admin"
os.environ["INITIAL_ADMIN_PASSWORD"] = "admin-test-password"

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from minio.deleteobjects import DeleteObject
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from redis import Redis
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app import security, seed, storage
from app.config import get_settings
from app.db import get_engine, get_session
from app.main import app
from app.models import AppUser, ConstructionObject, District, Territory
from app.models.enums import Role, TerritoryLevel
from app.modules.auth import throttle
from app.security import create_access_token, hash_password
from tests.support_collect import TEST_REDIS_URL

BACKEND_DIR = Path(__file__).resolve().parent.parent
PASSWORD = "Passw0rd-for-tests"


@pytest.fixture(scope="session", autouse=True)
def fast_password_hashing() -> None:
    """Argon2 with minimal cost: tests create many users."""
    security._password_hash = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=1024, parallelism=1),))


@pytest.fixture(autouse=True)
def login_counters(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Failed-login counters live in the test Redis database and do not carry over between tests."""
    monkeypatch.setattr(get_settings(), "redis_url", TEST_REDIS_URL)
    yield
    with Redis.from_url(TEST_REDIS_URL) as client:
        keys = list(client.scan_iter(f"{throttle.KEY_PREFIX}*"))
        if keys:
            client.delete(*keys)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = make_url(os.environ["TEST_DATABASE_URL"])
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    yield get_engine()
    get_engine().dispose()
    with admin_engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
    admin_engine.dispose()


def _empty_bucket(name: str) -> None:
    # Evidence is locked until retention expires; governance mode can be bypassed to keep MinIO tidy.
    client = storage.get_client()
    versions = [
        DeleteObject(item.object_name, item.version_id)
        for item in client.list_objects(name, recursive=True, include_version=True)
        if item.object_name
    ]
    for error in client.remove_objects(name, versions, bypass_governance_mode=True):
        raise RuntimeError(f"could not clean test bucket: {error}")


@pytest.fixture(scope="session")
def bucket() -> Iterator[str]:
    storage.ensure_bucket()
    yield get_settings().s3_bucket_evidence
    _empty_bucket(get_settings().s3_bucket_evidence)


@pytest.fixture(scope="session")
def vision_bucket() -> Iterator[str]:
    storage.ensure_vision_bucket()
    yield get_settings().s3_bucket_vision
    _empty_bucket(get_settings().s3_bucket_vision)


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield session
    session.close()
    outer.rollback()
    connection.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@dataclass
class World:
    region: Territory
    ust: Territory
    semey: Territory
    district: District
    users: dict[str, AppUser]


def _user(db: Session, username: str, role: Role, territory: Territory | None) -> AppUser:
    user = AppUser(
        username=username,
        full_name=username,
        password_hash=hash_password(PASSWORD),
        role=role,
        territory_id=territory.id if territory else None,
    )
    db.add(user)
    return user


@pytest.fixture
def world(db: Session) -> World:
    """Seeded reference data (region VKO, Ust-Kamenogorsk) plus a second city and one user per role."""
    seed.seed_reference(db)
    region = db.scalars(select(Territory).where(Territory.code == "vko")).one()
    ust = db.scalars(select(Territory).where(Territory.code == "ust-kamenogorsk")).one()
    semey = Territory(
        parent_id=region.id, level=TerritoryLevel.city, code="semey", name="Семей", timezone="Asia/Almaty"
    )
    db.add(semey)
    db.flush()
    district = District(territory_id=ust.id, name="Центральный")
    db.add(district)
    users = {
        "admin": _user(db, "t_admin", Role.admin, None),
        "admin_semey": _user(db, "t_admin_semey", Role.admin, semey),
        "mio_ust": _user(db, "t_mio_ust", Role.mio_officer, ust),
        "mio_semey": _user(db, "t_mio_semey", Role.mio_officer, semey),
        "mio_region": _user(db, "t_mio_region", Role.mio_officer, region),
        "gask": _user(db, "t_gask", Role.gask, ust),
        "law": _user(db, "t_law", Role.law_enforcement, region),
    }
    db.flush()
    return World(region=region, ust=ust, semey=semey, district=district, users=users)


def auth(user: AppUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def make_object(db: Session, territory: Territory, name: str = "ЖК Тест", **fields: object) -> ConstructionObject:
    obj = ConstructionObject(territory_id=territory.id, name=name, **fields)
    db.add(obj)
    db.flush()
    db.refresh(obj)
    return obj


@pytest.fixture
def sent_tasks(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[object, ...]]]:
    """Enable the event hook and record the Celery tasks it would send instead of using the broker."""
    sent: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(get_settings(), "events_enabled", True)
    monkeypatch.setattr(
        "app.events.celery_app.send_task",
        lambda name, args=(), **kwargs: sent.append((name, tuple(args))),
    )
    return sent


# Minimal valid files for upload tests.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF_BYTES = b"%PDF-1.4\n" + b"0" * 64
