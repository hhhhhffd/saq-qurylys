"""Text recognition on the photos of a publication (SPEC 10.2)."""

import io
import logging
import re

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
