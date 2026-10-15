"""Collection of accounts: ingest of posts and photos, edits, errors of a source and the notice about them."""

import socket
from collections.abc import Iterable, Iterator
from datetime import datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors import base
from app.collectors.base import CollectedPost, CollectorError, IsKnown
from app.collectors.media import MAX_PHOTO_BYTES, MAX_PHOTOS
from app.models import AdPost, AdPostVersion, AppUser, Evidence, Notification, SourceAccount
from app.models.enums import (
    AdOrigin,
    AdVersionSource,
    CaptureStatus,
    EvidenceKind,
    NotificationKind,
    OcrStatus,
    Platform,
    Role,
)
from app.modules.ads import service, tasks
from app.modules.ads import urls as ads_urls
from tests.conftest import PNG_BYTES, World
from tests.test_ads_tasks import SessionFactory

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
CDN = "https://cdn.alatau.test"


@pytest.fixture
def empty_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base, "_registry", {})


@pytest.fixture
def dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `.test` hosts resolve to a public address, except `internal.*` and `loopback.*`. Other hosts (MinIO) keep
    their real address: this patches the `socket` module for everyone."""
    real = socket.getaddrinfo

    def resolve(host: str, *args: Any, **kwargs: Any) -> Any:
        if not host.endswith(".test"):
            return real(host, *args, **kwargs)
        address = (
            "10.0.0.5"
            if host.startswith("internal.")
            else "127.0.0.1"
            if host.startswith("loopback.")
            else "93.184.216.34"
        )
        return [(0, 0, 0, "", (address, 443))]

    monkeypatch.setattr(ads_urls.socket, "getaddrinfo", resolve)


class Media:
    """A fake photo server: what it serves by path, and which hosts were asked."""

    def __init__(self, files: dict[str, httpx.Response]) -> None:
        self.files = files
        self.hosts: list[str] = []

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._answer))

    def _answer(self, request: httpx.Request) -> httpx.Response:
        self.hosts.append(request.url.host)
        return self.files.get(request.url.path, httpx.Response(404))


def photo(content: bytes) -> httpx.Response:
    return httpx.Response(200, content=content)


def telegram_account(db: Session, world: World, handle: str = "alatau_demo", **fields: Any) -> SourceAccount:
    account = SourceAccount(platform=Platform.telegram, handle=handle, **{"territory_id": world.ust.id, **fields})
    db.add(account)
    db.flush()
    return account


def collected(external_id: str = "alatau_demo/1", text: str = "Бронь квартир", **fields: Any) -> CollectedPost:
    return CollectedPost(external_id=external_id, text=text, **fields)


# ---------------------------------------------------------------- photos of a post


@pytest.mark.usefixtures("bucket", "dns")
def test_photos_are_stored_as_evidence_after_the_checks(db: Session, world: World) -> None:
    media = Media(
        {
            "/ok.png": photo(PNG_BYTES),
            "/ok.jpg": photo(JPEG_BYTES),
            "/page.png": photo(b"<html>not an image</html>"),
            "/huge.png": photo(PNG_BYTES + b"\x00" * MAX_PHOTO_BYTES),
            "/redirect.png": httpx.Response(302, headers={"location": "http://internal.alatau.test/secret.png"}),
            "/secret.png": photo(PNG_BYTES),
        }
    )
    account = telegram_account(db, world)
    urls = [
        f"{CDN}/ok.png",
        f"{CDN}/ok.jpg",
        f"{CDN}/page.png",
        f"{CDN}/huge.png",
        f"{CDN}/missing.png",
        f"{CDN}/redirect.png",
        "http://internal.alatau.test/secret.png",
        "http://loopback.alatau.test/secret.png",
        "file:///etc/passwd",
    ]

    ad = service.ingest_collected_post(
        db, account, collected(url="https://t.me/alatau_demo/1", media_urls=urls), capture=True, client=media.client()
    )

    assert ad is not None
    stored = list(db.scalars(select(Evidence).where(Evidence.ad_post_id == ad.id).order_by(Evidence.id)))
    assert [(item.kind, item.content_type, item.source_url) for item in stored] == [
        (EvidenceKind.photo, "image/png", f"{CDN}/ok.png"),
        (EvidenceKind.photo, "image/jpeg", f"{CDN}/ok.jpg"),
    ]
    assert all(item.created_by is None for item in stored)
    assert ad.ocr_status is OcrStatus.pending and ad.origin is AdOrigin.collector
    # A private address is never requested: neither directly nor through a redirect.
    assert set(media.hosts) == {"cdn.alatau.test"}


@pytest.mark.usefixtures("bucket", "dns")
def test_at_most_ten_photos_are_kept(db: Session, world: World) -> None:
    media = Media({f"/{number}.png": photo(PNG_BYTES) for number in range(MAX_PHOTOS + 2)})
    urls = [f"{CDN}/{number}.png" for number in range(MAX_PHOTOS + 2)]

    ad = service.ingest_collected_post(
        db, telegram_account(db, world), collected(media_urls=urls), capture=True, client=media.client()
    )

    assert ad is not None
    assert len(db.scalars(select(Evidence).where(Evidence.ad_post_id == ad.id)).all()) == MAX_PHOTOS


@pytest.mark.usefixtures("bucket", "dns")
def test_a_post_whose_photos_all_fail_is_still_stored_without_ocr(db: Session, world: World) -> None:
    media = Media({})

    ad = service.ingest_collected_post(
        db, telegram_account(db, world), collected(media_urls=[f"{CDN}/gone.png"]), capture=True, client=media.client()
    )

    assert ad is not None and ad.ocr_status is None and ad.text == "Бронь квартир"
    assert db.scalars(select(Evidence)).all() == []


def test_a_post_without_media_needs_no_client(db: Session, world: World) -> None:
    ad = service.ingest_collected_post(db, telegram_account(db, world), collected(), capture=True)

    assert ad is not None and ad.ocr_status is None


def test_the_page_of_a_post_is_captured_only_when_the_collector_asks(db: Session, world: World) -> None:
    account = telegram_account(db, world)
    captured = service.ingest_collected_post(db, account, collected("a/1", url="https://t.me/a/1"), capture=True)
    not_captured = service.ingest_collected_post(db, account, collected("a/2", url="https://t.me/a/2"), capture=False)
    no_url = service.ingest_collected_post(db, account, collected("a/3"), capture=True)

    assert captured is not None and captured.capture_status is CaptureStatus.pending
    assert not_captured is not None and not_captured.capture_status is None
    assert no_url is not None and no_url.capture_status is None


# ---------------------------------------------------------------- edits


def test_a_known_post_with_a_new_text_gets_a_version(db: Session, world: World) -> None:
    account = telegram_account(db, world)
    first = service.ingest_collected_post(db, account, collected(text="Бронь за 10%"), capture=True)
    assert first is not None

    again = collected(text="Продажи закрыты")
    assert service.ingest_collected_post(db, account, again, capture=True) is None
    # The same edit seen again, and a change of spaces only, add nothing.
    assert service.ingest_collected_post(db, account, again, capture=True) is None
    assert service.ingest_collected_post(db, account, collected(text="Продажи   закрыты "), capture=True) is None
    assert service.ingest_collected_post(db, account, collected(text="Бронь за 10%"), capture=True) is None

    versions = list(
        db.scalars(select(AdPostVersion).where(AdPostVersion.ad_post_id == first.id).order_by(AdPostVersion.id))
    )
    assert [(version.text, version.source) for version in versions] == [
        ("Продажи закрыты", AdVersionSource.collector),
        ("Бронь за 10%", AdVersionSource.collector),
    ]
    assert first.text == "Бронь за 10%"  # the saved original is never rewritten
    assert db.scalars(select(AdPost)).all() == [first]


# ---------------------------------------------------------------- running the collectors


class Scripted:
    """A collector that yields `posts` and then raises `error`."""

    platform = Platform.telegram

    def __init__(
        self, posts: Iterable[CollectedPost] = (), error: Exception | None = None, capture_urls: bool = True
    ) -> None:
        self.posts = list(posts)
        self.error = error
        self.capture_urls = capture_urls
        self.refuse: set[str] = set()
        self.calls: list[str] = []

    def handles(self, account: SourceAccount) -> bool:
        return account.handle not in self.refuse

    def collect(self, account: SourceAccount, since: datetime, is_known: IsKnown) -> Iterator[CollectedPost]:
        self.calls.append(account.handle)
        yield from self.posts
        if self.error is not None:
            raise self.error


def recipients(db: Session, account: SourceAccount) -> set[int]:
    return {notice.user_id for notice in notices(db) if notice.entity_id == account.id}


def notices(db: Session) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(Notification.kind == NotificationKind.collector_failed).order_by(Notification.id)
        )
    )


@pytest.mark.usefixtures("empty_registry")
def test_a_failing_source_is_recorded_and_the_admins_hear_about_it_once(db: Session, world: World) -> None:
    collector = Scripted(error=CollectorError("Telegram ответил HTTP 429"))
    base.register(collector)
    account = telegram_account(db, world)

    assert service.run_collectors(db) == []

    assert account.last_error == "Telegram ответил HTTP 429" and account.last_error_at is not None
    assert account.last_collected_at is None
    notice = notices(db)[0]
    assert (notice.entity_type, notice.entity_id) == ("source_account", account.id)
    assert notice.payload == {"name": "alatau_demo", "platform": "telegram", "error": "Telegram ответил HTTP 429"}
    first_count = len(notices(db))
    assert world.users["admin"].id in recipients(db, account)

    # Still failing: the error is refreshed, nobody is told again.
    collector.error = CollectorError("Telegram ответил HTTP 503")
    service.run_collectors(db)
    assert account.last_error == "Telegram ответил HTTP 503" and len(notices(db)) == first_count

    # A successful run clears it; the next failure is a new transition and is announced.
    collector.error = None
    service.run_collectors(db)
    assert (account.last_error, account.last_error_at) == (None, None) and account.last_collected_at is not None
    collector.error = CollectorError("Telegram ответил HTTP 500")
    service.run_collectors(db)
    assert len(notices(db)) == 2 * first_count


@pytest.mark.usefixtures("empty_registry")
def test_only_the_admins_who_cover_the_territory_are_notified(db: Session, world: World) -> None:
    base.register(Scripted(error=CollectorError("сбой")))
    home = telegram_account(db, world)
    abroad = telegram_account(db, world, "semey_demo", territory_id=world.semey.id)

    service.run_collectors(db)

    admin, admin_semey = world.users["admin"].id, world.users["admin_semey"].id
    assert admin in recipients(db, home) and admin in recipients(db, abroad)
    assert admin_semey in recipients(db, abroad) and admin_semey not in recipients(db, home)
    # Administrators only.
    assert {notice.user_id for notice in notices(db)} <= set(
        db.scalars(select(AppUser.id).where(AppUser.role == Role.admin))
    )


@pytest.mark.usefixtures("empty_registry")
def test_an_account_without_a_territory_is_reported_to_the_national_admins(db: Session, world: World) -> None:
    base.register(Scripted(error=CollectorError("сбой")))
    account = SourceAccount(platform=Platform.telegram, handle="nowhere_demo")
    db.add(account)
    db.flush()

    service.run_collectors(db)

    national = set(db.scalars(select(AppUser.id).where(AppUser.role == Role.admin, AppUser.territory_id.is_(None))))
    assert world.users["admin"].id in national and recipients(db, account) == national


@pytest.mark.usefixtures("empty_registry")
def test_an_unexpected_failure_is_logged_not_shown(db: Session, world: World, caplog: pytest.LogCaptureFixture) -> None:
    base.register(Scripted(error=RuntimeError("token=s3cr3t in https://x/?token=s3cr3t")))
    account = telegram_account(db, world)
    db.commit()

    service.run_collectors(db)

    assert account.last_error == "Непредвиденная ошибка сбора, подробности в журнале сервера"
    assert "s3cr3t" not in (account.last_error or "") and "s3cr3t" in caplog.text
    assert recipients(db, account)


@pytest.mark.usefixtures("empty_registry")
def test_posts_read_before_the_error_are_kept(db: Session, world: World) -> None:
    base.register(Scripted([collected("alatau_demo/1", url="https://t.me/alatau_demo/1")], CollectorError("сбой")))
    account = telegram_account(db, world)

    created = service.run_collectors(db)

    ad = db.scalars(select(AdPost)).one()
    assert created == [(ad.id, True)] and ad.source_account_id == account.id
    assert account.last_error == "сбой" and account.last_collected_at is None


@pytest.mark.usefixtures("empty_registry")
def test_the_collector_decides_whether_pages_are_captured(db: Session, world: World) -> None:
    base.register(Scripted([collected(url="https://t.me/alatau_demo/1")], capture_urls=False))
    telegram_account(db, world)

    created = service.run_collectors(db)

    assert [capture for _, capture in created] == [False]
    assert db.scalars(select(AdPost)).one().capture_status is None


@pytest.mark.usefixtures("empty_registry")
def test_accounts_the_collector_does_not_serve_are_left_alone(db: Session, world: World) -> None:
    collector = Scripted(error=CollectorError("сбой"))
    collector.refuse = {"refused_demo"}
    base.register(collector)
    refused = telegram_account(db, world, "refused_demo")
    other_platform = SourceAccount(platform=Platform.instagram, handle="alatau_demo", territory_id=world.ust.id)
    db.add(other_platform)
    db.flush()

    service.run_collectors(db)

    assert collector.calls == []
    for untouched in (refused, other_platform):
        assert (untouched.last_error, untouched.last_error_at, untouched.last_collected_at) == (None, None, None)
    assert notices(db) == []


@pytest.mark.usefixtures("empty_registry")
def test_a_post_seen_again_with_a_new_text_is_a_version_not_a_new_post(db: Session, world: World) -> None:
    collector = Scripted([collected(text="Бронь за 10%")])
    base.register(collector)
    telegram_account(db, world)
    assert len(service.run_collectors(db)) == 1

    collector.posts = [collected(text="Продажи закрыты")]
    assert service.run_collectors(db) == []

    assert [version.text for version in db.scalars(select(AdPostVersion))] == ["Продажи закрыты"]


# ---------------------------------------------------------------- one account now


@pytest.mark.usefixtures("empty_registry")
def test_collect_source_collects_that_account_only(db: Session, world: World) -> None:
    collector = Scripted([collected(url="https://t.me/muted_demo/1")])
    base.register(collector)
    telegram_account(db, world)
    muted = telegram_account(db, world, "muted_demo", is_watched=False)

    created = service.collect_source(db, muted.id)

    assert collector.calls == ["muted_demo"]  # watching only decides the scheduled runs
    assert len(created) == 1 and muted.last_collected_at is not None
    assert service.collect_source(db, 0) == []


@pytest.mark.usefixtures("empty_registry")
def test_collect_source_task_queues_the_pipeline_of_new_posts(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    queued: list[tuple[int, bool, int | None]] = []
    seen: list[int] = []

    def collect_source(session: Session, source_id: int) -> list[tuple[int, bool]]:
        seen.append(source_id)
        return [(21, True), (22, False)]

    def record(ad_id: int, *, capture: bool, requested_by: int | None) -> bool:
        queued.append((ad_id, capture, requested_by))
        return True

    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: SessionFactory(db))
    monkeypatch.setattr(tasks.service, "collect_source", collect_source)
    monkeypatch.setattr(tasks.service, "dispatch_pipeline", record)

    tasks.collect_source(5)

    assert seen == [5] and queued == [(21, True, None), (22, False, None)]
