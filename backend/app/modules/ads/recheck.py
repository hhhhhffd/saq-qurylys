"""Re-check of saved publications: has the source page been removed, and did its text change?"""

import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin

import httpx
from selectolax.lexbor import LexborHTMLParser
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import audit
from app.models import AdPost
from app.models.enums import AdStatus, AdVersionSource, CaptureStatus
from app.modules.ads.urls import UnsafeUrlError, ensure_public_url, telegram_embed_url
from app.modules.ads.versions import record_version
from app.modules.settings.service import load_settings

logger = logging.getLogger(__name__)

REMOVED_HTTP_STATUSES = frozenset({404, 410})
# Pages that answer 200 but say the publication is gone.
REMOVED_MARKERS = (
    "объявление не найдено",
    "объявление удалено",
    "объявление снято с публикации",
    "публикация удалена",
    "страница не найдена",
    "page not found",
    "post not found",
    "this page isn't available",
)
MAX_REDIRECTS = 5
MAX_BODY_BYTES = 200_000
BATCH_SIZE = 200
CHECK_TIMEOUT_S = 15


def fetch(client: httpx.Client, url: str) -> tuple[int, str]:
    """(final HTTP status, beginning of the body) following redirects by hand so that every hop is checked."""
    for _ in range(MAX_REDIRECTS + 1):
        ensure_public_url(url)
        with client.stream("GET", url) as response:
            if response.is_redirect and (location := response.headers.get("location")):
                try:
                    url = urljoin(url, location)
                except ValueError as exc:  # "Invalid IPv6 URL" in the Location header
                    raise UnsafeUrlError("Некорректный адрес перенаправления") from exc
                continue
            body = b""
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) >= MAX_BODY_BYTES:
                    break
            return response.status_code, body.decode(response.encoding or "utf-8", errors="replace")
    raise httpx.TooManyRedirects(f"more than {MAX_REDIRECTS} redirects")


def is_removed(status_code: int, body: str) -> bool:
    if status_code in REMOVED_HTTP_STATUSES:
        return True
    lowered = body.lower()
    return status_code == 200 and any(marker in lowered for marker in REMOVED_MARKERS)


def read_telegram_post(client: httpx.Client, url: str) -> tuple[bool, str | None]:
    """(removed, text) of a public Telegram post (`t.me/<channel>/<id>`) as its embed widget shows it now.

    The post page answers 200 with the channel card for a deleted post, while the widget says "Post not found".
    The text is read only from the widget's own message markup. Other URLs are not read: (False, None).
    """
    embed_url = telegram_embed_url(url)
    if embed_url is None:
        return False, None
    status_code, body = fetch(client, embed_url)
    if status_code != 200:
        return False, None
    page = LexborHTMLParser(body)
    if page.css_first("div.tgme_widget_message_error") is not None:
        return True, None
    message = page.css_first("div.tgme_widget_message_text")
    if message is None:
        return False, None
    for line_break in message.css("br"):
        line_break.replace_with("\n")
    return False, message.text().strip() or None


def recheck_due(session: Session, client: httpx.Client) -> list[int]:
    """Check the publications that were not checked for `recheck_after_days`; returns the ids of the objects
    whose publications turned out to be removed. The saved evidence is not touched; a text that differs from the
    saved one is stored as a later version (SPEC 10.6)."""
    now = datetime.now(UTC)
    threshold = now - timedelta(days=load_settings(session).recheck_after_days)
    last_check = func.coalesce(AdPost.last_checked_at, AdPost.captured_at, AdPost.created_at)
    due = (
        select(AdPost)
        .where(
            AdPost.url.isnot(None),
            AdPost.status != AdStatus.removed_saved,
            AdPost.removed_detected_at.is_(None),
            # A post whose capture is pending or failed has nothing saved yet.
            or_(AdPost.capture_status.is_(None), AdPost.capture_status == CaptureStatus.done),
            last_check < threshold,
        )
        .order_by(last_check)
        .limit(BATCH_SIZE)
    )
    removed_objects: list[int] = []
    for ad in session.scalars(due).all():
        if ad.url is None:
            continue
        removed = False
        text: str | None = None
        try:
            status_code, body = fetch(client, ad.url)
            removed = is_removed(status_code, body)
            if not removed:
                removed, text = read_telegram_post(client, ad.url)
        except Exception:
            # Inconclusive, and one bad URL must not stop the run: the post is looked at again after the next
            # interval, not on every run.
            logger.warning("Re-check of ad_post %s failed", ad.id, exc_info=True)
            status_code = 0
        ad.last_checked_at = now
        if text is not None:
            record_version(session, ad, text, AdVersionSource.recheck, now)
        if removed:
            before = audit.snapshot(ad)
            # The removal does not confirm a link nobody confirmed: such a post stays in `verification`, out of
            # the score (OPEN_QUESTIONS 27, 29). `removed_detected_at` is what says it is gone.
            if ad.status is not AdStatus.verification:
                ad.status = AdStatus.removed_saved
            ad.removed_detected_at = now
            audit.record(
                session,
                None,
                "ad.removed_detected",
                "ad_post",
                ad.id,
                before,
                {**audit.snapshot(ad), "http_status": status_code},
            )
            if ad.object_id is not None:
                removed_objects.append(ad.object_id)
        session.commit()
    return removed_objects
