"""OLX.kz saved searches, read from the public JSON API `https://www.olx.kz/api/v1/offers/`."""

import re
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

from app.collectors.base import CollectedPost, CollectorError, IsKnown
from app.collectors.html import fragment_links, fragment_text
from app.collectors.http import Fetcher
from app.models import SourceAccount
from app.models.enums import Platform
from app.modules.ads.urls import external_id_for

API_URL = "https://www.olx.kz/api/v1/offers/"
PAGE_SIZE = 40
PHOTO_SIZE = 1000
# Paging and ordering are set by the collector, not by the saved search.
_OWN_PARAMS = frozenset({"limit", "offset", "sort_by"})
_ID_PARAMS = frozenset({"category_id", "region_id", "city_id", "district_id"})
# `search[filter_enum_tip_zhilya][0]` in a web address is `filter_enum_tip_zhilya[0]` in the API.
_WEB_FILTER = re.compile(r"search\[(filter_[^\]]+)\]((?:\[[^\]]*\])*)")
_WEB_QUERY_SEGMENT = re.compile(r"q-(.+)")


def search_params(url: str) -> dict[str, str]:
    """API parameters of a saved search: a direct `/api/v1/offers/?...` address as it is, a web address by its
    `q-<query>` path segment, `query` and `*_id` parameters and `search[filter_*]` filters. City and region
    slugs of a web address cannot be mapped (the API takes numeric ids)."""
    parts = urlsplit(url)
    pairs = parse_qsl(parts.query)
    if parts.path.startswith("/api/v1/offers"):
        return {key: value for key, value in pairs if key not in _OWN_PARAMS}
    params: dict[str, str] = {}
    for segment in parts.path.split("/"):
        if match := _WEB_QUERY_SEGMENT.fullmatch(unquote(segment)):
            params["query"] = match.group(1).replace("-", " ")
    for key, value in pairs:
        if key in {"query", "q"}:
            params["query"] = value
        elif key in _ID_PARAMS:
            params[key] = value
        elif match := _WEB_FILTER.fullmatch(key):
            params[match.group(1) + match.group(2)] = value
    return params


def _photo_urls(item: dict[str, Any]) -> list[str]:
    links = (photo.get("link") for photo in item.get("photos") or [] if isinstance(photo, dict))
    return [
        link.replace("{width}", str(PHOTO_SIZE)).replace("{height}", str(PHOTO_SIZE))
        for link in links
        if isinstance(link, str) and link
    ]


def parse_offer(item: dict[str, Any]) -> CollectedPost | None:
    """One element of the API's `data`. The seller (`user`, `contact`) is left out on purpose: those fields hold
    names and phone numbers of private persons."""
    raw_url = item.get("url")
    if not isinstance(raw_url, str) or not raw_url:
        return None
    # The address of the offer carries a `reason` parameter that depends on the search, not on the offer.
    url = urlunsplit(urlsplit(raw_url)._replace(query="", fragment=""))
    lines = [str(item.get("title") or "").strip()]
    others: list[str] = []
    for param in item.get("params") or []:
        value = param.get("value") if isinstance(param, dict) else None
        label = value.get("label") if isinstance(value, dict) else None
        if not label:
            continue
        if param.get("key") == "price":
            lines.append(f"Цена: {label}")
        else:
            others.append(f"{param.get('name') or param.get('key')}: {label}")
    location = item.get("location") or {}
    place = [(location.get(kind) or {}).get("name") for kind in ("city", "region")]
    lines.extend(others)
    lines.append(", ".join(name for name in place if name))
    description_html = str(item.get("description") or "")
    description = fragment_text(description_html)
    text = "\n".join(line for line in lines if line)
    if description:
        text = f"{text}\n\n{description}"
    created = item.get("created_time")
    try:
        published_at = datetime.fromisoformat(created) if isinstance(created, str) else None
    except ValueError:
        published_at = None
    return CollectedPost(
        external_id=external_id_for(Platform.aggregator, url),
        text=text,
        url=url,
        published_at=published_at,
        links=fragment_links(description_html),
        media_urls=_photo_urls(item),
    )


class OlxCollector:
    def __init__(self, fetcher: Fetcher, max_pages: int) -> None:
        self._fetcher = fetcher
        self._max_pages = max_pages

    def collect(self, account: SourceAccount, since: datetime, is_known: IsKnown) -> Iterator[CollectedPost]:
        params = search_params(account.url or "")
        if not params:
            raise CollectorError("В адресе поиска OLX нет ни запроса, ни фильтров")
        seen: set[str] = set()
        for page in range(self._max_pages):
            offers = self._read_offers({**params, "limit": str(PAGE_SIZE), "offset": str(page * PAGE_SIZE)})
            organic_dates: list[datetime] = []
            for item in offers["data"]:
                post = parse_offer(item) if isinstance(item, dict) else None
                if post is None or post.external_id in seen:
                    continue
                seen.add(post.external_id)
                # Paid placements float to the top whatever their age: they say nothing about where `since` is.
                if post.published_at is not None and not (item.get("promotion") or {}).get("top_ad"):
                    organic_dates.append(post.published_at)
                if post.published_at is None or post.published_at > since or is_known(post.external_id):
                    yield post
            has_next = bool((offers.get("links") or {}).get("next"))
            if not offers["data"] or not has_next or (organic_dates and min(organic_dates) <= since):
                break

    def _read_offers(self, params: dict[str, str]) -> dict[str, Any]:
        response = self._fetcher.get(API_URL, params={**params, "sort_by": "created_at:desc"})
        if response.status_code != 200:
            raise CollectorError(f"OLX отклонил запрос (HTTP {response.status_code})")
        try:
            body = response.json()
        except ValueError as exc:
            raise CollectorError("OLX вернул ответ не в формате JSON") from exc
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise CollectorError("OLX вернул неожиданный ответ")
        return body
