"""Instagram business and creator accounts through the official Graph API (Business Discovery)."""

import re
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from urllib.parse import quote

from app.collectors.base import CollectedPost, CollectorError, IsKnown
from app.collectors.http import Fetcher
from app.models import SourceAccount
from app.models.enums import Platform
from app.modules.ads.urls import external_id_for

GRAPH_URL = "https://graph.facebook.com"
PAGE_SIZE = 25
MEDIA_FIELDS = "id,caption,permalink,timestamp,media_type,media_url,thumbnail_url,children{id,media_type,media_url}"
MAX_ERROR_CHARS = 300
_HANDLE = re.compile(r"[A-Za-z0-9._]{1,30}")
_CURSOR = re.compile(r"[A-Za-z0-9_=+/.-]+")


def _parse_time(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _photo_urls(item: dict[str, Any]) -> list[str]:
    """Pictures of a post. A video has only its cover (`thumbnail_url`); `media_url` can be missing."""
    media_type = item.get("media_type")
    if media_type == "VIDEO":
        urls = [item.get("thumbnail_url")]
    elif media_type == "CAROUSEL_ALBUM" and item.get("children"):
        children = (item.get("children") or {}).get("data") or []
        urls = [child.get("media_url") for child in children if child.get("media_type") == "IMAGE"]
    else:
        urls = [item.get("media_url")]
    return [url for url in urls if isinstance(url, str) and url]


def parse_media(item: dict[str, Any], handle: str) -> CollectedPost | None:
    """One element of `business_discovery.media.data`; None when it has neither a caption nor a picture."""
    permalink = item.get("permalink")
    external_id = external_id_for(Platform.instagram, permalink) if permalink else str(item.get("id") or "")
    text = item.get("caption") or ""
    media = _photo_urls(item)
    if not external_id or (not text and not media):
        return None
    return CollectedPost(
        external_id=external_id,
        text=text,
        url=permalink or None,
        author=handle,
        published_at=_parse_time(item.get("timestamp")),
        media_urls=media,
    )


class InstagramCollector:
    platform = Platform.instagram
    # The permalink of a post shows a login wall to a browser: the caption and the downloaded pictures are the copy.
    capture_urls = False

    def __init__(self, fetcher: Fetcher, max_pages: int, token: str, user_id: str, api_version: str) -> None:
        self._fetcher = fetcher
        self._max_pages = max_pages
        self._token = token
        self._user_id = user_id
        self._api_version = api_version

    def handles(self, account: SourceAccount) -> bool:
        return True

    def collect(self, account: SourceAccount, since: datetime, is_known: IsKnown) -> Iterator[CollectedPost]:
        handle = account.handle
        if not _HANDLE.fullmatch(handle):
            raise CollectorError("Некорректное имя аккаунта Instagram")
        after: str | None = None
        for _ in range(self._max_pages):
            media = self._read_media(handle, after)
            items = media.get("data") or []
            dates: list[datetime] = []
            for item in items:
                post = parse_media(item, handle)
                if post is None:
                    continue
                if post.published_at is not None:
                    dates.append(post.published_at)
                if post.published_at is None or post.published_at > since or is_known(post.external_id):
                    yield post
            paging = media.get("paging") or {}
            after = (paging.get("cursors") or {}).get("after")
            if not paging.get("next") or not after or not _CURSOR.fullmatch(after) or (dates and min(dates) <= since):
                break

    def _read_media(self, handle: str, after: str | None) -> dict[str, Any]:
        modifiers = f".limit({PAGE_SIZE})" + (f".after({after})" if after else "")
        fields = f"business_discovery.username({handle}){{media{modifiers}{{{MEDIA_FIELDS}}}}}"
        response = self._fetcher.get(
            f"{GRAPH_URL}/{self._api_version}/{quote(self._user_id, safe='')}",
            params={"fields": fields},
            # In a header, not in the query: addresses are logged, the token must not be.
            headers={"Authorization": f"Bearer {self._token}"},
        )
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            message = str(body["error"].get("message") or "неизвестная ошибка")
            raise CollectorError(f"Instagram: {message[:MAX_ERROR_CHARS]}")
        if response.status_code != 200 or not isinstance(body, dict):
            raise CollectorError(f"Instagram ответил HTTP {response.status_code}")
        discovery = body.get("business_discovery")
        if not isinstance(discovery, dict):
            raise CollectorError("Instagram не вернул данные аккаунта")
        media = discovery.get("media")
        return media if isinstance(media, dict) else {}
