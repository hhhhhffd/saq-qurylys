"""URL helpers for ad publications: platform detection, deduplication keys and an SSRF guard."""

import hashlib
import ipaddress
import re
import socket
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models.enums import Platform

EXTERNAL_ID_MAX = 255
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_PARAMS = frozenset({"igshid", "igsh", "fbclid", "gclid", "yclid"})

_PLATFORM_HOSTS: dict[str, Platform] = {
    "instagram.com": Platform.instagram,
    "tiktok.com": Platform.tiktok,
    "t.me": Platform.telegram,
    "telegram.me": Platform.telegram,
    "telegram.org": Platform.telegram,
    "krisha.kz": Platform.aggregator,
    "olx.kz": Platform.aggregator,
    "kn.kz": Platform.aggregator,
}

_INSTAGRAM_POST = re.compile(r"^/(?:[\w.]+/)?(?:p|reel|reels|tv)/([\w-]+)")
_INSTAGRAM_RESERVED = frozenset({"p", "reel", "reels", "tv", "explore", "stories", "accounts"})
_TIKTOK_VIDEO = re.compile(r"/video/(\d+)")
_TELEGRAM_POST = re.compile(r"^/(?:s/)?([\w]{4,})/(\d+)/?$")
_TELEGRAM_CHANNEL = re.compile(r"^/(?:s/)?([\w]{4,})(?:/|$)")
# The address of an OLX offer ends with its own code, `...-ID<code>.html`; the words before it follow the title.
_OLX_OFFER = re.compile(r"-(ID[A-Za-z0-9]+)\.html$")


class UnsafeUrlError(ValueError):
    """The URL is not a public http(s) address and must not be fetched by the server."""


def split_url(url: str) -> tuple[str, str]:
    """(host without `www.`, path) of a URL; the host is lowercased."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    return host, parts.path


def is_http_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 - raises ValueError for a port out of range
    except ValueError:
        return False
    return parts.scheme in {"http", "https"} and bool(parts.hostname)


def detect_platform(url: str) -> Platform:
    host, _ = split_url(url)
    for domain, platform in _PLATFORM_HOSTS.items():
        if host == domain or host.endswith(f".{domain}"):
            return platform
    return Platform.website


def normalize_url(url: str) -> str:
    """Canonical form used for deduplication: lowercase scheme and host, no fragment, no tracking parameters."""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS and not key.lower().startswith(_TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), (parts.netloc or "").lower(), path, urlencode(query), ""))


def external_id_for(platform: Platform, url: str) -> str:
    """Stable identifier of a publication: the platform's own post id when the URL has one, else the URL."""
    host, path = split_url(url)
    if platform is Platform.instagram and (match := _INSTAGRAM_POST.match(path)):
        return match.group(1)
    if platform is Platform.tiktok and (match := _TIKTOK_VIDEO.search(path)):
        return match.group(1)
    if platform is Platform.telegram and (match := _TELEGRAM_POST.match(path)):
        return f"{match.group(1).lower()}/{match.group(2)}"
    if (
        platform is Platform.aggregator
        and (host == "olx.kz" or host.endswith(".olx.kz"))
        and (match := _OLX_OFFER.search(path))
    ):
        # An edit of the title changes the words of the address, not the offer: the code identifies it.
        return f"olx.kz/{match.group(1)}"
    normalized = normalize_url(url)
    if len(normalized) <= EXTERNAL_ID_MAX:
        return normalized
    return f"sha256:{hashlib.sha256(normalized.encode()).hexdigest()}"


def handle_from_url(platform: Platform, url: str) -> str | None:
    """Account handle (lowercase, no `@`) that published the URL, when the platform's URLs carry it."""
    host, path = split_url(url)
    if platform is Platform.instagram:
        first = path.strip("/").split("/")[0]
        return first.lower() if first and first not in _INSTAGRAM_RESERVED else None
    if platform is Platform.tiktok:
        first = path.strip("/").split("/")[0]
        return first.removeprefix("@").lower() if first.startswith("@") else None
    if platform is Platform.telegram and (match := _TELEGRAM_CHANNEL.match(path)):
        return match.group(1).lower()
    if platform in {Platform.website, Platform.aggregator}:
        return host or None
    return None


def telegram_embed_url(url: str) -> str | None:
    """Single-message widget of a public Telegram post (`t.me/<channel>/<id>`); None for other URLs."""
    host, path = split_url(url)
    match = _TELEGRAM_POST.match(path)
    if host not in {"t.me", "telegram.me"} or match is None:
        return None
    return f"https://t.me/{match.group(1)}/{match.group(2)}?embed=1&mode=tme"


def ensure_public_url(url: str) -> None:
    """Reject anything but a public http(s) address: the server fetches these URLs from inside the
    deployment network, so loopback, private, link-local and reserved targets must stay unreachable.

    A host that does not resolve passes: the fetch itself then fails with a clear error.
    """
    try:
        parts = urlsplit(url)
        host, port = parts.hostname, parts.port
    except ValueError as exc:  # "Invalid IPv6 URL", "Port out of range"
        raise UnsafeUrlError("Некорректная ссылка") from exc
    if parts.scheme not in {"http", "https"} or not host:
        raise UnsafeUrlError("Допустимы только ссылки http и https")
    try:
        infos = socket.getaddrinfo(host, port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror:
        return
    except (ValueError, OverflowError) as exc:  # a host name that cannot be encoded
        raise UnsafeUrlError("Некорректный адрес") from exc
    for info in infos:
        address = ipaddress.ip_address(str(info[4][0]).split("%")[0])
        if not address.is_global:
            raise UnsafeUrlError("Адрес находится во внутренней сети и недоступен для фиксации")
