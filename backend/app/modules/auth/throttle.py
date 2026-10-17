"""Protection of the login against password guessing.

Failed logins are counted in Redis per username and per client IP over a fixed window. While either counter is at its
limit, the login is refused without checking the password. The username counter lets an attacker lock a known
account out for one window; that is the usual price of stopping guessing of its password.
"""

import hashlib
import hmac

from redis import Redis

from app.config import get_settings

KEY_PREFIX = "auth:login:"


def _keys(username: str, ip: str | None) -> list[str]:
    # HMAC: Redis holds no usernames or addresses in clear, only counters.
    secret = get_settings().jwt_secret.encode()
    keys = [KEY_PREFIX + "user:" + hmac.new(secret, username.encode(), hashlib.sha256).hexdigest()]
    if ip:
        keys.append(KEY_PREFIX + "ip:" + hmac.new(secret, ip.encode(), hashlib.sha256).hexdigest())
    return keys


def blocked_for(username: str, ip: str | None) -> int:
    """Seconds until the next login attempt is accepted; 0 when it is accepted now."""
    settings = get_settings()
    keys = _keys(username, ip)
    limits = [settings.login_max_failures_per_user, settings.login_max_failures_per_ip]
    with Redis.from_url(settings.redis_url) as client:
        pipeline = client.pipeline()
        for key in keys:
            pipeline.get(key)
            pipeline.ttl(key)
        values = pipeline.execute()
    wait = 0
    for index in range(len(keys)):
        count, ttl = values[2 * index], values[2 * index + 1]
        if count is not None and int(count) >= limits[index]:
            wait = max(wait, ttl if ttl > 0 else 1)
    return wait


def record_failure(username: str, ip: str | None) -> None:
    window_s = get_settings().login_lockout_minutes * 60
    with Redis.from_url(get_settings().redis_url) as client:
        pipeline = client.pipeline()
        for key in _keys(username, ip):
            pipeline.incr(key)
            pipeline.expire(key, window_s, nx=True)
        pipeline.execute()


def record_success(username: str) -> None:
    """A correct password clears the failures of the account (not of the address: it may be guessing others)."""
    with Redis.from_url(get_settings().redis_url) as client:
        client.delete(_keys(username, None)[0])
