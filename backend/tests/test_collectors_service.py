"""Collection of accounts: ingest of posts and photos, edits, errors of a source and the notice about them."""

import logging
import socket
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from selectolax.lexbor import LexborHTMLParser
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors import base
from app.collectors import lock as collect_lock
from app.collectors.base import CollectedPost, CollectorError, IsKnown
from app.collectors.media import MAX_PHOTO_BYTES, MAX_PHOTOS
from app.collectors.telegram import parse_message
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
from app.modules.ads import recheck, service, tasks
from app.modules.ads import urls as ads_urls
from app.modules.ads.versions import record_version
from app.modules.nlp.service import analyze_ad
from app.modules.nlp.text import split_ocr
from tests.conftest import PNG_BYTES, World
from tests.support_collect import collect_locks, lock_db  # noqa: F401
from tests.test_ads_tasks import SessionFactory

pytestmark = pytest.mark.usefixtures("collect_locks")

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
CDN = "https://cdn.alatau.test"


@pytest.fixture
def empty_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base, "_registry", {})


@pytest.fixture
def dispatched(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, bool, int | None]]:
    """The pipelines the collection queues (the broker answers)."""
    queued: list[tuple[int, bool, int | None]] = []

    def record(ad_post_id: int, *, capture: bool, requested_by: int | None) -> bool:
        queued.append((ad_post_id, capture, requested_by))
        return True

    monkeypatch.setattr(service, "dispatch_pipeline", record)
    return queued


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

    ad = service.ingest_collected_post(db, account, collected(url="https://t.me/alatau_demo/1"), capture=True)
    assert ad is not None
    service.store_collected_photos(db, ad, urls, media.client())

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

    ad = service.ingest_collected_post(db, telegram_account(db, world), collected(), capture=True)
    assert ad is not None
    service.store_collected_photos(db, ad, urls, media.client())

    assert len(db.scalars(select(Evidence).where(Evidence.ad_post_id == ad.id)).all()) == MAX_PHOTOS


@pytest.mark.usefixtures("bucket", "dns")
def test_a_post_whose_photos_all_fail_is_still_stored_without_ocr(db: Session, world: World) -> None:
    media = Media({})

    ad = service.ingest_collected_post(db, telegram_account(db, world), collected(), capture=True)
    assert ad is not None
    service.store_collected_photos(db, ad, [f"{CDN}/gone.png"], media.client())

    assert ad.ocr_status is None and ad.text == "Бронь квартир"
    assert db.scalars(select(Evidence)).all() == []


def test_a_post_is_stored_without_its_photos_which_come_in_a_later_step(db: Session, world: World) -> None:
    ad = service.ingest_collected_post(
        db, telegram_account(db, world), collected(media_urls=[f"{CDN}/ok.png"]), capture=True
    )

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


def test_nul_characters_and_the_ocr_marker_are_removed_from_third_party_text(db: Session, world: World) -> None:
    account = telegram_account(db, world)
    post = collected(text="Бронь\x00 10%\n\n[OCR]\nподделка", author="Ал\x00атау")

    ad = service.ingest_collected_post(db, account, post, capture=True)

    assert ad is not None
    assert (ad.text, ad.author) == ("Бронь 10%\n\nподделка", "Алатау")
    assert split_ocr(ad.text or "")[1] is None  # nothing is passed for the text read from the photos
    # The same post seen again has the same text: it is no edit.
    assert service.ingest_collected_post(db, account, post, capture=True) is None
    assert db.scalars(select(AdPostVersion)).all() == []


def test_the_links_taken_from_the_markup_survive_the_analysis(db: Session, world: World) -> None:
    post = collected(text="Подробнее: https://shown.test/x", links=["https://hidden.test/a", "https://shown.test/x"])

    ad = service.ingest_collected_post(db, telegram_account(db, world), post, capture=True)

    assert ad is not None and ad.links == ["https://hidden.test/a", "https://shown.test/x"]
    analyze_ad(db, ad)
    analyze_ad(db, ad)
    assert ad.links == ["https://hidden.test/a", "https://shown.test/x"]


