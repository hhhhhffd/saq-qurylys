"""Polite HTTP access shared by the collectors: a pause between requests and no hidden redirects."""

import time
from collections.abc import Callable, Mapping

import httpx

from app.collectors.base import CollectorError

REQUEST_TIMEOUT_S = 20


class Fetcher:
    """GET requests through an injectable `httpx.Client`, `delay_s` apart. Redirects are not followed: the
    callers decide what a redirect means (for Telegram it is an error)."""

    def __init__(self, client: httpx.Client, delay_s: float, sleep: Callable[[float], None] = time.sleep) -> None:
        self._client = client
        self._delay_s = delay_s
        self._sleep = sleep
        self._requested = False

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | str | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        if self._requested:
            self._sleep(self._delay_s)
        self._requested = True
        try:
            return self._client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise CollectorError("Источник не ответил вовремя") from exc
        except httpx.HTTPError as exc:
            # The exception text can carry the request URL, so it is not copied into the message.
            raise CollectorError("Не удалось получить данные источника: ошибка сети") from exc
