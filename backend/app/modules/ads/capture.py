"""Evidence capture of a publication by its URL: full-page PNG and MHTML snapshot from headless Chromium."""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from playwright.sync_api import BrowserContext, Page, Response, Route, ViewportSize, sync_playwright
from playwright.sync_api import Error as PlaywrightError
from sqlalchemy.orm import Session

from app import storage
from app.models import AdPost, Notification
from app.models.enums import AdVersionSource, CaptureStatus, EvidenceKind, NotificationKind, Platform
from app.modules.ads.urls import UnsafeUrlError, detect_platform, ensure_public_url, telegram_embed_url
from app.modules.ads.versions import SOURCE_TEXT_ORIGINS, record_version
from app.modules.nlp.text import OCR_MARKER, split_ocr
from app.storage import EvidenceLink

logger = logging.getLogger(__name__)

VIEWPORT: ViewportSize = {"width": 1366, "height": 900}
# Fixed on purpose: the same page is rendered the same way on every capture.
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
CAPTURE_TIMEOUT_S = 45
NETWORK_IDLE_TIMEOUT_S = 8
MAX_TEXT_CHARS = 20_000
MIN_BODY_CHARS = 40
MAX_ERROR_CHARS = 500
# Their pages carry the caption of the post in the description; Telegram posts come from the embed widget.
_CAPTION_IN_DESCRIPTION = frozenset({Platform.instagram, Platform.tiktok})
# Platforms whose captured text is the post itself. On other pages it is the whole page, with menus and counters
# that change on their own, so it cannot be compared with the saved text.
_POST_TEXT_PLATFORMS = _CAPTION_IN_DESCRIPTION | {Platform.telegram}

# `widget`: the page is the embed widget of a single Telegram post, whose message and time are the post's own.
_EXTRACT_SCRIPT = """
(widget) => {
  const meta = (selector) => (document.querySelector(selector)?.getAttribute('content') ?? '').trim();
  const root = document.querySelector('article, [role="article"], main') ?? document.body;
  const message = widget ? document.querySelector('.tgme_widget_message_text') : null;
  const time = widget ? document.querySelector('.tgme_widget_message time[datetime]') : null;
  return {
    description: meta('meta[property="og:description"]') || meta('meta[name="description"]'),
    body: (root?.innerText ?? '').trim(),
    message: (message?.innerText ?? '').trim(),
    published: meta('meta[property="article:published_time"]') || (time?.getAttribute('datetime') ?? ''),
  };
}
"""


class CaptureError(Exception):
    """The page could not be captured."""


@dataclass(frozen=True)
class PageCapture:
    png: bytes
    mhtml: bytes
    final_url: str
    text: str
    published_at: datetime | None


def _clean_text(value: str) -> str:
    value = re.sub(r"[ \t\r\f\v ]+", " ", value)
    value = re.sub(r"\n\s*\n+", "\n\n", value)
    return value.strip()[:MAX_TEXT_CHARS]


def _publication_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _choose_text(info: dict[str, str], platform: Platform) -> str:
    """The text of the publication: the caption on Instagram and TikTok, the main text of the page elsewhere."""
    if info["message"]:
        return info["message"]
    description, body = info["description"], info["body"]
    if platform in _CAPTION_IN_DESCRIPTION:
        return description or body
    return body if len(body) >= MIN_BODY_CHARS or len(body) >= len(description) else description