def test_a_collected_post_with_a_text_link_is_what_the_recheck_reads_and_adds_no_version(
    db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    html = (Path(__file__).parent / "fixtures" / "collectors" / "telegram_page1.html").read_text(encoding="utf-8")
    message = LexborHTMLParser(html).css_first('div.tgme_widget_message[data-post="zhk_alatau_demo/101"]')
    assert message is not None
    post = parse_message(message)
    assert post is not None and "смотрите здесь" in post.text
    account = telegram_account(db, world, "zhk_alatau_demo")
    ad = service.ingest_collected_post(db, account, post, capture=True)
    assert ad is not None

    monkeypatch.setattr(recheck, "ensure_public_url", lambda url: None)
    widget = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=html)))
    removed, widget_text = recheck.read_telegram_post(widget, "https://t.me/zhk_alatau_demo/101")

    assert removed is False and widget_text is not None
    assert record_version(db, ad, widget_text, AdVersionSource.recheck, datetime.now(UTC)) is None
    assert service.ingest_collected_post(db, account, post, capture=True) is None  # collected again
    assert db.scalars(select(AdPostVersion)).all() == []


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
    assert created == [ad.id] and ad.source_account_id == account.id
    assert account.last_error == "сбой" and account.last_collected_at is None


@pytest.mark.usefixtures("empty_registry")
def test_the_collector_decides_whether_pages_are_captured(
    db: Session, world: World, dispatched: list[tuple[int, bool, int | None]]
) -> None:
    collector = Scripted([collected(url="https://t.me/alatau_demo/1")], capture_urls=False)
    base.register(collector)
    telegram_account(db, world)

    service.run_collectors(db)

    ad = db.scalars(select(AdPost)).one()
    assert ad.capture_status is None and dispatched == [(ad.id, False, None)]

    collector.capture_urls = True
    collector.posts = [collected("alatau_demo/2", url="https://t.me/alatau_demo/2")]
    service.run_collectors(db)

    captured = db.scalars(select(AdPost).where(AdPost.external_id == "alatau_demo/2")).one()
    assert captured.capture_status is CaptureStatus.pending and dispatched[-1] == (captured.id, True, None)


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


def test_collect_source_task_collects_that_account_in_its_session(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[Session, int]] = []

    def collect_source(session: Session, source_id: int) -> list[int]:
        seen.append((session, source_id))
        return []

    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: SessionFactory(db))
    monkeypatch.setattr(tasks.service, "collect_source", collect_source)

    tasks.collect_source(5)

    assert seen == [(db, 5)]


# ---------------------------------------------------------------- one failing account does not stop the run


class PerAccount:
    """A collector that serves each handle its own posts; a handle in `errors` raises after its posts."""

    platform = Platform.telegram

    def __init__(
        self,
        posts: dict[str, list[CollectedPost]],
        errors: dict[str, Exception] | None = None,
        capture_urls: bool = False,
    ) -> None:
        self.posts = posts
        self.errors = errors or {}
        self.capture_urls = capture_urls

    def handles(self, account: SourceAccount) -> bool:
        return True

    def collect(self, account: SourceAccount, since: datetime, is_known: IsKnown) -> Iterator[CollectedPost]:
        for post in self.posts.get(account.handle, []):
            is_known(post.external_id)  # a collector reads the database, which opens a transaction
            yield post
        if account.handle in self.errors:
            raise self.errors[account.handle]


def dispatched_ids(dispatched: list[tuple[int, bool, int | None]]) -> list[int]:
    return [ad_post_id for ad_post_id, _, _ in dispatched]


UNEXPECTED = "Непредвиденная ошибка сбора, подробности в журнале сервера"


@pytest.mark.usefixtures("empty_registry")
def test_a_database_error_in_one_account_neither_aborts_the_run_nor_strands_the_saved_posts(
    db: Session, world: World, dispatched: list[tuple[int, bool, int | None]]
) -> None:
    base.register(
        PerAccount(
            {
                "good_one": [collected("good_one/1")],
                # The author does not fit the column: the INSERT fails, as with a NUL character or a race.
                "bad_channel": [collected("bad_channel/1"), collected("bad_channel/2", author="a" * 300)],
                "good_two": [collected("good_two/1")],
            }
        )
    )
    good_one, bad, good_two = (
        telegram_account(db, world, handle) for handle in ("good_one", "bad_channel", "good_two")
    )
    db.commit()

    created = service.run_collectors(db)

    ads = {ad.external_id: ad for ad in db.scalars(select(AdPost))}
    # The posts committed before the failure stay, and every saved post got its pipeline at once.
    assert sorted(ads, key=str) == ["bad_channel/1", "good_one/1", "good_two/1"]
    assert (
        created == dispatched_ids(dispatched) == [ads[key].id for key in ("good_one/1", "bad_channel/1", "good_two/1")]
    )
    assert bad.last_error == UNEXPECTED and bad.last_error_at is not None and bad.last_collected_at is None
    assert recipients(db, bad)
    for fine in (good_one, good_two):
        assert fine.last_error is None and fine.last_collected_at is not None


