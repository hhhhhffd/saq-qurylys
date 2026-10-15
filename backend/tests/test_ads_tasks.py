import hashlib
import logging
import socket
import struct
import threading
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.collectors import base as collectors
from app.collectors.base import CollectedPost, IsKnown
from app.config import get_settings
from app.models import AdPost, AuditLog, Evidence, Notification, SourceAccount
from app.models.enums import (
    AdStatus,
    CaptureStatus,
    EvidenceKind,
    NotificationKind,
    Platform,
)
from app.modules.ads import capture, recheck, service, tasks
from app.modules.ads.urls import UnsafeUrlError, ensure_public_url, telegram_embed_url
from app.storage import EvidenceLink
from tests.conftest import PNG_BYTES, World, make_object
from tests.support_ads import add_ad
from tests.support_collect import collect_locks  # noqa: F401

DAYS_AGO = timedelta(days=4)  # older than the default `recheck_after_days` (3)


class SessionFactory:
    """Stands in for the sessionmaker so that the tasks work inside the test transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def __call__(self) -> "SessionFactory":
        return self

    def __enter__(self) -> Session:
        return self.session

    def __exit__(self, *args: object) -> None:
        return None


# ---------------------------------------------------------------- pipeline dispatch


class FakeChain:
    def __init__(self, *signatures: Any) -> None:
        self.signatures = signatures
        self.options: dict[str, Any] = {}

    def apply_async(self, **options: Any) -> None:
        self.options = options


def describe(chain: FakeChain) -> list[tuple[str, tuple[Any, ...], str, bool]]:
    return [(sig.task, tuple(sig.args), sig.options["queue"], sig.immutable) for sig in chain.signatures]


def test_pipeline_is_a_chain_of_immutable_steps_on_their_queues(monkeypatch: pytest.MonkeyPatch) -> None:
    chains: list[FakeChain] = []

    def fake_chain(*sigs: Any) -> FakeChain:
        chains.append(FakeChain(*sigs))
        return chains[-1]

    monkeypatch.setattr(get_settings(), "events_enabled", True)
    monkeypatch.setattr(service, "chain", fake_chain)

    assert service.dispatch_pipeline(7, capture=True, requested_by=3) is True
    assert service.dispatch_pipeline(8, capture=False, requested_by=None) is True

    assert describe(chains[0]) == [
        ("archive.capture", (7, 3), "archive", True),
        ("nlp.ocr", (7,), "nlp", True),
        ("nlp.analyze", (7,), "nlp", True),
        ("nlp.link", (7,), "nlp", True),
        ("nlp.llm_extract", (7,), "nlp", True),
    ]
    assert [step[0] for step in describe(chains[1])] == ["nlp.ocr", "nlp.analyze", "nlp.link", "nlp.llm_extract"]
    assert chains[0].options == {"retry": False}


def test_pipeline_reports_a_broker_outage_and_is_silent_when_events_are_off(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*sigs: Any) -> Any:
        raise ConnectionError("broker is down")

    monkeypatch.setattr(service, "chain", broken)
    assert service.dispatch_pipeline(1, capture=True, requested_by=None) is True  # events are off in tests
    monkeypatch.setattr(get_settings(), "events_enabled", True)
    assert service.dispatch_pipeline(1, capture=True, requested_by=None) is False


# ---------------------------------------------------------------- re-check


@pytest.fixture(autouse=True)
def no_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recheck, "ensure_public_url", lambda url: None)


def run_recheck(db: Session, handler: Callable[[httpx.Request], httpx.Response]) -> list[int]:
    return recheck.recheck_due(db, httpx.Client(transport=httpx.MockTransport(handler)))


def due_ad(db: Session, world: World, url: str | None = "https://alatau.test/post/1", **fields: Any) -> AdPost:
    values: dict[str, Any] = {
        "url": url,
        "last_checked_at": datetime.now(UTC) - DAYS_AGO,
        "capture_status": CaptureStatus.done,
    }
    return add_ad(db, world.ust, **{**values, **fields})


@pytest.mark.parametrize("status_code", [404, 410])
def test_removed_publication_is_marked_and_its_evidence_stays(
    db: Session, world: World, bucket: str, status_code: int
) -> None:
    obj = make_object(db, world.ust)
    ad = due_ad(db, world, object_id=obj.id)
    kept = storage.put_evidence(
        db, PNG_BYTES, EvidenceKind.screenshot_png, "image/png", ad.url, link=EvidenceLink(ad_post_id=ad.id)
    )

    changed = run_recheck(db, lambda request: httpx.Response(status_code))

    assert changed == [obj.id]
    assert ad.status is AdStatus.removed_saved and ad.removed_detected_at is not None
    assert ad.last_checked_at is not None and ad.last_checked_at > datetime.now(UTC) - timedelta(minutes=1)
    assert db.get(Evidence, kept.id) is not None
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "ad.removed_detected")).one()
    assert entry.user_id is None and entry.entity_id == ad.id
    assert entry.before["status"] == "captured" and entry.after["status"] == "removed_saved"
    assert entry.after["http_status"] == status_code


def test_page_that_says_the_post_is_gone_counts_as_removed(db: Session, world: World) -> None:
    ad = due_ad(db, world)
    run_recheck(db, lambda request: httpx.Response(200, text="<h1>Объявление не найдено</h1>"))
    assert ad.status is AdStatus.removed_saved


def test_live_publication_only_gets_a_new_check_time(db: Session, world: World) -> None:
    ad = due_ad(db, world, status=AdStatus.verification)
    before = ad.last_checked_at

    assert run_recheck(db, lambda request: httpx.Response(200, text="<p>Бронь квартир</p>")) == []

    assert ad.status is AdStatus.verification and ad.removed_detected_at is None
    assert ad.last_checked_at is not None and before is not None and ad.last_checked_at > before


def test_redirects_are_followed_hop_by_hop(db: Session, world: World) -> None:
    moved_to_gone = due_ad(db, world, url="https://alatau.test/old")
    moved_to_live = due_ad(db, world, url="https://alatau.test/live")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        path = request.url.path
        if path == "/old":
            return httpx.Response(301, headers={"location": "/moved"})
        if path == "/live":
            return httpx.Response(302, headers={"location": "https://alatau.test/fresh"})
        return httpx.Response(404 if path == "/moved" else 200, text="ok")

    run_recheck(db, handler)

    assert moved_to_gone.status is AdStatus.removed_saved
    assert moved_to_live.status is AdStatus.captured
    assert "https://alatau.test/fresh" in seen


def test_every_hop_is_checked_against_internal_addresses(
    db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def guard(url: str) -> None:
        if "internal" in url:
            raise UnsafeUrlError("internal")

    monkeypatch.setattr(recheck, "ensure_public_url", guard)
    ad = due_ad(db, world)
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fetched.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://internal.test/secret"})

    run_recheck(db, handler)

    assert fetched == ["https://alatau.test/post/1"]
    assert ad.status is AdStatus.captured  # inconclusive, not removed


def test_inconclusive_checks_do_not_mark_removal_but_postpone_the_next_check(db: Session, world: World) -> None:
    server_error = due_ad(db, world, url="https://alatau.test/a")
    unreachable = due_ad(db, world, url="https://alatau.test/b")
    looping = due_ad(db, world, url="https://alatau.test/c")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a":
            return httpx.Response(503)
        if request.url.path == "/b":
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(302, headers={"location": "/c"})

    assert run_recheck(db, handler) == []

    for ad in (server_error, unreachable, looping):
        assert ad.status is AdStatus.captured
        assert ad.last_checked_at is not None and ad.last_checked_at > datetime.now(UTC) - timedelta(minutes=1)


def test_only_publications_that_are_due_are_checked(db: Session, world: World) -> None:
    now = datetime.now(UTC)
    never_checked = add_ad(db, world.ust, url="https://alatau.test/1", created_at=now - DAYS_AGO)
    due = due_ad(db, world, url="https://alatau.test/2")
    manual = due_ad(db, world, url="https://alatau.test/3", capture_status=None)
    skipped = [
        due_ad(db, world, url="https://alatau.test/recent", last_checked_at=now - timedelta(days=2)),
        due_ad(db, world, url="https://alatau.test/removed", status=AdStatus.removed_saved),
        due_ad(db, world, url="https://alatau.test/pending", capture_status=CaptureStatus.pending),
        due_ad(db, world, url="https://alatau.test/failed", capture_status=CaptureStatus.failed),
        due_ad(db, world, url=None),
        add_ad(db, world.ust, url="https://alatau.test/fresh-entry"),  # entered a moment ago
    ]
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return httpx.Response(200)

    run_recheck(db, handler)

    assert sorted(requested) == ["/1", "/2", "/3"]
    assert all(ad.last_checked_at is not None for ad in (never_checked, due, manual))
    assert [ad.last_checked_at is None or ad.last_checked_at < now - timedelta(minutes=1) for ad in skipped] == [
        True
    ] * 6


def test_recheck_task_reports_the_changed_objects(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    changed: list[int] = []
    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: SessionFactory(db))
    monkeypatch.setattr(tasks.recheck, "recheck_due", lambda session, client: [5, 6])
    monkeypatch.setattr(tasks.service, "refresh_all_claimed_readiness", lambda session: [6, 7])
    monkeypatch.setattr(tasks, "objects_changed", lambda ids: changed.extend(ids))

    tasks.recheck_due()

    assert changed == [5, 6, 6, 7]


def test_claimed_readiness_of_all_objects_follows_the_ad_window(db: Session, world: World) -> None:
    now = datetime.now(UTC)
    fresh = make_object(db, world.ust, "Свежая заявка")
    stale = make_object(db, world.ust, "Старая заявка", readiness_claimed_pct=80)
    quiet = make_object(db, world.ust, "Без рекламы")
    unchanged = make_object(db, world.ust, "Без изменений", readiness_claimed_pct=30)
    add_ad(db, world.ust, object_id=fresh.id, claimed_readiness_pct=50, published_at=now - timedelta(days=1))
    add_ad(db, world.ust, object_id=fresh.id, claimed_readiness_pct=35, published_at=now - timedelta(days=2))
    add_ad(db, world.ust, object_id=stale.id, claimed_readiness_pct=80, published_at=now - timedelta(days=60))
    add_ad(db, world.ust, object_id=unchanged.id, claimed_readiness_pct=30, published_at=now - timedelta(days=1))

    changed = service.refresh_all_claimed_readiness(db)

    assert sorted(changed) == sorted([fresh.id, stale.id])
    assert (fresh.readiness_claimed_pct, stale.readiness_claimed_pct) == (50, None)
    assert quiet.readiness_claimed_pct is None and unchanged.readiness_claimed_pct == 30


# ---------------------------------------------------------------- collectors


class FakeCollector:
    platform = Platform.telegram
    capture_urls = True

    def __init__(self, posts: Iterable[CollectedPost], fail_for: str | None = None) -> None:
        self.posts = list(posts)
        self.fail_for = fail_for
        self.calls: list[tuple[str, datetime]] = []

    def handles(self, account: SourceAccount) -> bool:
        return True

    def collect(self, account: SourceAccount, since: datetime, is_known: IsKnown) -> Iterable[CollectedPost]:
        self.calls.append((account.handle, since))
        if account.handle == self.fail_for:
            raise RuntimeError("platform is down")
        return self.posts


def test_collect_does_nothing_without_collectors(db: Session, world: World, caplog: pytest.LogCaptureFixture) -> None:
    db.add(SourceAccount(platform=Platform.telegram, handle="alatau", territory_id=world.ust.id))
    db.flush()
    with caplog.at_level(logging.INFO, logger="app.modules.ads.service"):
        assert service.run_collectors(db) == []
    assert "no collectors" in caplog.text
    assert db.scalars(select(AdPost)).all() == []


@pytest.mark.usefixtures("collect_locks")
def test_collect_ingests_new_posts_of_watched_accounts(
    db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(collectors, "_registry", {})
    posts = [
        CollectedPost(external_id="alatau/1", text="Бронь квартир", url="https://t.me/alatau/1", author="Alatau"),
        CollectedPost(external_id="alatau/2", text="Без ссылки", links=["https://alatau.kz"]),
    ]
    collector = FakeCollector(posts, fail_for="broken")
    collectors.register(collector)
    obj = make_object(db, world.ust)
    watched = SourceAccount(platform=Platform.telegram, handle="alatau", object_id=obj.id)
    broken = SourceAccount(platform=Platform.telegram, handle="broken", territory_id=world.ust.id)
    muted = SourceAccount(platform=Platform.telegram, handle="muted", is_watched=False)
    other_platform = SourceAccount(platform=Platform.instagram, handle="alatau", territory_id=world.ust.id)
    db.add_all([watched, broken, muted, other_platform])
    db.flush()

    created = service.run_collectors(db)

    ads = list(db.scalars(select(AdPost).order_by(AdPost.id)))
    assert [(ad.external_id, ad.url is not None) for ad in ads] == [("alatau/1", True), ("alatau/2", False)]
    assert created == [ads[0].id, ads[1].id]
    first = ads[0]
    assert (first.platform, first.source_account_id, first.territory_id) == (
        Platform.telegram,
        watched.id,
        world.ust.id,
    )
    assert (first.text, first.author, first.capture_status) == ("Бронь квартир", "Alatau", CaptureStatus.pending)
    assert ads[1].capture_status is None and ads[1].links == ["https://alatau.kz"]
    assert watched.last_collected_at is not None and broken.last_collected_at is None
    assert muted.last_collected_at is None and sorted(handle for handle, _ in collector.calls) == ["alatau", "broken"]

    # The second run finds the same posts: nothing new, and the window starts at the previous collection.
    first_run_at = watched.last_collected_at
    assert service.run_collectors(db) == []
    assert dict(collector.calls[-2:])["alatau"] == first_run_at


def test_collect_all_task_runs_the_collectors_in_its_session(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[Session] = []

    def run_collectors(session: Session) -> list[int]:
        ran.append(session)
        return []

    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: SessionFactory(db))
    monkeypatch.setattr(tasks.service, "run_collectors", run_collectors)
    tasks.run_all()
    assert ran == [db]


# ---------------------------------------------------------------- URL guard


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost:8000/",
        "http://[::1]/",
        "http://10.1.2.3/",
        "http://192.168.0.10/x",
        "http://172.16.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0/",
        "http://[::ffff:127.0.0.1]/",
        "ftp://example.com/file",
        "file:///etc/passwd",
    ],
)
def test_internal_addresses_and_other_schemes_are_refused(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        ensure_public_url(url)


def test_public_addresses_pass() -> None:
    ensure_public_url("https://93.184.216.34/page")  # a literal address: no DNS needed


def test_telegram_embed_url_only_for_posts() -> None:
    assert telegram_embed_url("https://t.me/alatau_news/42") == "https://t.me/alatau_news/42?embed=1&mode=tme"
    assert telegram_embed_url("https://t.me/s/alatau_news/42?x=1") == "https://t.me/alatau_news/42?embed=1&mode=tme"
    assert telegram_embed_url("https://t.me/s/alatau_news") is None
    assert telegram_embed_url("https://example.com/alatau_news/42") is None


# ---------------------------------------------------------------- capture (real Chromium)

PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>ЖК Алатау</title>
<meta property="article:published_time" content="2026-10-01T09:30:00+05:00"></head>
<body><header>Меню</header>
<article><h1>ЖК Алатау</h1>
<p>Откройте бронирование квартир уже сегодня. Первоначальный взнос от 10%.</p>
<p>Звоните: 8 777 123 45 67</p></article>
<img src="__ALIAS__/secret.png" alt="">
</body></html>"""


