"""Client of the public API behind homeportal.kz (АО «КЖК»).

The API is undocumented: it is what the site itself calls. Regular use needs the agreement of АО «КЖК»
(docs/OPEN_QUESTIONS.md, item 11), so the client is deliberately polite: one request at a time, a pause between
requests and a User-Agent that says who is asking.
"""

import time
from collections.abc import Callable
from types import TracebackType
from typing import Any, Self

import httpx

from app.modules.registry_sync.records import API_BASE, RegistryFormatError, RegistryRecord, from_detail

USER_AGENT = "SAQ-QURYLYS/1.0 (pilot; contact: admin)"
REQUEST_PAUSE_S = 1.5
TIMEOUT_S = 30.0
_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}


class HomeportalClient:
    def __init__(
        self,
        http: httpx.Client | None = None,
        *,
        pause_s: float = REQUEST_PAUSE_S,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._owns_http = http is None
        self._http = http or httpx.Client(timeout=TIMEOUT_S)
        self._pause_s = pause_s
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.close()

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if self._last_request_at is not None:
            wait = self._pause_s - (self._clock() - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        try:
            response = self._http.request(method, url, headers=_HEADERS, **kwargs)
        finally:
            self._last_request_at = self._clock()
        response.raise_for_status()
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise RegistryFormatError("ответ реестра не является JSON") from exc

    def list_registry_ids(self, region_id: int) -> list[int]:
        """Ids of the registry records of a region. The list answer carries little; details are fetched per id."""
        body = self._json(self._request("POST", f"{API_BASE}/getobjects", json={"region_id": region_id}))
        try:
            items = body["data"]["objects"]["data"]
            ids = [int(item["id"]) for item in items]
        except (KeyError, TypeError, ValueError) as exc:
            raise RegistryFormatError("в ответе реестра нет списка объектов") from exc
        return list(dict.fromkeys(ids))

    def fetch_record(self, registry_id: int) -> tuple[RegistryRecord, bytes]:
        """The parsed record and the answer exactly as received (kept as evidence)."""
        response = self._request("GET", f"{API_BASE}/objects-detail/{registry_id}")
        return from_detail(registry_id, self._json(response)), response.content
