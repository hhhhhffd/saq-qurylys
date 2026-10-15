"""Public Telegram channels, read from the server-rendered web preview `https://t.me/s/<channel>`."""

import re
from collections.abc import Iterator
from datetime import datetime

from selectolax.lexbor import LexborHTMLParser, LexborNode

from app.collectors.base import CollectedPost, CollectorError, IsKnown
from app.collectors.html import link_urls, node_text
from app.collectors.http import Fetcher
from app.models import SourceAccount
from app.models.enums import Platform

PREVIEW_URL = "https://t.me/s"
_CHANNEL = re.compile(r"[A-Za-z0-9_]{4,64}")
_BACKGROUND_URL = re.compile(r"url\(\s*['\"]?([^'\")]+?)['\"]?\s*\)")
_MEDIA_SELECTOR = "a.tgme_widget_message_photo_wrap, i.tgme_widget_message_video_thumb"


def _background_url(node: LexborNode) -> str | None:
    match = _BACKGROUND_URL.search(node.attributes.get("style") or "")
    return match.group(1) if match else None


def _parse_time(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def _main_text(message: LexborNode) -> LexborNode | None:
    # A reply carries a quote of the message it answers in a block with the same class.
    for node in message.css("div.tgme_widget_message_text"):
        if "js-message_reply_text" not in (node.attributes.get("class") or ""):
            return node
    return None


def parse_message(message: LexborNode) -> CollectedPost | None:
    """The post in one `div.tgme_widget_message`; None for a message without text and photos."""
    data_post = message.attributes.get("data-post") or ""
    channel, _, number = data_post.rpartition("/")
    if not channel or not number.isdigit():
        return None
    text_node = _main_text(message)
    text = node_text(text_node) if text_node is not None else ""
    links = link_urls(text_node) if text_node is not None else []
    preview = message.css_first("a.tgme_widget_message_link_preview[href]")
    preview_url = (preview.attributes.get("href") or "").strip() if preview is not None else ""
    if preview_url.startswith(("http://", "https://")) and preview_url not in links:
        links.append(preview_url)
    media = [url for node in message.css(_MEDIA_SELECTOR) if (url := _background_url(node))]
    if not text and not media:
        return None

    date_link = message.css_first("a.tgme_widget_message_date")
    time_node = date_link.css_first("time[datetime]") if date_link is not None else None
    owner = message.css_first("a.tgme_widget_message_owner_name")
    return CollectedPost(
        external_id=data_post.lower(),
        text=text,
        url=(date_link.attributes.get("href") if date_link is not None else None) or f"https://t.me/{data_post}",
        author=(node_text(owner) if owner is not None else "") or None,
        published_at=_parse_time(time_node.attributes.get("datetime") if time_node is not None else None),
        links=links,
        media_urls=list(dict.fromkeys(media)),
    )


class TelegramCollector:
    platform = Platform.telegram
    capture_urls = True

    def __init__(self, fetcher: Fetcher, max_pages: int) -> None:
        self._fetcher = fetcher
        self._max_pages = max_pages

    def handles(self, account: SourceAccount) -> bool:
        return True

    def collect(self, account: SourceAccount, since: datetime, is_known: IsKnown) -> Iterator[CollectedPost]:
        channel = account.handle
        if not _CHANNEL.fullmatch(channel):
            raise CollectorError("Некорректное имя канала Telegram")
        before: str | None = None
        for _ in range(self._max_pages):
            page = self._read_page(channel, before)
            nodes = page.css("div.tgme_widget_message[data-post]")
            posts = [post for node in nodes if (post := parse_message(node)) is not None]
            for post in posts:
                if post.published_at is None or post.published_at > since or is_known(post.external_id):
                    yield post
            dates = [post.published_at for post in posts if post.published_at is not None]
            more = page.css_first("a.tme_messages_more[data-before]")
            before = more.attributes.get("data-before") if more is not None else None
            # `before` is the number of the oldest message of the page: the next page continues from it.
            if not before or not before.isdigit() or (dates and min(dates) <= since):
                break

    def _read_page(self, channel: str, before: str | None) -> LexborHTMLParser:
        response = self._fetcher.get(f"{PREVIEW_URL}/{channel}", params={"before": before} if before else None)
        if response.is_redirect:
            # Telegram sends a channel without a web preview (and a user or a bot) to its ordinary page.
            raise CollectorError("У канала нет публичного веб-просмотра (t.me/s)")
        if response.status_code != 200:
            raise CollectorError(f"Telegram ответил HTTP {response.status_code}")
        return LexborHTMLParser(response.text)