TELEGRAM_WIDGET = """<!doctype html><html><body><div class="tgme_widget_message">
<div class="tgme_widget_message_text">Бронь открыта!<br>Звоните сегодня</div>
<a><time datetime="2026-08-26T19:12:34+00:00">Aug 26</time></a></div></body></html>"""
TELEGRAM_CHANNEL_CARD = """<!doctype html><html><head><meta charset="utf-8">
<meta property="og:description" content="Официальный канал застройщика: продажи квартир"></head>
<body><main>Предпросмотр канала</main></body></html>"""
TELEGRAM_FEED = """<!doctype html><html><body><main>
<div class="tgme_widget_message"><div class="tgme_widget_message_text">Первый пост ленты</div>
<time datetime="2026-01-01T10:00:00+00:00">1 Jan</time></div>
<div class="tgme_widget_message"><div class="tgme_widget_message_text">Второй пост ленты</div>
<time datetime="2026-01-02T10:00:00+00:00">2 Jan</time></div></main></body></html>"""


class Site:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                site.requests.append((self.path, self.headers.get("User-Agent", "")))
                html = {
                    "/ad": PAGE.replace("__ALIAS__", site.alias_url),
                    "/card": TELEGRAM_CHANNEL_CARD,
                    "/widget": TELEGRAM_WIDGET,
                    "/empty-widget": "<!doctype html><html><body></body></html>",
                    "/feed": TELEGRAM_FEED,
                }
                if self.path in html:
                    body, status, kind = html[self.path].encode(), 200, "text/html; charset=utf-8"
                elif self.path == "/secret.png":
                    body, status, kind = PNG_BYTES, 200, "image/png"
                else:
                    body, status, kind = b"<h1>nope</h1>", 404, "text/html"
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return None

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{port}"
        self.alias_url = f"http://localhost:{port}"  # the same server under another host name
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def paths(self) -> list[str]:
        return [path for path, _ in self.requests]


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> Iterator[Site]:
    """A local page served over HTTP; the guard against internal addresses is lifted for it."""
    monkeypatch.setattr(capture, "ensure_public_url", lambda url: None)
    site = Site()
    yield site
    site.server.shutdown()
    site.server.server_close()


