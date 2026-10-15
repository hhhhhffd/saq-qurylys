"""Photos of collected posts: downloaded through the SSRF guard and checked by their signature."""

import logging
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from app.modules.ads.urls import UnsafeUrlError, ensure_public_url
from app.uploads import PHOTO_TYPES, sniff_content_type

logger = logging.getLogger(__name__)

MAX_PHOTOS = 10
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 3


@dataclass(frozen=True)
class DownloadedPhoto:
    url: str
    data: bytes
    content_type: str


class PhotoRejectedError(Exception):
    """The address answered, but not with a photo we keep."""


def fetch_photo(client: httpx.Client, url: str) -> tuple[bytes, str]:
    """(bytes, content type) of a photo. Redirects are followed by hand so that every hop passes the SSRF guard."""
    for _ in range(MAX_REDIRECTS + 1):
        ensure_public_url(url)
        with client.stream("GET", url) as response:
            if response.is_redirect and (location := response.headers.get("location")):
                try:
                    url = urljoin(url, location)
                except ValueError as exc:  # "Invalid IPv6 URL" in the Location header
                    raise UnsafeUrlError("Некорректный адрес перенаправления") from exc
                continue
            if response.status_code != 200:
                raise PhotoRejectedError(f"HTTP {response.status_code}")
            declared = response.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > MAX_PHOTO_BYTES:
                raise PhotoRejectedError("larger than the limit")
            data = bytearray()
            for chunk in response.iter_bytes():
                data += chunk
                if len(data) > MAX_PHOTO_BYTES:
                    raise PhotoRejectedError("larger than the limit")
            content_type = sniff_content_type(bytes(data))
            if content_type not in PHOTO_TYPES:
                raise PhotoRejectedError("not a JPEG, PNG or WebP image")
            return bytes(data), content_type
    raise PhotoRejectedError("too many redirects")


def download_photos(client: httpx.Client, urls: list[str]) -> list[DownloadedPhoto]:
    """The first `MAX_PHOTOS` distinct photos that could be fetched. A failed one is logged and skipped."""
    photos: list[DownloadedPhoto] = []
    for url in list(dict.fromkeys(urls))[:MAX_PHOTOS]:
        try:
            data, content_type = fetch_photo(client, url)
        except (UnsafeUrlError, PhotoRejectedError, httpx.HTTPError, httpx.InvalidURL) as exc:
            # The address is not logged: signed CDN addresses carry tokens in the query.
            logger.warning("A photo of a collected post was skipped: %s", exc)
            continue
        photos.append(DownloadedPhoto(url=url, data=data, content_type=content_type))
    return photos
