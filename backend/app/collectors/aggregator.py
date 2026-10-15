"""Saved searches of listing sites: one collector for the `aggregator` platform that serves OLX.kz and Krisha.kz."""

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol
from urllib.parse import parse_qsl, urlsplit

from app.collectors.base import CollectedPost, CollectorError, IsKnown
from app.models import SourceAccount
from app.models.enums import Platform
from app.modules.ads.urls import is_http_url, split_url

SOURCE_HOSTS = {"olx.kz": "olx", "krisha.kz": "krisha"}
# robots.txt of Krisha disallows these; a search that needs them is not collected.
_KRISHA_FORBIDDEN_PARAMS = frozenset({"raion", "sub_cat"})
_KRISHA_FORBIDDEN_PATHS = ("/ajax/", "/a/show-map/")


class SiteCollector(Protocol):
    def collect(self, account: SourceAccount, since: datetime, is_known: IsKnown) -> Iterable[CollectedPost]: ...


def source_of(url: str | None) -> str | None:
    """`olx` or `krisha` for a search address on one of the supported sites, else None."""
    return SOURCE_HOSTS.get(split_url(url)[0]) if url else None


def check_search_url(url: str) -> None:
    """Raise ValueError (message in Russian) unless `url` is a search address on olx.kz or krisha.kz."""
    if not is_http_url(url):
        raise ValueError("Ссылка должна начинаться с http:// или https://")
    source = source_of(url)
    if source is None:
        raise ValueError("Поддерживаются только поиски на olx.kz и krisha.kz")
    parts = urlsplit(url)
    if source == "krisha" and (
        parts.path.startswith(_KRISHA_FORBIDDEN_PATHS)
        or any(key in _KRISHA_FORBIDDEN_PARAMS for key, _ in parse_qsl(parts.query, keep_blank_values=True))
    ):
        raise ValueError("Адрес поиска Krisha содержит часть, которую запрещает robots.txt сайта")


class AggregatorCollector:
    platform = Platform.aggregator
    capture_urls = True

    def __init__(self, sites: dict[str, SiteCollector]) -> None:
        # Only the enabled sites: a search on another one is skipped.
        self._sites = sites

    def handles(self, account: SourceAccount) -> bool:
        source = source_of(account.url)
        # An address that is on neither site is reported by `collect` as the account's error.
        return source is None or source in self._sites

    def collect(self, account: SourceAccount, since: datetime, is_known: IsKnown) -> Iterable[CollectedPost]:
        try:
            check_search_url(account.url or "")
        except ValueError as exc:
            raise CollectorError(str(exc)) from exc
        site = self._sites.get(source_of(account.url) or "")
        if site is None:
            raise CollectorError("Сборщик этого сайта выключен")
        return site.collect(account, since, is_known)