def stored_bytes(row: Evidence) -> bytes:
    response = storage.open_evidence(row)
    try:
        return bytes(response.read())
    finally:
        response.close()
        response.release_conn()


def test_capture_stores_png_and_mhtml_evidence_and_the_page_text(
    db: Session, world: World, bucket: str, site: Site
) -> None:
    user = world.users["mio_ust"]
    ad = add_ad(
        db, world.ust, None, url=f"{site.url}/ad", platform=Platform.website, capture_status=CaptureStatus.pending
    )

    capture.capture_ad(db, ad.id, user.id)

    assert ad.capture_status is CaptureStatus.done and ad.capture_error is None
    assert ad.text is not None and "Откройте бронирование квартир уже сегодня" in ad.text
    assert "Звоните: 8 777 123 45 67" in ad.text and "Меню" not in ad.text  # the article, not the whole page
    assert ad.captured_at is not None and ad.last_checked_at is not None
    assert ad.published_at == datetime(2026, 10, 1, 4, 30, tzinfo=UTC)

    rows = list(db.scalars(select(Evidence).where(Evidence.ad_post_id == ad.id).order_by(Evidence.id)))
    assert [(row.kind, row.content_type) for row in rows] == [
        (EvidenceKind.screenshot_png, "image/png"),
        (EvidenceKind.archive_mhtml, "multipart/related"),
    ]
    for row in rows:
        data = stored_bytes(row)
        assert hashlib.sha256(data).hexdigest() == row.sha256 and len(data) == row.size_bytes
        assert row.source_url == f"{site.url}/ad" and row.created_by == user.id and row.ad_post_id == ad.id
    png, mhtml = (stored_bytes(row) for row in rows)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", png[16:24])[0] == capture.VIEWPORT["width"]
    assert mhtml.startswith(b"From: <Saved by Blink>")
    assert f"Snapshot-Content-Location: {site.url}/ad".encode() in mhtml
    assert {agent for _, agent in site.requests} == {capture.USER_AGENT}