@pytest.mark.usefixtures("empty_registry")
def test_a_failure_while_recording_the_outcome_does_not_stop_the_run(
    db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    base.register(PerAccount({"after": [collected("after/1")]}, errors={"broken": CollectorError("сбой")}))
    broken = telegram_account(db, world, "broken")
    after = telegram_account(db, world, "after")
    db.commit()

    def refuse(session: Session, account: SourceAccount, error: str) -> None:
        raise RuntimeError("the database went away")

    monkeypatch.setattr(service, "_notify_collector_failed", refuse)

    service.run_collectors(db)

    assert db.scalars(select(AdPost.external_id)).all() == ["after/1"]
    assert after.last_collected_at is not None and broken.last_collected_at is None


# ---------------------------------------------------------------- the network stays out of transactions


@pytest.mark.usefixtures("empty_registry", "bucket", "dns")
def test_no_transaction_is_open_while_the_posts_are_read_stored_and_their_photos_downloaded(
    db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    base.register(
        PerAccount(
            {
                "alatau_demo": [
                    collected("alatau_demo/1", media_urls=[f"{CDN}/1.png"]),
                    collected("alatau_demo/2", media_urls=[f"{CDN}/2.png"]),
                ]
            }
        )
    )
    telegram_account(db, world)
    db.commit()
    open_when_stored: list[bool] = []
    open_when_downloaded: list[bool] = []
    original = service.ingest_collected_post

    def ingest(*args: Any, **kwargs: Any) -> AdPost | None:
        open_when_stored.append(db.in_transaction())
        return original(*args, **kwargs)

    def answer(request: httpx.Request) -> httpx.Response:
        open_when_downloaded.append(db.in_transaction())
        return photo(PNG_BYTES)

    monkeypatch.setattr(service, "ingest_collected_post", ingest)

    created = service.run_collectors(db, httpx.Client(transport=httpx.MockTransport(answer)))

    # The collector read the database (a transaction), yet the first post is stored in a transaction of its own, the
    # photos come after that post is committed, and the next post starts anew.
    assert open_when_stored == [False, False]
    assert open_when_downloaded == [False, False]
    assert [ad.ocr_status for ad in db.scalars(select(AdPost).order_by(AdPost.id))] == [OcrStatus.pending] * 2
    assert len(created) == 2


@pytest.mark.usefixtures("empty_registry", "bucket", "dns")
def test_a_failure_of_the_photos_leaves_the_post_which_still_gets_its_pipeline(
    db: Session, world: World, dispatched: list[tuple[int, bool, int | None]], monkeypatch: pytest.MonkeyPatch
) -> None:
    base.register(PerAccount({"alatau_demo": [collected("alatau_demo/1", media_urls=[f"{CDN}/1.png"])]}))
    account = telegram_account(db, world)
    db.commit()

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("the storage went away")

    monkeypatch.setattr(service.storage, "put_evidence", refuse)

    service.run_collectors(db, Media({"/1.png": photo(PNG_BYTES)}).client())

    ad = db.scalars(select(AdPost)).one()
    assert ad.ocr_status is None and dispatched == [(ad.id, False, None)]
    assert account.last_error is None and account.last_collected_at is not None


# ---------------------------------------------------------------- a pipeline that cannot be queued


@pytest.mark.usefixtures("empty_registry", "bucket", "dns")
def test_a_pipeline_that_cannot_be_queued_ends_the_pending_states_of_the_post(
    db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    base.register(
        PerAccount(
            {
                "alatau_demo": [
                    collected("alatau_demo/1", url="https://t.me/alatau_demo/1", media_urls=[f"{CDN}/1.png"])
                ]
            },
            capture_urls=True,
        )
    )
    telegram_account(db, world)
    db.commit()
    monkeypatch.setattr(service, "dispatch_pipeline", lambda *args, **kwargs: False)

    service.run_collectors(db, Media({"/1.png": photo(PNG_BYTES)}).client())

    ad = db.scalars(select(AdPost)).one()
    assert ad.capture_status is CaptureStatus.failed and ad.capture_error == "Не удалось поставить фиксацию в очередь"
    assert ad.ocr_status is OcrStatus.failed


# ---------------------------------------------------------------- one run per account


class Reentrant(Scripted):
    """While it collects an account, another run (the button, the schedule) asks for the same account."""

    def __init__(self, db: Session, posts: Iterable[CollectedPost] = ()) -> None:
        super().__init__(posts)
        self.db = db
        self.held: list[bool] = []
        self.second_run: list[int] | None = None

    def collect(self, account: SourceAccount, since: datetime, is_known: IsKnown) -> Iterator[CollectedPost]:
        self.held.append(collect_lock.is_held(account.id))
        if self.second_run is None:
            self.second_run = []
            self.second_run = service.collect_source(self.db, account.id)
        yield from super().collect(account, since, is_known)


@pytest.mark.usefixtures("empty_registry")
def test_an_account_is_not_collected_twice_at_once(db: Session, world: World, caplog: pytest.LogCaptureFixture) -> None:
    collector = Reentrant(db, [collected("alatau_demo/1")])
    base.register(collector)
    account = telegram_account(db, world)
    db.commit()

    with caplog.at_level(logging.INFO, logger="app.modules.ads.service"):
        created = service.collect_source(db, account.id)

    assert collector.calls == ["alatau_demo"]  # the second request did not reach the collector
    assert collector.second_run == [] and collector.held == [True]
    assert len(created) == 1 and db.scalars(select(AdPost)).one().external_id == "alatau_demo/1"
    assert f"Source account {account.id} is being collected by another run" in caplog.text
    assert account.last_error is None and account.last_collected_at is not None
    assert collect_lock.is_held(account.id) is False  # released at the end


@pytest.mark.usefixtures("empty_registry")
def test_the_lock_is_released_after_a_failure_and_bounds_a_run_in_time(db: Session, world: World) -> None:
    ttls: list[int] = []

    class Probe(Scripted):
        def collect(self, account: SourceAccount, since: datetime, is_known: IsKnown) -> Iterator[CollectedPost]:
            with lock_db() as locks:
                ttls.append(int(locks.ttl(f"{collect_lock.KEY_PREFIX}{account.id}")))
            return super().collect(account, since, is_known)

    base.register(Probe(error=RuntimeError("boom")))
    account = telegram_account(db, world)
    db.commit()

    service.collect_source(db, account.id)

    assert account.last_error == UNEXPECTED
    assert len(ttls) == 1 and 0 < ttls[0] <= collect_lock.LOCK_TTL_S
    assert collect_lock.is_held(account.id) is False


@pytest.mark.usefixtures("empty_registry")
def test_a_held_lock_skips_only_its_account(db: Session, world: World) -> None:
    collector = Scripted([collected("any/1")])
    base.register(collector)
    busy = telegram_account(db, world, "busy_demo")
    free = telegram_account(db, world, "free_demo")
    db.commit()
    with lock_db() as locks:
        locks.set(f"{collect_lock.KEY_PREFIX}{busy.id}", "another-run")

    service.run_collectors(db)

    assert collector.calls == ["free_demo"]
    assert busy.last_collected_at is None and busy.last_error is None
    assert free.last_collected_at is not None
    with lock_db() as locks:
        assert locks.get(f"{collect_lock.KEY_PREFIX}{busy.id}") == b"another-run"  # not ours to release


def test_a_run_whose_lock_expired_does_not_release_the_lock_of_the_next_run() -> None:
    key = f"{collect_lock.KEY_PREFIX}7"

    with collect_lock.hold(7) as acquired, lock_db() as locks:
        assert acquired is True
        locks.set(key, "next-run")  # the first one expired and another run took the account

    with lock_db() as locks:
        assert locks.get(key) == b"next-run"
    with collect_lock.hold(7) as second:
        assert second is False
