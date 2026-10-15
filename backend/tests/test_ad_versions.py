import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.enums import AdVersionSource
from app.modules.ads.versions import record_version
from app.modules.nlp.text import OCR_MARKER, split_ocr
from tests.conftest import World
from tests.support_ads import add_ad

NOW = datetime(2026, 10, 13, 12, tzinfo=UTC)


def test_an_unchanged_text_is_not_a_version_whitespace_and_ocr_part_aside(db: Session, world: World) -> None:
    ad = add_ad(db, world.ust, f"Бронь  за 10%\nзвоните{OCR_MARKER}БРОНЬ 10%")
    assert record_version(db, ad, "Бронь за 10% звоните", AdVersionSource.recheck, NOW) is None


def test_each_change_is_compared_with_the_latest_version(db: Session, world: World) -> None:
    ad = add_ad(db, world.ust, "Бронь за 10%, звоните")

    first = record_version(db, ad, "Скоро старт продаж, звоните", AdVersionSource.collector, NOW)
    assert first is not None
    assert first.text_sha256 == hashlib.sha256("Скоро старт продаж, звоните".encode()).hexdigest()
    assert record_version(db, ad, "Скоро старт продаж, звоните", AdVersionSource.collector, NOW) is None
    second = record_version(db, ad, "Продажи закрыты", AdVersionSource.recheck, NOW + timedelta(hours=2))
    assert second is not None and second.id != first.id


def test_a_post_without_saved_text_has_nothing_to_compare(db: Session, world: World) -> None:
    ad = add_ad(db, world.ust, None)
    assert record_version(db, ad, "Бронь за 10%", AdVersionSource.capture, NOW) is None


def test_split_ocr() -> None:
    assert split_ocr("Текст") == ("Текст", None)
    assert split_ocr(f"Текст{OCR_MARKER}С фото") == ("Текст", "С фото")