def test_capture_keeps_the_text_that_a_person_entered(db: Session, world: World, bucket: str, site: Site) -> None:
    ad = add_ad(db, world.ust, "Текст, внесённый вручную", url=f"{site.url}/ad", capture_status=CaptureStatus.pending)
    capture.capture_ad(db, ad.id, None)
    assert ad.capture_status is CaptureStatus.done and ad.text == "Текст, внесённый вручную"


def test_capture_is_not_repeated_for_a_finished_capture(db: Session, world: World, site: Site) -> None:
    ad = add_ad(db, world.ust, url=f"{site.url}/ad", capture_status=CaptureStatus.done)
    capture.capture_ad(db, ad.id, None)
    assert site.requests == []


def test_browser_does_not_load_subresources_from_internal_hosts(
    db: Session, world: World, bucket: str, site: Site, monkeypatch: pytest.MonkeyPatch
) -> None:
    def loads_image(guard: Callable[[str], None]) -> bool:
        monkeypatch.setattr(capture, "ensure_public_url", guard)
        site.requests.clear()
        ad = add_ad(db, world.ust, None, url=f"{site.url}/ad", capture_status=CaptureStatus.pending)
        capture.capture_ad(db, ad.id, None)
        assert ad.capture_status is CaptureStatus.done
        return "/secret.png" in site.paths()

    def refuse_alias(url: str) -> None:
        if "localhost" in url:
            raise UnsafeUrlError("internal")

    assert loads_image(lambda url: None) is True  # the image is reachable when nothing is blocked
    assert loads_image(refuse_alias) is False


