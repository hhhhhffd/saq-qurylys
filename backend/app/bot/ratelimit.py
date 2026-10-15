import hashlib
import hmac

from redis import Redis

WINDOW_SECONDS = 3600


class RateLimiter:
    """Reports and complaints of one citizen per hour. The counter is keyed by an HMAC of the Telegram id, so no
    identifier of the citizen is stored; it disappears an hour after the first message of the window."""

    def __init__(self, client: Redis, secret: str, limit: int, prefix: str = "bot:rate:") -> None:
        self._client = client
        self._secret = secret.encode()
        self._limit = limit
        self._prefix = prefix

    def key(self, user_id: int) -> str:
        return self._prefix + hmac.new(self._secret, str(user_id).encode(), hashlib.sha256).hexdigest()

    def allow(self, user_id: int) -> bool:
        """Count one more message of the citizen; False when the hourly limit is exceeded."""
        key = self.key(user_id)
        pipeline = self._client.pipeline()
        pipeline.incr(key)
        pipeline.expire(key, WINDOW_SECONDS, nx=True)
        count = pipeline.execute()[0]
        return int(count) <= self._limit
