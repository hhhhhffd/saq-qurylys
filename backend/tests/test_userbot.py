"""The Telegram userbot without Telegram: which messages are kept, how they are stored, and the rules around it."""

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import collectors
from app.collectors import base
from app.collectors.base import CollectedPost
from app.collectors.telegram import TelegramCollector
from app.config import Settings
from app.models import AdPost, Evidence, Phrase, SourceAccount
from app.models.enums import AdOrigin, CaptureStatus, EvidenceKind, OcrStatus, PhraseCategory, Platform
from app.userbot import service
from tests.conftest import PNG_BYTES, World
from tests.test_collectors import settings_with

PUBLISHED = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
PHRASES = [Phrase(category=PhraseCategory.booking, text="бронь", variants=[], weight=10, is_active=True)]


def build(*, is_channel: bool, text: str = "Бронь квартир открыта", has_photo: bool = False) -> CollectedPost | None:
    return service.build_post(
        username="Alatau_Demo",
        message_id=7,
        text=text,
        links=["https://example.kz/a"],
        published_at=PUBLISHED,
        has_photo=has_photo,
        is_channel=is_channel,
        channel_title="Alatau",
        phrases=PHRASES,
    )


@pytest.fixture
def pipelines(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, bool, int | None]]:
    queued: list[tuple[int, bool, int | None]] = []

    def record(ad_post_id: int, *, capture: bool, requested_by: int | None) -> bool:
        queued.append((ad_post_id, capture, requested_by))
        return True

    monkeypatch.setattr(service, "dispatch_pipeline", record)
    return queued


@pytest.fixture
def source(db: Session, world: World) -> SourceAccount:
    account = SourceAccount(platform=Platform.telegram, handle="alatau_demo", territory_id=world.ust.id)
    db.add(account)
    db.flush()
    return account


def test_channel_post_is_kept_with_title_and_url() -> None:
    post = build(is_channel=True, text="Новости без слов из словаря")

    assert post == CollectedPost(
        external_id="alatau_demo/7",
        text="Новости без слов из словаря",
        url="https://t.me/Alatau_Demo/7",
        author="Alatau",
        published_at=PUBLISHED,
        links=["https://example.kz/a"],
    )


def test_channel_message_without_text_and_photo_is_skipped() -> None:
    assert build(is_channel=True, text="") is None
    assert build(is_channel=True, text="", has_photo=True) is not None


def test_group_message_is_kept_only_on_a_dictionary_hit_and_without_the_member() -> None:
    post = build(is_channel=False)

    assert post is not None
    assert post.author is None and post.url is None
    assert build(is_channel=False, text="Продаю велосипед") is None
    assert build(is_channel=False, text="", has_photo=True) is None


def test_store_message_saves_the_post_photo_and_queues_the_pipeline(
    db: Session, bucket: str, source: SourceAccount, pipelines: list[tuple[int, bool, int | None]]
) -> None:
    post = build(is_channel=True)
    assert post is not None

    ad_id = service.store_message(db, source.id, post, [PNG_BYTES, b"not an image"], capture=True)

    assert ad_id is not None
    ad = db.get(AdPost, ad_id)
    assert ad is not None
    assert ad.origin is AdOrigin.collector and ad.platform is Platform.telegram
    assert ad.external_id == "alatau_demo/7" and ad.capture_status is CaptureStatus.pending
    assert ad.ocr_status is OcrStatus.pending
    evidence = db.scalars(select(Evidence).where(Evidence.ad_post_id == ad_id)).all()
    assert [item.kind for item in evidence] == [EvidenceKind.photo]
    assert pipelines == [(ad_id, True, None)]
    assert service.is_stored(db, "ALATAU_demo", 7)


def test_stored_message_is_not_stored_again(
    db: Session, source: SourceAccount, pipelines: list[tuple[int, bool, int | None]]
) -> None:
    post = build(is_channel=False)
    assert post is not None

    assert service.store_message(db, source.id, post, [], capture=False) is not None
    assert service.store_message(db, source.id, post, [], capture=False) is None

    assert len(pipelines) == 1
    assert pipelines[0][1] is False


def test_userbot_replaces_the_web_preview_collector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base, "_registry", {})
    client = httpx.Client()
    credentials = {"telegram_api_id": 12345, "telegram_api_hash": "hash"}

    assert collectors.register_enabled(settings_with(collect_telegram_enabled=True, **credentials), client) == []

    # Credentials without the flag, or the flag without credentials: the web preview collector works as before.
    assert settings_with(**credentials).userbot_configured is False
    assert settings_with(collect_telegram_enabled=True).userbot_configured is False
    registered = collectors.register_enabled(settings_with(collect_telegram_enabled=True), client)
    assert registered == [Platform.telegram]
    assert isinstance(base.get_collector(Platform.telegram), TelegramCollector)


def test_empty_api_id_in_the_environment_means_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "")

    settings = Settings()

    assert settings.telegram_api_id == 0 and settings.userbot_configured is False