def test_telegram_post_text_comes_from_its_widget_not_from_the_channel_card(
    db: Session, world: World, bucket: str, site: Site, monkeypatch: pytest.MonkeyPatch
) -> None:
    widgets = {"/card": "/widget", "/card-deleted": "/empty-widget"}
    monkeypatch.setattr(capture, "telegram_embed_url", lambda url: site.url + widgets[url.removeprefix(site.url)])
    monkeypatch.setattr(capture, "detect_platform", lambda url: Platform.telegram)

    def run(path: str) -> AdPost:
        ad = add_ad(db, world.ust, None, url=site.url + path, capture_status=CaptureStatus.pending)
        capture.capture_ad(db, ad.id, None)
        return ad

    post = run("/card")
    assert post.capture_status is CaptureStatus.done
    assert post.text == "Бронь открыта!\nЗвоните сегодня"
    assert post.published_at == datetime(2026, 8, 26, 19, 12, 34, tzinfo=UTC)
    assert db.scalars(select(Evidence).where(Evidence.ad_post_id == post.id)).all()[0].source_url == site.url + "/card"

    # The channel card of a post that no longer exists says "Официальный канал…": that is not the post's text.
    monkeypatch.setattr(
        capture, "telegram_embed_url", lambda url: site.url + "/empty-widget" if url.endswith("/card") else None
    )
    deleted = run("/card")
    assert deleted.capture_status is CaptureStatus.done and deleted.text is None


