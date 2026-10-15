"""Where versions of a publication come from (recapture, re-check of a Telegram post) and how the ad card shows them."""

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import storage
from app.models import AdPost, AdPostVersion, Evidence
from app.models.enums import AdOrigin, AdStatus, AdVersionSource, CaptureStatus, EvidenceKind, Platform
from app.modules.ads import capture, recheck
from app.modules.ads.urls import UnsafeUrlError
from app.modules.ads.versions import record_version
from app.modules.nlp.text import OCR_MARKER, split_ocr
from app.storage import EvidenceLink
from tests.conftest import PNG_BYTES, World, auth, make_object
from tests.support_ads import add_ad

NOW = datetime(2026, 10, 13, 12, tzinfo=UTC)
ORIGINAL = "🏠 Старт продаж\n\nБронь за 10% до конца недели"
EDITED = "🏠 Старт продаж\n\nСкоро, подробности в директ"
POST_URL = "https://t.me/alatau_news/42"


def versions_of(db: Session, ad: AdPost) -> list[AdPostVersion]:
    return list(db.scalars(select(AdPostVersion).where(AdPostVersion.ad_post_id == ad.id).order_by(AdPostVersion.id)))


def test_stored_versions_cannot_be_rewritten_through_the_orm(db: Session, world: World) -> None:
    ad = add_ad(db, world.ust, ORIGINAL)
    version = record_version(db, ad, EDITED, AdVersionSource.recheck, NOW)
    assert version is not None

    version.text = "forged"
    with pytest.raises(IntegrityError, match="append-only"), db.begin_nested():
        db.flush()


# ---------------------------------------------------------------- recapture


def recapture(db: Session, world: World, page_text: str, text: str = ORIGINAL, **fields: Any) -> AdPost:
    """A publication with the saved `text` whose capture is pending is captured; the page says `page_text`."""
    values: dict[str, Any] = {
        "platform": Platform.telegram,
        "url": POST_URL,
        "capture_status": CaptureStatus.pending,
        "origin": AdOrigin.capture,
    }
    ad = add_ad(db, world.ust, text, **{**values, **fields})
    page = capture.PageCapture(png=PNG_BYTES, mhtml=b"From: x", final_url=POST_URL, text=page_text, published_at=None)
    capture.capture_ad(db, ad.id, None, page_capture=lambda url: page)
    return ad


def test_recapture_keeps_the_original_and_records_the_changed_text_as_a_version(
    db: Session, world: World, bucket: str
) -> None:
    ad = recapture(db, world, EDITED)

    assert ad.capture_status is CaptureStatus.done and ad.text == ORIGINAL
    [version] = versions_of(db, ad)
    screenshot = db.scalars(
        select(Evidence).where(Evidence.ad_post_id == ad.id, Evidence.kind == EvidenceKind.screenshot_png)
    ).one()
    assert version.text == EDITED and version.source is AdVersionSource.capture
    assert version.text_sha256 == hashlib.sha256(EDITED.encode()).hexdigest()
    assert version.evidence_id == screenshot.id
    assert ad.captured_at is not None and version.observed_at == ad.captured_at


def test_recapture_of_an_unchanged_text_records_nothing(db: Session, world: World, bucket: str) -> None:
    ad = recapture(db, world, "🏠 Старт продаж\nБронь   за 10% до конца недели ")  # only the whitespace differs
    assert ad.capture_status is CaptureStatus.done and versions_of(db, ad) == []


def test_first_capture_of_a_post_without_text_fills_the_original_and_is_no_version(
    db: Session, world: World, bucket: str
) -> None:
    ad = add_ad(db, world.ust, None, platform=Platform.telegram, url=POST_URL, capture_status=CaptureStatus.pending)
    page = capture.PageCapture(png=PNG_BYTES, mhtml=b"From: x", final_url=POST_URL, text=EDITED, published_at=None)

    capture.capture_ad(db, ad.id, None, page_capture=lambda url: page)

    assert ad.text == EDITED and versions_of(db, ad) == []


