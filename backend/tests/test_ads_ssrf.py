"""The server fetches URLs that people enter: capture (Chromium) and re-check (httpx) must never reach internal
addresses, also through redirects, scripts of the page and malformed addresses."""

import contextlib
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Evidence, Notification
from app.models.enums import AdStatus, CaptureStatus
from app.modules.ads import capture, recheck
from app.modules.ads import urls as ads_urls
from app.modules.ads.urls import UnsafeUrlError, ensure_public_url, is_http_url
from tests.conftest import World, auth
from tests.support_ads import add_ad

Respond = Callable[[str, "Server"], tuple[int, dict[str, str], bytes]]


class Server:
    """A local HTTP server; `hits` lists every path it was asked for (the sockets' handshakes included)."""

    def __init__(self, respond: Respond) -> None:
        self.hits: list[str] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                server.hits.append(self.path)
                status, headers, body = respond(self.path, server)
                self.send_response(status)
                for name, value in {"Content-Length": str(len(body)), **headers}.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return None

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def html(body: str) -> tuple[int, dict[str, str], bytes]:
    return 200, {"Content-Type": "text/html; charset=utf-8"}, body.encode()


def redirect(location: str) -> tuple[int, dict[str, str], bytes]:
    return 302, {"Location": location}, b""


@pytest.fixture
def internal() -> Iterator[Server]:
    """The service that must stay unreachable: answers everything with a page full of secrets."""
    server = Server(lambda path, _: html("<article>INTERNAL-SECRET token=abc123</article>"))
    yield server
    server.close()


@pytest.fixture
def public(internal: Server, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[Respond], Server]]:
    """Public servers; the guard treats the port of `internal` as private, everything else as public."""

    def guard(url: str) -> None:
        if f":{internal.port}" in url:
            raise UnsafeUrlError("Адрес находится во внутренней сети и недоступен для фиксации")

    monkeypatch.setattr(capture, "ensure_public_url", guard)
    started: list[Server] = []

    def start(respond: Respond) -> Server:
        started.append(Server(respond))
        return started[-1]

    yield start
    for server in started:
        server.close()


# ---------------------------------------------------------------- capture


def test_redirect_to_an_internal_address_is_not_followed(internal: Server, public: Callable[[Respond], Server]) -> None:
    site = public(lambda path, _: redirect(f"{internal.url}/secret") if path == "/go" else html("<p>public</p>"))

    with pytest.raises(capture.CaptureError, match="внутренней сети"):
        capture.capture_page(f"{site.url}/go")

    assert internal.hits == []


def test_redirect_chain_through_public_hops_is_checked_at_every_hop(
    internal: Server, public: Callable[[Respond], Server]
) -> None:
    routes: dict[str, str] = {"/one": "/two", "/two": "/three", "/three": f"{internal.url}/secret"}
    site = public(lambda path, _: redirect(routes[path]) if path in routes else html("<p>public</p>"))

    with pytest.raises(capture.CaptureError, match="внутренней сети"):
        capture.capture_page(f"{site.url}/one")

    assert internal.hits == []
    assert {"/one", "/two", "/three"} <= set(site.hits)


def test_public_redirects_are_followed(public: Callable[[Respond], Server]) -> None:
    site = public(
        lambda path, _: redirect("/final") if path == "/old" else html("<article>Новый адрес страницы</article>")
    )

    captured = capture.capture_page(f"{site.url}/old")

    assert captured.final_url == f"{site.url}/final" and "Новый адрес" in captured.text


def test_scripts_frames_pop_ups_and_sockets_cannot_reach_internal_addresses(
    internal: Server, public: Callable[[Respond], Server]
) -> None:
    page = f"""<p>public page with an article text that is long enough</p>
<img src="{internal.url}/img">
<img src="/image-redirect">
<iframe src="{internal.url}/frame"></iframe>
<iframe src="/frame-redirect"></iframe>
<script>
fetch("{internal.url}/fetch").catch(() => {{}});
window.open("{internal.url}/popup");
new WebSocket("ws://127.0.0.1:{internal.port}/socket");
new Worker(URL.createObjectURL(new Blob([`fetch("{internal.url}/worker").catch(() => {{}})`])));
</script>"""

    def respond(path: str, _: Server) -> tuple[int, dict[str, str], bytes]:
        if path in {"/image-redirect", "/frame-redirect"}:
            return redirect(f"{internal.url}{path}")
        return html(page) if path == "/" else html("<p>other</p>")

    site = public(respond)

    captured = capture.capture_page(f"{site.url}/")
    time.sleep(0.5)  # requests that slipped through would have arrived by now

    assert "public page" in captured.text and "INTERNAL-SECRET" not in captured.text
    assert internal.hits == []
    assert "/image-redirect" in site.hits and "/frame-redirect" in site.hits


def test_page_that_navigates_to_an_internal_address_never_reaches_it(
    internal: Server, public: Callable[[Respond], Server]
) -> None:
    site = public(lambda path, _: html(f'<p>public page</p><script>location.href = "{internal.url}/secret"</script>'))

    # Depending on timing the capture keeps the public page or fails; the internal address is never contacted.
    with contextlib.suppress(capture.CaptureError):
        captured = capture.capture_page(f"{site.url}/")
        assert "INTERNAL-SECRET" not in captured.text
    time.sleep(0.3)

    assert internal.hits == []


