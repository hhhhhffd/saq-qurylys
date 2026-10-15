"""Mutual exclusion of collection runs of one account (SPEC 10.1).

The scheduled run and the «Собрать сейчас» button run in different workers, and two runs over the same account would
store the same posts twice. The lock is a Redis key with an expiry, so a worker that died cannot hold it forever.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

from app.config import get_settings

logger = logging.getLogger(__name__)

# Longer than any run: pages, pauses and photos of one account take minutes.
LOCK_TTL_S = 30 * 60
KEY_PREFIX = "collect:lock:"
# Deletes the key only while it still holds our token: after the expiry another run may own it.
_RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0"


def _key(account_id: int) -> str:
    return f"{KEY_PREFIX}{account_id}"


def is_held(account_id: int) -> bool:
    with Redis.from_url(get_settings().redis_url) as client:
        return bool(client.exists(_key(account_id)))


@contextmanager
def hold(account_id: int) -> Iterator[bool]:
    """Take the account's lock for the block; yields False, without waiting, when another run holds it."""
    token = uuid4().hex
    with Redis.from_url(get_settings().redis_url) as client:
        acquired = bool(client.set(_key(account_id), token, nx=True, ex=LOCK_TTL_S))
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    client.eval(_RELEASE, 1, _key(account_id), token)
                except RedisError:
                    # The run is over and saved; the key expires by itself.
                    logger.exception("The collection lock of source account %s was not released", account_id)