def test_first_capture_cannot_smuggle_the_ocr_marker_into_the_text(db: Session, world: World, bucket: str) -> None:
    """A page that carries the marker would pass the words after it for text read from the photos (SPEC 10.2)."""
    ad = add_ad(db, world.ust, None, platform=Platform.telegram, url=POST_URL, capture_status=CaptureStatus.pending)
    page_text = f"Старт продаж{OCR_MARKER}бронь за 10%"
    page = capture.PageCapture(png=PNG_BYTES, mhtml=b"From: x", final_url=POST_URL, text=page_text, published_at=None)

    capture.capture_ad(db, ad.id, None, page_capture=lambda url: page)

    assert ad.text == "Старт продаж\n\nбронь за 10%" and split_ocr(ad.text or "")[1] is None


def test_recapture_of_a_collected_post_is_compared_too(db: Session, world: World, bucket: str) -> None:
    ad = recapture(db, world, EDITED, origin=AdOrigin.collector)
    assert [version.text for version in versions_of(db, ad)] == [EDITED]


@pytest.mark.parametrize(
    "fields",
    [
        {"platform": Platform.website},  # the text of a whole page: menus and counters change on their own
        {"origin": AdOrigin.citizen},  # the note of a citizen is not the text of the post
        {"origin": AdOrigin.manual},  # nor are the words staff typed in
        {"text": f"{OCR_MARKER}Бронь на фото"},  # nothing but the text read from the photos is saved
    ],
)
def test_texts_that_cannot_be_compared_with_the_page_are_not_versions(
    db: Session, world: World, bucket: str, fields: dict[str, Any]
) -> None:
    ad = recapture(db, world, EDITED, **fields)
    assert ad.capture_status is CaptureStatus.done and versions_of(db, ad) == []


def test_failed_capture_records_no_version(db: Session, world: World) -> None:
    def failing(url: str) -> capture.PageCapture:
        raise capture.CaptureError("HTTP 404")

    ad = add_ad(db, world.ust, ORIGINAL, platform=Platform.telegram, url=POST_URL, capture_status=CaptureStatus.pending)
    capture.capture_ad(db, ad.id, None, page_capture=failing)
    assert ad.capture_status is CaptureStatus.failed and versions_of(db, ad) == []


# ---------------------------------------------------------------- re-check of a Telegram post

# Reduced copies of what the embed widget of t.me answers (checked against a public post, 2026-10-13).
WIDGET = (
    '<html><body><div class="tgme_widget_message_wrap"><div class="tgme_widget_message">'
    '<div class="tgme_widget_message_text js-message_text" dir="auto">'
    '<tg-emoji emoji-id="1"><i class="emoji"><b>🏠</b></i></tg-emoji> Старт продаж<br/><br/>'
    "Скоро, подробности в директ</div></div></div></body></html>"
)
WIDGET_WITHOUT_TEXT = (
    '<html><body><div class="tgme_widget_message"><a class="tgme_widget_message_photo_wrap"></a></div></body></html>'
)
WIDGET_POST_NOT_FOUND = (
    '<html><body><div class="tgme_widget_message err_message">'
    '<div class="tgme_widget_message_error" dir="auto">Post not found</div></div></body></html>'
)
CHANNEL_CARD = "<html><body><div class='tgme_page'>Канал застройщика</div></body></html>"


@pytest.fixture(autouse=True)
def no_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recheck, "ensure_public_url", lambda url: None)


def widget_handler(widget: str, requested: list[httpx.URL] | None = None) -> Callable[[httpx.Request], httpx.Response]:
    """The post page answers like the channel card, the embed widget (`?embed=1`) shows the post."""

    def handler(request: httpx.Request) -> httpx.Response:
        if requested is not None:
            requested.append(request.url)
        return httpx.Response(200, text=widget if request.url.params.get("embed") == "1" else CHANNEL_CARD)

    return handler


def due_post(db: Session, world: World, text: str = ORIGINAL, **fields: Any) -> AdPost:
    values: dict[str, Any] = {
        "platform": Platform.telegram,
        "url": POST_URL,
        "capture_status": CaptureStatus.done,
        "last_checked_at": datetime.now(UTC) - timedelta(days=4),
        "origin": AdOrigin.capture,
    }
    return add_ad(db, world.ust, text, **{**values, **fields})


