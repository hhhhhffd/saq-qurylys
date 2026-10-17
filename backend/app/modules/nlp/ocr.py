"""Text recognition on the photos of a publication (SPEC 10.2)."""

import io
import logging
import re
from dataclasses import dataclass

import pytesseract
from minio.error import S3Error
from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.config import get_settings
from app.models import AdPost, Evidence
from app.models.enums import EvidenceKind, OcrStatus
from app.modules.nlp.text import OCR_MARKER, split_ocr

logger = logging.getLogger(__name__)

# Tesseract reads small text badly: photos narrower than this are enlarged first.
UPSCALE_BELOW_WIDTH_PX = 1000
UPSCALE_FACTOR = 2
# One photo must not hold the queue forever.
TESSERACT_TIMEOUT_S = 60
_BLANK_RUNS = re.compile(r"\n{3,}")


class OcrError(Exception):
    """None of the photos of a publication could be read."""


def clean_text(raw: str) -> str:
    """Recognised text without lines made of noise (no letter or digit) and with blank lines collapsed."""
    lines = [line.strip() for line in raw.splitlines()]
    kept = [line for line in lines if not line or any(char.isalnum() for char in line)]
    return _BLANK_RUNS.sub("\n\n", "\n".join(kept)).strip()


def _prepare(data: bytes) -> Image.Image:
    """The photo as Tesseract likes it: upright, grayscale, not too small. Raises OSError for a broken image."""
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("L")
    if image.width < UPSCALE_BELOW_WIDTH_PX:
        image = image.resize((image.width * UPSCALE_FACTOR, image.height * UPSCALE_FACTOR), Image.Resampling.LANCZOS)
    return image


@dataclass(frozen=True)
class OcrResult:
    text: str
    # Mean confidence of the recognised words as a fraction (0..1); None when no word was recognised.
    confidence: float | None
    engine: str


def _engine_name() -> str:
    try:
        version = str(pytesseract.get_tesseract_version())
    except (OSError, pytesseract.TesseractError):
        # Only a label of the result: the version lookup must not fail a recognition that has succeeded.
        version = "unknown"
    return f"tesseract {version} {get_settings().ocr_languages}"


def ocr_image(data: bytes) -> OcrResult:
    """Recognise the text of one picture (a cut-out region): cleaned text and Tesseract's own confidence.

    One Tesseract call: the text is rebuilt from the word table, lines in reading order, blocks and paragraphs
    separated by a blank line. Raises OSError for a broken image and Tesseract's errors (missing binary, timeout).
    """
    settings = get_settings()
    table = pytesseract.image_to_data(
        _prepare(data), lang=settings.ocr_languages, timeout=TESSERACT_TIMEOUT_S, output_type=pytesseract.Output.DICT
    )
    lines: dict[tuple[int, int, int], list[str]] = {}
    confidences: list[float] = []
    for block, paragraph, line, word, conf in zip(
        table["block_num"], table["par_num"], table["line_num"], table["text"], table["conf"], strict=True
    ):
        word = str(word).strip()
        if not word or float(conf) < 0:
            continue
        lines.setdefault((block, paragraph, line), []).append(word)
        confidences.append(float(conf))
    parts: list[str] = []
    previous: tuple[int, int] | None = None
    for (block, paragraph, _line), words in lines.items():
        if previous is not None and previous != (block, paragraph):
            parts.append("")
        parts.append(" ".join(words))
        previous = (block, paragraph)
    confidence = sum(confidences) / len(confidences) / 100 if confidences else None
    return OcrResult(text=clean_text("\n".join(parts)), confidence=confidence, engine=_engine_name())


def _load(evidence: Evidence) -> bytes:
    return b"".join(storage.stream_object(storage.open_evidence(evidence)))


def recognise_ad(session: Session, ad: AdPost) -> None:
    """Read the photos of the publication and put the text after the OCR marker of `ad.text`.

    Sets `ocr_status`; raises when the photos cannot be recognised (Tesseract is missing or fails, no photo can be
    read), leaving the text as it was. Flushed, not committed.
    """
    photos = session.scalars(
        select(Evidence).where(Evidence.ad_post_id == ad.id, Evidence.kind == EvidenceKind.photo).order_by(Evidence.id)
    ).all()
    settings = get_settings()
    if not settings.ocr_enabled or not photos:
        # `pending` was set by whoever stored the photos; there is nothing to wait for.
        if ad.ocr_status is OcrStatus.pending:
            ad.ocr_status = None
        return

    texts: list[str] = []
    unreadable = 0
    for photo in photos:
        try:
            image = _prepare(_load(photo))
        except (S3Error, OSError, Image.DecompressionBombError) as exc:
            unreadable += 1
            logger.warning("nlp.ocr: photo (evidence %s) of ad_post %s cannot be read: %s", photo.id, ad.id, exc)
            continue
        text = clean_text(pytesseract.image_to_string(image, lang=settings.ocr_languages, timeout=TESSERACT_TIMEOUT_S))
        if text:
            texts.append(text)
    if unreadable == len(photos):
        raise OcrError(f"none of the {len(photos)} photos of ad_post {ad.id} could be read")

    own, previous = split_ocr(ad.text or "")
    if texts:
        ad.text = own + OCR_MARKER + "\n\n".join(texts)
    elif previous is not None:
        ad.text = own
    ad.ocr_status = OcrStatus.done
