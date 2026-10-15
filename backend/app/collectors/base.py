"""Collector interface for automatic post collection (SPEC 10.1).

A collector knows how to fetch recent posts of one platform for a watched `SourceAccount`. Implementations are
registered explicitly by `app.collectors.register_enabled`; the collect tasks look them up by `SourceAccount.platform`.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.models import SourceAccount
from app.models.enums import Platform


@dataclass(frozen=True)
class CollectedPost:
    external_id: str
    text: str
    url: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    links: list[str] = field(default_factory=list)
    # Photos of the post; the caller downloads (and caps) them.
    media_urls: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class CollectorError(Exception):
    """The source cannot be read. The message is shown to staff as the account's last error: it is short, in
    Russian and must not contain secrets (tokens, URLs that carry them)."""


# Tells whether a post (by its external id) is stored already.
IsKnown = Callable[[str], bool]


class Collector(Protocol):
    platform: Platform
    # Whether the URLs of the collected posts are opened with the browser (the capture step of the pipeline).
    capture_urls: bool

    def handles(self, account: SourceAccount) -> bool:
        """False when this collector cannot serve the account (its source is switched off): the account is skipped."""
        ...

    def collect(self, account: SourceAccount, since: datetime, is_known: IsKnown) -> Iterable[CollectedPost]:
        """Posts of `account` published after `since`, plus the stored ones that appear again on the pages read:
        the caller compares their text to notice edits."""
        ...


_registry: dict[Platform, Collector] = {}


def register(collector: Collector) -> None:
    if collector.platform in _registry:
        raise ValueError(f"A collector for {collector.platform} is already registered")
    _registry[collector.platform] = collector


def get_collector(platform: Platform) -> Collector | None:
    return _registry.get(platform)


def registered_platforms() -> list[Platform]:
    return sorted(_registry)
