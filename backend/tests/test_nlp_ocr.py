import io
import logging
import shutil
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytesseract
import pytest
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from app import storage
from app.config import get_settings
from app.models import AdPost, Evidence
from app.models.enums import EvidenceKind, OcrStatus
from app.modules.nlp import ocr, tasks
from app.modules.nlp.text import OCR_MARKER, split_ocr
from app.storage import EvidenceLink
from tests.conftest import PNG_BYTES, World
from tests.support_ads import add_ad

DEJAVU_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
)


def image_bytes(width: int = 300, height: int = 100, fmt: str = "PNG", **save_options: Any) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, fmt, **save_options)
    return buffer.getvalue()


def add_photo(db: Session, ad: AdPost, data: bytes) -> Evidence:
    return storage.put_evidence(db, data, EvidenceKind.photo, "image/png", link=EvidenceLink(ad_post_id=ad.id))


class FakeTesseract:
    """Stands in for `pytesseract.image_to_string`: answers with the given texts in order, one per photo."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *answers: str | Exception) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[Image.Image, str]] = []
        monkeypatch.setattr(pytesseract, "image_to_string", self)

    def __call__(self, image: Image.Image, lang: str, timeout: int) -> str:
        self.calls.append((image, lang))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def run_task(db: Session, monkeypatch: pytest.MonkeyPatch, ad_post_id: int) -> None:
    """Run the task in the test transaction; what was added so far is committed first (the task may roll back)."""
    db.commit()
    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: lambda: nullcontext(db))
    tasks.ocr(ad_post_id)


# ---------------------------------------------------------------- cleaning


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  БРОНЬ за 10%  \n\n\n\n Звоните 777 \x0c", "БРОНЬ за 10%\n\nЗвоните 777"),
        ("Первая\n\n~~ | \n\n— —\n\nВторая", "Первая\n\nВторая"),
        ("\n  \n", ""),
        ("---\n|\n", ""),
        ("Одна строка", "Одна строка"),
    ],
)
def test_clean_text(raw: str, expected: str) -> None:
    assert ocr.clean_text(raw) == expected


# ---------------------------------------------------------------- recognition


def test_text_of_all_photos_goes_after_the_marker_and_a_rerun_replaces_only_that_part(
    db: Session, world: World, bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    ad = add_ad(db, world.ust, "Квартиры в рассрочку", ocr_status=OcrStatus.pending)
    add_photo(db, ad, image_bytes(300, 100))
    add_photo(db, ad, image_bytes(1200, 400))
    fake = FakeTesseract(monkeypatch, " БРОНЬ за 10% \n\n\n~~\nПервый взнос", "Второе фото\n", "Новый текст\n", "")

    ocr.recognise_ad(db, ad)

    assert ad.text == f"Квартиры в рассрочку{OCR_MARKER}БРОНЬ за 10%\n\nПервый взнос\n\nВторое фото"
    assert ad.ocr_status is OcrStatus.done
    assert split_ocr(ad.text) == ("Квартиры в рассрочку", "БРОНЬ за 10%\n\nПервый взнос\n\nВторое фото")
    # Grayscale, upright; narrow photos are enlarged, wide ones are not.
    assert [(image.mode, image.size) for image, _ in fake.calls] == [("L", (600, 200)), ("L", (1200, 400))]
    assert {lang for _, lang in fake.calls} == {get_settings().ocr_languages}

    ocr.recognise_ad(db, ad)  # the second run reads only "Новый текст" and an empty answer
    assert ad.text == f"Квартиры в рассрочку{OCR_MARKER}Новый текст"
    assert ad.ocr_status is OcrStatus.done


def test_a_rerun_that_reads_nothing_drops_the_old_ocr_part(
    db: Session, world: World, bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    ad = add_ad(db, world.ust, f"Квартиры в рассрочку{OCR_MARKER}Старый текст")
    add_photo(db, ad, image_bytes())
    FakeTesseract(monkeypatch, "  ~~\n | \n")

    ocr.recognise_ad(db, ad)

    assert ad.text == "Квартиры в рассрочку"
    assert ad.ocr_status is OcrStatus.done


def test_a_post_without_text_gets_only_the_ocr_part(
    db: Session, world: World, bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    ad = add_ad(db, world.ust, None, ocr_status=OcrStatus.pending)
    add_photo(db, ad, image_bytes())
    FakeTesseract(monkeypatch, "Бронь")

    ocr.recognise_ad(db, ad)

    assert split_ocr(ad.text or "") == ("", "Бронь")


def test_a_post_without_text_stays_without_text_when_nothing_is_read(
    db: Session, world: World, bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    ad = add_ad(db, world.ust, None, ocr_status=OcrStatus.pending)
    add_photo(db, ad, image_bytes())
    FakeTesseract(monkeypatch, "")

    ocr.recognise_ad(db, ad)

    assert ad.text is None and ad.ocr_status is OcrStatus.done


def test_the_orientation_of_the_photo_is_applied_before_recognition(
    db: Session, world: World, bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # the photo must be rotated by 90 degrees to be upright
    ad = add_ad(db, world.ust)
    add_photo(db, ad, image_bytes(300, 100, "JPEG", exif=exif))
    fake = FakeTesseract(monkeypatch, "Бронь")

    ocr.recognise_ad(db, ad)

    assert fake.calls[0][0].size == (200, 600)  # turned upright (100x300), then enlarged


def test_screenshots_are_not_recognised(
    db: Session, world: World, bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    ad = add_ad(db, world.ust, "Текст", ocr_status=OcrStatus.pending)
    storage.put_evidence(
        db, image_bytes(), EvidenceKind.screenshot_png, "image/png", link=EvidenceLink(ad_post_id=ad.id)
    )
    FakeTesseract(monkeypatch)  # any call would run out of answers

    ocr.recognise_ad(db, ad)

    assert ad.text == "Текст" and ad.ocr_status is None


# ---------------------------------------------------------------- no work


def test_a_post_without_photos_keeps_a_null_status(db: Session, world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    FakeTesseract(monkeypatch)
    plain = add_ad(db, world.ust, "Текст")
    stale = add_ad(db, world.ust, "Текст", ocr_status=OcrStatus.pending)

    ocr.recognise_ad(db, plain)
    ocr.recognise_ad(db, stale)

    assert plain.ocr_status is None and plain.text == "Текст"
    assert stale.ocr_status is None  # the photos the creator waited for do not exist


def test_disabled_ocr_does_nothing(db: Session, world: World, bucket: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ocr_enabled", False)
    ad = add_ad(db, world.ust, "Текст", ocr_status=OcrStatus.pending)
    add_photo(db, ad, image_bytes())
    finished = add_ad(db, world.ust, f"Текст{OCR_MARKER}С фото", ocr_status=OcrStatus.done)
    add_photo(db, finished, image_bytes())
    FakeTesseract(monkeypatch)

    ocr.recognise_ad(db, ad)
    ocr.recognise_ad(db, finished)

    assert ad.text == "Текст" and ad.ocr_status is None
    assert finished.text == f"Текст{OCR_MARKER}С фото" and finished.ocr_status is OcrStatus.done


# ---------------------------------------------------------------- the task never raises


def test_task_stores_the_result(db: Session, world: World, bucket: str, monkeypatch: pytest.MonkeyPatch) -> None:
    ad = add_ad(db, world.ust, "Текст", ocr_status=OcrStatus.pending)
    add_photo(db, ad, image_bytes())
    FakeTesseract(monkeypatch, "Бронь за 10%")

    run_task(db, monkeypatch, ad.id)

    assert ad.text == f"Текст{OCR_MARKER}Бронь за 10%" and ad.ocr_status is OcrStatus.done


def test_a_missing_ad_is_skipped(
    db: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        run_task(db, monkeypatch, 2_000_000_000)
    assert "does not exist" in caplog.text


@pytest.mark.parametrize(
    "failure",
    [
        pytesseract.TesseractNotFoundError(),
        pytesseract.TesseractError(1, "Failed loading language 'kaz'"),
        RuntimeError("Tesseract process timeout"),
    ],
)
def test_tesseract_failure_is_recorded_and_not_raised(
    db: Session,
    world: World,
    bucket: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: Exception,
) -> None:
    ad = add_ad(db, world.ust, f"Текст{OCR_MARKER}Старое", ocr_status=OcrStatus.pending)
    add_photo(db, ad, image_bytes())
    FakeTesseract(monkeypatch, failure)

    with caplog.at_level(logging.ERROR):
        run_task(db, monkeypatch, ad.id)  # a raised exception would stop analyze, link and the LLM step

    assert ad.ocr_status is OcrStatus.failed
    assert ad.text == f"Текст{OCR_MARKER}Старое"
    assert f"recognition failed for ad_post {ad.id}" in caplog.text


def test_failure_when_no_photo_can_be_read(
    db: Session, world: World, bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    ad = add_ad(db, world.ust, "Текст", ocr_status=OcrStatus.pending)
    add_photo(db, ad, PNG_BYTES)  # a signature without an image
    FakeTesseract(monkeypatch)

    run_task(db, monkeypatch, ad.id)

    assert ad.ocr_status is OcrStatus.failed and ad.text == "Текст"


def test_a_broken_photo_does_not_spoil_the_others(
    db: Session, world: World, bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    ad = add_ad(db, world.ust, "Текст", ocr_status=OcrStatus.pending)
    add_photo(db, ad, PNG_BYTES)
    add_photo(db, ad, image_bytes())
    FakeTesseract(monkeypatch, "Бронь")

    run_task(db, monkeypatch, ad.id)

    assert ad.ocr_status is OcrStatus.done and ad.text == f"Текст{OCR_MARKER}Бронь"


# ---------------------------------------------------------------- real Tesseract


def test_real_tesseract_reads_cyrillic_text(db: Session, world: World, bucket: str) -> None:
    if shutil.which("tesseract") is None:
        pytest.skip("tesseract is not installed")
    font_path = next((path for path in DEJAVU_FONTS if Path(path).exists()), None)
    if font_path is None:
        pytest.skip("no Cyrillic-capable font (DejaVu) found")
    image = Image.new("RGB", (700, 160), "white")
    ImageDraw.Draw(image).text((24, 36), "БРОНЬ ЗА 10%", font=ImageFont.truetype(font_path, 64), fill="black")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    ad = add_ad(db, world.ust, "Квартиры", ocr_status=OcrStatus.pending)
    add_photo(db, ad, buffer.getvalue())

    ocr.recognise_ad(db, ad)

    own, recognised = split_ocr(ad.text or "")
    assert own == "Квартиры" and ad.ocr_status is OcrStatus.done
    assert recognised is not None
    words = recognised.upper().split()
    assert "БРОНЬ" in words and "ЗА" in words and any(word.startswith("10") for word in words)
