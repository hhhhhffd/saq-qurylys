"""Krisha.kz saved searches: list pages for the ids, detail pages for the text of the listings not seen yet."""

import json
import re
from collections.abc import Iterator
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit
from zoneinfo import ZoneInfo

import httpx
from selectolax.lexbor import LexborHTMLParser, LexborNode

from app.collectors.base import CollectedPost, CollectorError, IsKnown
from app.collectors.html import clean_text, link_urls, node_text
from app.collectors.http import Fetcher
from app.models import SourceAccount
from app.models.enums import Platform
from app.modules.ads.urls import external_id_for

SITE_URL = "https://krisha.kz"
# Detail pages are opened only for listings not stored yet; this keeps a run short when a search has many of them.
MAX_DETAILS_PER_RUN = 20
TIME_ZONE = ZoneInfo("Asia/Almaty")
_ADDED_AT = re.compile(r'"addedAt"\s*:\s*"(\d{4}-\d{2}-\d{2})')
_WINDOW_DATA = re.compile(r"window\.data\s*=\s*")
# Removed between the list and its detail page: not an error of the source.
_GONE_STATUSES = frozenset({404, 410})


def _text_of(root: LexborHTMLParser | LexborNode, selector: str) -> str:
    node = root.css_first(selector)
    return node_text(node) if node is not None else ""


def _scripts(tree: LexborHTMLParser) -> list[str]:
    return [script.text(deep=True) for script in tree.css("script")]


def _photo_urls(scripts: list[str]) -> list[str]:
    """Photos in the JSON the page assigns to `window.data` (`advert.photos[].src`)."""
    for source in scripts:
        if match := _WINDOW_DATA.search(source):
            try:
                data, _ = json.JSONDecoder().raw_decode(source, match.end())
            except ValueError:
                return []
            advert: dict[str, Any] = data.get("advert") or {} if isinstance(data, dict) else {}
            photos = advert.get("photos") or []
            return [photo["src"] for photo in photos if isinstance(photo, dict) and isinstance(photo.get("src"), str)]
    return []


def _added_at(scripts: list[str]) -> datetime | None:
    for source in scripts:
        if match := _ADDED_AT.search(source):
            day = date.fromisoformat(match.group(1))
            return datetime(day.year, day.month, day.day, tzinfo=TIME_ZONE)
    return None


def listing_url(listing_id: str) -> str:
    return f"{SITE_URL}/a/show/{listing_id}"


def list_ids(page: LexborHTMLParser) -> list[str]:
    """Ids of the listing cards of a list page, in page order."""
    ids = (card.attributes.get("data-id") or "" for card in page.css("div.a-card[data-id]"))
    return list(dict.fromkeys(card_id for card_id in ids if card_id.isdigit()))


def parse_detail(html: str, listing_id: str) -> CollectedPost | None:
    """The post of a detail page; None when the page does not look like a listing (e.g. a bot check)."""
    tree = LexborHTMLParser(html)
    title = _text_of(tree, ".offer__advert-title h1")
    if not title:
        return None
    lines = [title, _text_of(tree, "p.offer__price"), _text_of(tree, ".offer__location span")]
    for row in tree.css(".offer__info-item"):
        name = _text_of(row, ".offer__info-title")
        value = _text_of(row, ".offer__advert-short-info")
        if name and value:
            lines.append(f"{name}: {value}")
    text = "\n".join(line for line in lines if line)
    links: list[str] = []
    description_node = tree.css_first(".offer__description .text .a-text")
    if description_node is not None:
        links = link_urls(description_node)
        if description := node_text(description_node):
            text = f"{text}\n\n{description}"
    scripts = _scripts(tree)
    url = listing_url(listing_id)
    return CollectedPost(
        external_id=external_id_for(Platform.aggregator, url),
        text=clean_text(text),
        url=url,
        published_at=_added_at(scripts),
        links=links,
        media_urls=_photo_urls(scripts),
    )


def _body(response: httpx.Response) -> str:
    if response.status_code != 200:
        raise CollectorError(f"Krisha отклонил запрос (HTTP {response.status_code}): сайт требует проверки браузером")
    return response.text


class KrishaCollector:
    """Unlike the other sources, a listing is not cut off at `since`: a listing is current advertising whatever its
    date, and the ones already stored are recognised by id. A search with many unseen listings is read over
    several runs."""

    def __init__(self, fetcher: Fetcher, max_pages: int) -> None:
        self._fetcher = fetcher
        self._max_pages = max_pages

    def collect(self, account: SourceAccount, since: datetime, is_known: IsKnown) -> Iterator[CollectedPost]:
        base = urlsplit(account.url or "")
        query = [
            (key, value)
            for key, value in parse_qsl(base.query, keep_blank_values=True)
            if key != "page" and not key.startswith("utm_")
        ]
        fetched = 0
        for page_number in range(1, self._max_pages + 1):
            params = urlencode([*query, ("page", str(page_number))] if page_number > 1 else query)
            page = LexborHTMLParser(_body(self._fetcher.get(f"{SITE_URL}{base.path}", params=params)))
            new_ids = [
                listing_id
                for listing_id in list_ids(page)
                if not is_known(external_id_for(Platform.aggregator, listing_url(listing_id)))
            ]
            for listing_id in new_ids[: MAX_DETAILS_PER_RUN - fetched]:
                fetched += 1
                response = self._fetcher.get(listing_url(listing_id))
                if response.status_code in _GONE_STATUSES:
                    continue
                post = parse_detail(_body(response), listing_id)
                if post is None:
                    raise CollectorError("Krisha: не удалось разобрать страницу объявления")
                yield post
            # A page of known listings means the older ones are known too.
            if not new_ids or fetched >= MAX_DETAILS_PER_RUN or page.css_first("a.paginator__btn--next") is None:
                break