def test_feed_page_gives_its_whole_text_and_no_publication_time(
    db: Session, world: World, bucket: str, site: Site, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(capture, "detect_platform", lambda url: Platform.telegram)
    ad = add_ad(db, world.ust, None, url=f"{site.url}/feed", capture_status=CaptureStatus.pending)

    capture.capture_ad(db, ad.id, None)

    assert ad.text is not None and "Первый пост ленты" in ad.text and "Второй пост ленты" in ad.text
    assert ad.published_at is None


def test_text_is_the_caption_on_instagram_and_the_page_text_elsewhere() -> None:
    info = {"description": "Подпись к посту", "body": "Войдите, чтобы продолжить. " * 5, "message": "", "published": ""}
    assert capture._choose_text(info, Platform.instagram) == "Подпись к посту"
    assert capture._choose_text(info, Platform.telegram) == info["body"]
    assert capture._choose_text(info, Platform.website) == info["body"]
    short = {**info, "body": "Меню", "description": "Подробное описание страницы со всеми условиями продажи"}
    assert capture._choose_text(short, Platform.website) == short["description"]
    assert capture._choose_text({**info, "message": "Текст поста"}, Platform.telegram) == "Текст поста"


def test_failed_capture_is_recorded_and_reported_to_the_requesting_user(db: Session, world: World, site: Site) -> None:
    user = world.users["mio_ust"]
    ad = add_ad(db, world.ust, None, url=f"{site.url}/gone", capture_status=CaptureStatus.pending)

    capture.capture_ad(db, ad.id, user.id)

    assert ad.capture_status is CaptureStatus.failed and ad.capture_error == "HTTP 404"
    assert db.scalars(select(Evidence).where(Evidence.ad_post_id == ad.id)).all() == []
    note = db.scalars(select(Notification).where(Notification.user_id == user.id)).one()
    assert note.kind is NotificationKind.capture_failed and note.entity_id == ad.id and note.read_at is None
    assert note.payload == {"url": f"{site.url}/gone", "error": "HTTP 404"}


def test_unreachable_page_fails_without_raising(db: Session, world: World, site: Site) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    ad = add_ad(db, world.ust, None, url=f"http://127.0.0.1:{closed_port}/", capture_status=CaptureStatus.pending)

    capture.capture_ad(db, ad.id, None)  # no requesting user: nobody to notify

    assert ad.capture_status is CaptureStatus.failed and ad.capture_error
    assert db.scalars(select(Notification)).all() == []


def test_capture_refuses_internal_addresses_without_starting_a_browser(db: Session, world: World) -> None:
    ad = add_ad(
        db, world.ust, None, url="http://169.254.169.254/latest/meta-data/", capture_status=CaptureStatus.pending
    )
    capture.capture_ad(db, ad.id, None)
    assert ad.capture_status is CaptureStatus.failed and "внутренней сети" in (ad.capture_error or "")


def test_unexpected_evidence_failure_rolls_back_partial_evidence(
    db: Session, world: World, bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = world.users["mio_ust"]
    ad = add_ad(db, world.ust, None, url="https://alatau.test/ad", capture_status=CaptureStatus.pending)
    real_put = storage.put_evidence
    calls = {"count": 0}

    def flaky(*args: Any, **kwargs: Any) -> Evidence:
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("storage is down")
        return real_put(*args, **kwargs)

    monkeypatch.setattr(storage, "put_evidence", flaky)
    page = capture.PageCapture(
        png=PNG_BYTES, mhtml=b"From: x", final_url="https://alatau.test/ad", text="t", published_at=None
    )

    capture.capture_ad(db, ad.id, user.id, page_capture=lambda url: page)

    assert ad.capture_status is CaptureStatus.failed and ad.capture_error == "storage is down"
    assert db.scalars(select(Evidence).where(Evidence.ad_post_id == ad.id)).all() == []


def test_capture_task_uses_the_requesting_user(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int | None]] = []
    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: SessionFactory(db))
    monkeypatch.setattr(tasks, "capture_ad", lambda session, ad_id, requested_by: calls.append((ad_id, requested_by)))
    tasks.capture(5, 9)
    tasks.capture(6)
    assert calls == [(5, 9), (6, None)]