def test_refused_capture_is_recorded_without_evidence(
    db: Session, world: World, internal: Server, public: Callable[[Respond], Server]
) -> None:
    site = public(lambda path, _: redirect(f"{internal.url}/secret"))
    user = world.users["mio_ust"]
    ad = add_ad(db, world.ust, None, url=f"{site.url}/go", capture_status=CaptureStatus.pending)

    capture.capture_ad(db, ad.id, user.id)

    assert ad.capture_status is CaptureStatus.failed and "внутренней сети" in (ad.capture_error or "")
    assert db.scalars(select(Evidence).where(Evidence.ad_post_id == ad.id)).all() == []
    assert db.scalars(select(Notification).where(Notification.user_id == user.id)).one().payload["error"]
    assert internal.hits == []


def test_verify_public_chain_checks_every_request_and_the_final_page(monkeypatch: pytest.MonkeyPatch) -> None:
    class Hop:
        def __init__(self, url: str, previous: "Hop | None" = None) -> None:
            self.url, self.redirected_from = url, previous

    class Reply:
        def __init__(self, request: Hop) -> None:
            self.request = request

    checked: list[str] = []
    monkeypatch.setattr(capture, "ensure_public_url", checked.append)

    capture._verify_public_chain(Reply(Hop("https://c/", Hop("https://b/", Hop("https://a/")))), "https://c/")  # type: ignore[arg-type]
    assert checked == ["https://c/", "https://b/", "https://a/", "https://c/"]

    def refuse_b(url: str) -> None:
        if url == "https://b/":
            raise UnsafeUrlError("internal")

    monkeypatch.setattr(capture, "ensure_public_url", refuse_b)
    with pytest.raises(UnsafeUrlError):
        capture._verify_public_chain(Reply(Hop("https://c/", Hop("https://b/"))), "https://c/")  # type: ignore[arg-type]
    with pytest.raises(UnsafeUrlError):
        capture._verify_public_chain(None, "https://b/")


# ---------------------------------------------------------------- malformed addresses

MALFORMED = [
    "http://example.com:99999/",
    "http://example.com:-1/",
    "http://[::1/",
    "http://[fe80::1%25eth0]:99999/",
    "http://" + "a" * 70 + ".com/",
]


@pytest.mark.parametrize("url", MALFORMED)
def test_malformed_addresses_are_unsafe_not_errors(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        ensure_public_url(url)


@pytest.mark.parametrize("url", [u for u in MALFORMED if "99999" in u or "-1" in u or "[::1/" in u])
def test_is_http_url_rejects_ports_out_of_range_and_broken_ipv6(url: str) -> None:
    assert is_http_url(url) is False


@pytest.mark.parametrize("url", MALFORMED)
def test_capture_endpoint_answers_422_for_malformed_urls(client: TestClient, world: World, url: str) -> None:
    response = client.post("/api/v1/ads/capture", headers=auth(world.users["mio_ust"]), json={"url": url})
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("url", ["http://example.com:99999/", "http://[::1/"])
def test_manual_endpoint_answers_422_for_malformed_urls(client: TestClient, world: World, url: str) -> None:
    response = client.post(
        "/api/v1/ads/manual", headers=auth(world.users["mio_ust"]), data={"text": "x", "platform": "other", "url": url}
    )
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------- re-check


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ads_urls.socket, "getaddrinfo", lambda *args, **kwargs: [(0, 0, 0, "", ("93.184.216.34", 443))])


def stale_ad(db: Session, world: World, url: str, **fields: Any) -> Any:
    old = datetime.now(UTC) - timedelta(days=10)
    values: dict[str, Any] = {"capture_status": CaptureStatus.done, "captured_at": old, "last_checked_at": old}
    return add_ad(db, world.ust, url=url, **{**values, **fields})


@pytest.mark.usefixtures("public_dns")
@pytest.mark.parametrize("location", ["http://example.com:99999/", "http://[::1/"])
def test_recheck_survives_a_malformed_redirect_and_goes_on(db: Session, world: World, location: str) -> None:
    broken = stale_ad(db, world, "https://alatau.test/broken")
    removed = stale_ad(db, world, "https://alatau.test/gone")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/broken":
            return httpx.Response(302, headers={"location": location})
        return httpx.Response(404)

    recheck.recheck_due(db, httpx.Client(transport=httpx.MockTransport(handler)))

    assert broken.status is AdStatus.captured
    assert broken.last_checked_at is not None and broken.last_checked_at > datetime.now(UTC) - timedelta(minutes=1)
    assert removed.status is AdStatus.removed_saved  # the run went on


@pytest.mark.usefixtures("public_dns")
def test_recheck_isolates_an_unexpected_failure_of_one_publication(db: Session, world: World) -> None:
    failing = stale_ad(db, world, "https://alatau.test/fails")
    removed = stale_ad(db, world, "https://alatau.test/gone")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fails":
            raise RuntimeError("unexpected")
        return httpx.Response(410)

    recheck.recheck_due(db, httpx.Client(transport=httpx.MockTransport(handler)))

    assert failing.status is AdStatus.captured and failing.last_checked_at > datetime.now(UTC) - timedelta(minutes=1)
    assert removed.status is AdStatus.removed_saved