def run_recheck(db: Session, handler: Callable[[httpx.Request], httpx.Response]) -> list[int]:
    return recheck.recheck_due(db, httpx.Client(transport=httpx.MockTransport(handler)))


def test_recheck_stores_the_text_a_telegram_post_shows_now_as_a_version(db: Session, world: World) -> None:
    ad = due_post(db, world)
    requested: list[httpx.URL] = []

    assert run_recheck(db, widget_handler(WIDGET, requested)) == []

    [version] = versions_of(db, ad)
    assert version.text == EDITED  # <br/> are line breaks, the emoji is part of the text
    assert version.source is AdVersionSource.recheck and version.evidence_id is None
    assert version.text_sha256 == hashlib.sha256(EDITED.encode()).hexdigest()
    assert version.observed_at == ad.last_checked_at
    assert ad.text == ORIGINAL and ad.status is AdStatus.captured and ad.removed_detected_at is None
    assert [url.path for url in requested] == ["/alatau_news/42", "/alatau_news/42"]
    assert [url.params.get("embed") for url in requested] == [None, "1"]


@pytest.mark.parametrize("origin", [AdOrigin.citizen, AdOrigin.manual])
def test_recheck_does_not_compare_a_note_with_the_post(db: Session, world: World, origin: AdOrigin) -> None:
    """Review repro: a citizen's own words about the post are not an earlier version of the post."""
    ad = due_post(db, world, "Видел эту рекламу, похоже на мошенников", origin=origin)

    run_recheck(db, widget_handler(WIDGET))

    assert versions_of(db, ad) == [] and ad.last_checked_at is not None


def test_recheck_compares_a_collected_post_too(db: Session, world: World) -> None:
    ad = due_post(db, world, origin=AdOrigin.collector)
    run_recheck(db, widget_handler(WIDGET))
    assert [version.text for version in versions_of(db, ad)] == [EDITED]


def test_recheck_of_an_unchanged_telegram_post_records_nothing(db: Session, world: World) -> None:
    ad = due_post(db, world, text="🏠 Старт продаж Скоро,  подробности в директ")  # the same up to whitespace
    run_recheck(db, widget_handler(WIDGET))
    assert versions_of(db, ad) == []


def test_each_recheck_compares_with_the_latest_version(db: Session, world: World) -> None:
    ad = due_post(db, world)
    run_recheck(db, widget_handler(WIDGET))
    ad.last_checked_at = datetime.now(UTC) - timedelta(days=4)
    run_recheck(db, widget_handler(WIDGET))  # the same edit seen again
    assert [v.text for v in versions_of(db, ad)] == [EDITED]

    ad.last_checked_at = datetime.now(UTC) - timedelta(days=4)
    run_recheck(db, widget_handler(WIDGET.replace("Скоро, подробности в директ", "Продажи закрыты")))
    assert [v.text for v in versions_of(db, ad)] == [EDITED, "🏠 Старт продаж\n\nПродажи закрыты"]


def test_recheck_reads_nothing_when_the_widget_has_no_message_text(db: Session, world: World) -> None:
    ad = due_post(db, world)
    assert run_recheck(db, widget_handler(WIDGET_WITHOUT_TEXT)) == []
    assert versions_of(db, ad) == [] and ad.status is AdStatus.captured and ad.last_checked_at is not None


def test_recheck_marks_a_telegram_post_removed_when_the_widget_cannot_find_it(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    ad = due_post(db, world, object_id=obj.id)

    assert run_recheck(db, widget_handler(WIDGET_POST_NOT_FOUND)) == [obj.id]

    assert ad.status is AdStatus.removed_saved and ad.removed_detected_at is not None
    assert ad.text == ORIGINAL and versions_of(db, ad) == []


def test_recheck_ignores_an_unusable_widget_answer(db: Session, world: World) -> None:
    ad = due_post(db, world)
    assert run_recheck(db, lambda request: httpx.Response(429 if request.url.params.get("embed") else 200)) == []
    assert versions_of(db, ad) == [] and ad.status is AdStatus.captured


def test_recheck_does_not_read_text_of_other_platforms_or_feeds(db: Session, world: World) -> None:
    other = due_post(db, world, url="https://alatau.test/post/1", platform=Platform.website)
    feed = due_post(db, world, url="https://t.me/s/alatau_news")  # a feed, not a post
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, text="<p>Совсем другой текст страницы</p>")

    run_recheck(db, handler)

    assert sorted(requested) == ["https://alatau.test/post/1", "https://t.me/s/alatau_news"]
    assert versions_of(db, other) == [] and versions_of(db, feed) == []


