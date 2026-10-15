"""What the userbot stores, without Telegram: the decision to keep a message and the saving of the kept one."""

import logging
from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.collectors.base import CollectedPost
from app.collectors.media import MAX_PHOTO_BYTES, MAX_PHOTOS
from app.models import AdPost, Phrase, SourceAccount
from app.models.enums import CaptureStatus, EvidenceKind, OcrStatus, Platform
from app.modules.ads.service import dispatch_pipeline, ingest_collected_post, mark_capture_unqueued
from app.modules.nlp.text import find_matches
from app.storage import EvidenceLink
from app.uploads import PHOTO_TYPES, sniff_content_type

logger = logging.getLogger(__name__)


def external_id(username: str, message_id: int) -> str:
    """The same id the t.me/s collector gives, so a post is stored once whichever mechanism reads it."""
    return f"{username}/{message_id}".lower()


def is_stored(session: Session, username: str, message_id: int) -> bool:
    stmt = select(AdPost.id).where(
        AdPost.platform == Platform.telegram, AdPost.external_id == external_id(username, message_id)
    )
    return session.scalar(stmt) is not None


def load_phrases(session: Session) -> list[Phrase]:
    return list(session.scalars(select(Phrase).where(Phrase.is_active)))


def build_post(
    *,
    username: str,
    message_id: int,
    text: str,
    links: list[str],
    published_at: datetime,
    has_photo: bool,
    is_channel: bool,
    channel_title: str,
    phrases: Iterable[Phrase],
) -> CollectedPost | None:
    """The post to store for a message of a public chat, or None when the message is not kept.

    A broadcast channel is public by nature: every post is kept, signed with the channel's title. A group is kept
    only when the text hits the dictionary, and never with its author or its link: the public page of a message
    shows the member who wrote it.
    """
    if is_channel:
        if not text and not has_photo:
            return None
    elif not text or not find_matches(text, phrases):
        return None
    return CollectedPost(
        external_id=external_id(username, message_id),
        text=text,
        url=f"https://t.me/{username}/{message_id}" if is_channel else None,
        author=channel_title if is_channel else None,
        published_at=published_at,
        links=links,
    )


def _usable_photos(photos: Sequence[bytes]) -> list[tuple[bytes, str]]:
    usable: list[tuple[bytes, str]] = []
    for data in photos:
        content_type = sniff_content_type(data) if 0 < len(data) <= MAX_PHOTO_BYTES else None
        if content_type in PHOTO_TYPES:
            usable.append((data, content_type or ""))
    return usable[:MAX_PHOTOS]


def store_message(
    session: Session, account_id: int, post: CollectedPost, photos: Sequence[bytes], *, capture: bool
) -> int | None:
    """Store a kept message with its photos and queue its pipeline. Commits; returns the new post's id.

    A message that is stored already is not stored again (an edited text becomes a version); the result is None.
    """
    account = session.get(SourceAccount, account_id)
    if account is None:
        return None
    ad = ingest_collected_post(session, account, post, capture=capture)
    session.commit()
    if ad is None:
        return None
    ad_id, queued_capture = ad.id, ad.capture_status is CaptureStatus.pending
    usable = _usable_photos(photos)
    if usable:
        try:
            for data, content_type in usable:
                storage.put_evidence(
                    session, data, EvidenceKind.photo, content_type, link=EvidenceLink(ad_post_id=ad_id)
                )
            ad.ocr_status = OcrStatus.pending
            session.commit()
        except Exception:
            # The post is saved; it goes through the pipeline without its photos.
            logger.exception("The photos of ad_post %s were not stored", ad_id)
            session.rollback()
    if not dispatch_pipeline(ad_id, capture=queued_capture, requested_by=None):
        mark_capture_unqueued(session, ad)
    return ad_id
