"""Support for the tests that run the collection: its locks live in Redis."""

from collections.abc import Iterator

import pytest
from redis import Redis

from app.config import get_settings

# The development Redis (database 0) also serves the running stack: the tests use another database, emptied after.
TEST_REDIS_URL = "redis://localhost:6379/15"


def lock_db() -> Redis:
    """The Redis database that holds the locks during the tests."""
    return Redis.from_url(TEST_REDIS_URL)


@pytest.fixture
def collect_locks(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(get_settings(), "redis_url", TEST_REDIS_URL)
    with lock_db() as client:
        client.flushdb()
        yield
        client.flushdb()
