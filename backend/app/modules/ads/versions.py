"""Later texts of a publication (SPEC 10.6): the source was edited after the original was saved."""

import hashlib
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AdPost, AdPostVersion
from app.models.enums import AdOrigin, AdVersionSource
from app.modules.nlp.text import split_ocr

_SPACE = re.compile(r"\s+")
# Only a saved text that came from the source itself can be compared with what the source shows later: not the
# note of a citizen and not the words staff typed in.
SOURCE_TEXT_ORIGINS = frozenset({AdOrigin.capture, AdOrigin.collector})


def _comparable(text: str) -> str:
    return _SPACE.sub(" ", text).strip()


def record_version(
    session: Session,
    ad: AdPost,
    text: str,
    source: AdVersionSource,
    observed_at: datetime,
    evidence_id: int | None = None,
) -> AdPostVersion | None:
    """Store `text` as seen at the source when it differs (ignoring whitespace) from the latest known text: the
    last stored version, or else the saved original without its OCR part. Flushed, not committed.

    Returns the new version, or None when the text is unchanged or the post has no saved original to compare with.
    """
    if not ad.text:
        return None
    latest = session.scalar(
        select(AdPostVersion.text)
        .where(AdPostVersion.ad_post_id == ad.id)
        .order_by(AdPostVersion.observed_at.desc(), AdPostVersion.id.desc())
        .limit(1)
    )
    known = latest if latest is not None else split_ocr(ad.text)[0]
    if _comparable(text) == _comparable(known):
        return None
    version = AdPostVersion(
        ad_post_id=ad.id,
        text=text,
        text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        observed_at=observed_at,
        source=source,
        evidence_id=evidence_id,
    )
    session.add(version)
    session.flush()
    return version
