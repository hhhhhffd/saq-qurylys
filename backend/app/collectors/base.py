"""Collector interface for automatic post collection (phase 2; v1 ships no implementations).

A collector knows how to fetch recent posts of one platform for a watched `SourceAccount`.
Implementations register themselves with `register()`; the `collect.run_all` task looks them
up by `SourceAccount.platform`.
"""

from collections.abc import Iterable
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
    raw: dict[str, Any] = field(default_factory=dict)


class Collector(Protocol):
    platform: Platform

    def collect(self, account: SourceAccount, since: datetime) -> Iterable[CollectedPost]:
        """Posts of `account` published after `since`."""
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