def test_recheck_checks_every_hop_of_the_widget_request(
    db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def guard(url: str) -> None:
        if "internal" in url:
            raise UnsafeUrlError("internal")

    monkeypatch.setattr(recheck, "ensure_public_url", guard)
    ad = due_post(db, world)
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fetched.append(str(request.url))
        if request.url.params.get("embed"):
            return httpx.Response(302, headers={"location": "http://internal.test/secret"})
        return httpx.Response(200, text=CHANNEL_CARD)

    assert run_recheck(db, handler) == []

    assert fetched == [POST_URL, f"{POST_URL}?embed=1&mode=tme"]
    assert versions_of(db, ad) == [] and ad.status is AdStatus.captured  # inconclusive, not removed
    assert ad.last_checked_at is not None and ad.last_checked_at > datetime.now(UTC) - timedelta(minutes=1)


# ---------------------------------------------------------------- the ad card


def test_ad_detail_gives_the_original_its_proof_and_the_later_versions(
    client: TestClient, db: Session, world: World, bucket: str
) -> None:
    captured_at = NOW - timedelta(days=2)
    ad = add_ad(db, world.ust, ORIGINAL, captured_at=captured_at, platform=Platform.telegram)
    link = EvidenceLink(ad_post_id=ad.id)
    page = storage.put_evidence(db, b"From: x", EvidenceKind.archive_mhtml, "multipart/related", link=link)
    first = storage.put_evidence(db, PNG_BYTES, EvidenceKind.screenshot_png, "image/png", link=link)
    later = storage.put_evidence(db, PNG_BYTES + b"1", EvidenceKind.screenshot_png, "image/png", link=link)
    edited = record_version(db, ad, EDITED, AdVersionSource.capture, captured_at + timedelta(hours=1), later.id)
    closed = record_version(db, ad, "Продажи закрыты", AdVersionSource.recheck, captured_at + timedelta(hours=2))
    assert edited is not None and closed is not None

    body = client.get(f"/api/v1/ads/{ad.id}", headers=auth(world.users["mio_ust"])).json()

    assert body["text"] == ORIGINAL
    assert body["versions"] == [
        {
            "id": edited.id,
            "text": EDITED,
            "text_sha256": hashlib.sha256(EDITED.encode()).hexdigest(),
            "observed_at": "2026-10-11T13:00:00Z",
            "source": "capture",
            "evidence_id": later.id,
        },
        {
            "id": closed.id,
            "text": "Продажи закрыты",
            "text_sha256": hashlib.sha256("Продажи закрыты".encode()).hexdigest(),
            "observed_at": "2026-10-11T14:00:00Z",
            "source": "recheck",
            "evidence_id": None,
        },
    ]
    assert body["original_captured_at"] == "2026-10-11T12:00:00Z"
    assert page.id < first.id < later.id
    assert body["original_evidence"]["id"] == first.id and body["original_evidence"]["kind"] == "screenshot_png"
    assert body["original_evidence"]["sha256"] == hashlib.sha256(PNG_BYTES).hexdigest()
    assert body["original_evidence"]["has_tsa_token"] is False
    assert [item["id"] for item in body["evidence"]] == [page.id, first.id, later.id]


def test_ad_detail_of_an_unchanged_post_without_a_capture(client: TestClient, db: Session, world: World) -> None:
    ad = add_ad(db, world.ust, ORIGINAL)  # entered by hand: never captured, no screenshot

    body = client.get(f"/api/v1/ads/{ad.id}", headers=auth(world.users["mio_ust"])).json()

    assert body["versions"] == [] and body["original_evidence"] is None
    assert body["captured_at"] is None
    assert datetime.fromisoformat(body["original_captured_at"]) == ad.created_at
