"""Collectors of publications (SPEC 10.1) and the rules that switch them on.

A collector is on when its flag is set (Instagram: when it has a token); a collector that is off is not registered, so
the accounts of its platform are skipped. The API reads the same rules to report the state and to refuse a manual
collection.
"""

import time
from collections.abc import Callable
from functools import lru_cache

import httpx

from app.collectors import base
from app.collectors.aggregator import AggregatorCollector, SiteCollector, source_of
from app.collectors.http import REQUEST_TIMEOUT_S, Fetcher
from app.collectors.instagram import InstagramCollector
from app.collectors.krisha import KrishaCollector
from app.collectors.olx import OlxCollector
from app.collectors.telegram import TelegramCollector
from app.config import Settings, get_settings
from app.models import SourceAccount
from app.models.enums import Platform

# Platforms that have a collector. TikTok is only added by link (OPEN_QUESTIONS 31).
COLLECTOR_PLATFORMS = (Platform.instagram, Platform.telegram, Platform.aggregator)


def enabled_sources(settings: Settings) -> dict[str, bool]:
    """Whether each source (`instagram`, `telegram`, `olx`, `krisha`) is switched on."""
    return {
        "instagram": bool(settings.instagram_graph_token.strip() and settings.instagram_graph_user_id.strip()),
        "telegram": settings.collect_telegram_enabled,
        "olx": settings.collect_olx_enabled,
        "krisha": settings.collect_krisha_enabled,
    }


def platform_enabled(platform: Platform, settings: Settings) -> bool:
    sources = enabled_sources(settings)
    if platform is Platform.aggregator:
        return sources["olx"] or sources["krisha"]
    return sources.get(platform.value, False)


def account_enabled(account: SourceAccount, settings: Settings) -> bool:
    """Whether the account's source is on: for an aggregator search it is the site of its address."""
    if account.platform is Platform.aggregator:
        source = source_of(account.url)
        return source is not None and enabled_sources(settings)[source]
    return platform_enabled(account.platform, settings)


@lru_cache
def default_client() -> httpx.Client:
    """The client of the collectors and of the photo downloads. Redirects are never followed by it."""
    return httpx.Client(
        headers={"User-Agent": get_settings().collect_user_agent}, timeout=REQUEST_TIMEOUT_S, follow_redirects=False
    )


def register_enabled(
    settings: Settings, client: httpx.Client, sleep: Callable[[float], None] = time.sleep
) -> list[Platform]:
    """Register the collectors that are switched on; returns their platforms."""
    sources = enabled_sources(settings)

    def fetcher() -> Fetcher:
        return Fetcher(client, settings.collect_request_delay_s, sleep)

    collectors: list[base.Collector] = []
    # The userbot reads Telegram instead: it also reaches the groups that have no t.me/s preview (SPEC 10.8).
    if sources["telegram"] and not settings.userbot_configured:
        collectors.append(TelegramCollector(fetcher(), settings.collect_max_pages))
    if sources["instagram"]:
        collectors.append(
            InstagramCollector(
                fetcher(),
                settings.collect_max_pages,
                settings.instagram_graph_token.strip(),
                settings.instagram_graph_user_id.strip(),
                settings.instagram_graph_api_version,
            )
        )
    sites: dict[str, SiteCollector] = {}
    if sources["olx"]:
        sites["olx"] = OlxCollector(fetcher(), settings.collect_max_pages)
    if sources["krisha"]:
        sites["krisha"] = KrishaCollector(fetcher(), settings.collect_max_pages)
    if sites:
        collectors.append(AggregatorCollector(sites))
    for collector in collectors:
        base.register(collector)
    return [collector.platform for collector in collectors]