class _RequestGuard:
    """Keeps the browser away from non-public addresses: every request is checked, every redirect hop, in every
    frame and worker of the page.

    Playwright routes only see the first URL of a redirect chain (its follow-up requests are not routed, also
    after `route.fulfill` of a 3xx), so the page is also watched through the DevTools `Fetch` domain, which
    pauses every hop. Nothing is cached: DNS answers can change between two requests.
    """

    def __init__(self) -> None:
        self.refusal: str | None = None

    def check(self, url: str) -> bool:
        if url.startswith(("data:", "blob:", "about:")):
            return True
        try:
            ensure_public_url(url)
        except UnsafeUrlError as exc:
            logger.warning("Capture: blocked a request to a non-public address: %s", url)
            self.refusal = self.refusal or str(exc)
            return False
        return True

    def route(self, route: Route) -> None:
        """First hop of every request of the context (also of pop-ups, which have no DevTools guard)."""
        if self.check(route.request.url):
            route.continue_()
        else:
            route.abort("blockedbyclient")

    def watch(self, context: BrowserContext, page: Page) -> None:
        cdp = context.new_cdp_session(page)

        def on_paused(params: dict[str, Any]) -> None:
            try:
                allowed = self.check(params["request"]["url"])
            except Exception:
                logger.exception("Capture: could not check a request, blocking it")
                allowed = False
            if allowed:
                cdp.send("Fetch.continueRequest", {"requestId": params["requestId"]})
            else:
                cdp.send("Fetch.failRequest", {"requestId": params["requestId"], "errorReason": "BlockedByClient"})

        cdp.on("Fetch.requestPaused", on_paused)
        cdp.send("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})


def _verify_public_chain(response: Response | None, page_url: str) -> None:
    """Refuse the capture when any hop of the navigation, or the page it ended on, is not public."""
    request = response.request if response is not None else None
    while request is not None:
        ensure_public_url(request.url)
        request = request.redirected_from
    ensure_public_url(page_url)


def _goto(page: Page, url: str, guard: _RequestGuard) -> Response | None:
    try:
        response = page.goto(url, wait_until="domcontentloaded")
    except PlaywrightError as exc:
        if guard.refusal:
            raise UnsafeUrlError(guard.refusal) from exc
        raise
    _verify_public_chain(response, page.url)
    return response


def capture_page(url: str) -> PageCapture:
    """Open the URL in headless Chromium and take the evidence. Raises CaptureError."""
    platform = detect_platform(url)
    timeout_ms = CAPTURE_TIMEOUT_S * 1000
    try:
        ensure_public_url(url)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--disable-dev-shm-usage"])
            try:
                context = browser.new_context(
                    viewport=VIEWPORT, user_agent=USER_AGENT, locale="ru-RU", service_workers="block"
                )
                context.set_default_timeout(timeout_ms)
                guard = _RequestGuard()
                context.route("**/*", guard.route)
                context.route_web_socket(
                    "**/*", lambda socket: None
                )  # never connected to the server: a capture needs no sockets
                page = context.new_page()
                page.on("popup", lambda popup: popup.close())  # nor pop-ups
                guard.watch(context, page)
                response = _goto(page, url, guard)
                if response is not None and response.status >= 400:
                    raise CaptureError(f"HTTP {response.status}")
                try:
                    page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_S * 1000)
                except PlaywrightError:
                    logger.info("Capture: %s did not become idle, taking the snapshot anyway", url)
                png = page.screenshot(full_page=True, type="png", animations="disabled")
                snapshot: dict[str, Any] = context.new_cdp_session(page).send(
                    "Page.captureSnapshot", {"format": "mhtml"}
                )
                final_url = page.url
                _verify_public_chain(response, final_url)  # a script may have navigated away since
                info: dict[str, str] = page.evaluate(_EXTRACT_SCRIPT, False)

                embed_url = telegram_embed_url(url)
                if embed_url is not None:
                    # The post page of Telegram describes the channel; the embed widget holds the post itself,
                    # and a post that no longer exists has no text rather than the channel's.
                    try:
                        _goto(page, embed_url, guard)
                        embedded: dict[str, str] = page.evaluate(_EXTRACT_SCRIPT, True)
                        info = {
                            "description": "",
                            "body": "",
                            "message": embedded["message"],
                            "published": embedded["published"],
                        }
                    except PlaywrightError:
                        logger.warning("Capture: could not read the Telegram post widget of %s", url, exc_info=True)
            finally:
                browser.close()
    except UnsafeUrlError as exc:
        raise CaptureError(str(exc)) from exc
    except PlaywrightError as exc:
        raise CaptureError(str(exc).splitlines()[0] if str(exc) else type(exc).__name__) from exc

    return PageCapture(
        png=png,
        mhtml=str(snapshot["data"]).encode(),
        final_url=final_url,
        text=_clean_text(_choose_text(info, platform)),
        published_at=_publication_time(info["published"]),
    )


def capture_ad(
    session: Session,
    ad_post_id: int,
    requested_by: int | None,
    page_capture: Callable[[str], PageCapture] = capture_page,
) -> None:
    """Capture the publication's URL into evidence and fill in what the page tells (text, publication time).

    A failure is recorded on the post (and reported to the requesting user), never raised: the analysis of
    the post goes on with the data it has.
    """
    ad = session.get(AdPost, ad_post_id)
    if ad is None:
        logger.warning("archive.capture: ad_post %s does not exist", ad_post_id)
        return
    if ad.url is None or ad.capture_status is CaptureStatus.done:
        return
    url = ad.url
    session.commit()  # no transaction is held while the browser works

    try:
        captured = page_capture(url)
        link = EvidenceLink(ad_post_id=ad.id)
        screenshot_id: int | None = None
        for data, kind, content_type in (
            (captured.png, EvidenceKind.screenshot_png, "image/png"),
            (captured.mhtml, EvidenceKind.archive_mhtml, "multipart/related"),
        ):
            evidence = storage.put_evidence(
                session, data, kind, content_type, captured.final_url, link=link, created_by=requested_by
            )
            if kind is EvidenceKind.screenshot_png:
                screenshot_id = evidence.id
    except Exception as exc:
        session.rollback()
        error = (str(exc).splitlines() or [""])[0][:MAX_ERROR_CHARS] or type(exc).__name__
        if not isinstance(exc, CaptureError):
            logger.exception("archive.capture: unexpected failure for ad_post %s", ad_post_id)
        ad = session.get(AdPost, ad_post_id)
        if ad is None:
            return
        ad.capture_status = CaptureStatus.failed
        ad.capture_error = error
        if requested_by is not None:
            session.add(
                Notification(
                    user_id=requested_by,
                    kind=NotificationKind.capture_failed,
                    entity_type="ad_post",
                    entity_id=ad.id,
                    payload={"url": url, "error": error},
                )
            )
        session.commit()
        return

    now = datetime.now(UTC)
    if not (ad.text or "").strip():
        # The page is not trusted to carry the OCR marker: text after it would pass for text read from the photos.
        ad.text = captured.text.replace(OCR_MARKER, "\n\n") or None
    elif (
        captured.text
        and split_ocr(ad.text or "")[0].strip()
        and ad.platform in _POST_TEXT_PLATFORMS
        and ad.origin in SOURCE_TEXT_ORIGINS  # not a citizen's note or the words typed in by staff
    ):
        # The saved text stays the original; what the page says now, when it differs, is a later version.
        record_version(session, ad, captured.text, AdVersionSource.capture, now, screenshot_id)
    if ad.published_at is None:
        ad.published_at = captured.published_at
    ad.captured_at = now
    ad.last_checked_at = now
    ad.capture_status = CaptureStatus.done
    ad.capture_error = None
    session.commit()
