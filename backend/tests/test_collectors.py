"""Parsers and paging of the collectors on synthetic pages (tests/fixtures/collectors); no real site is touched."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app import collectors
from app.collectors import base, krisha
from app.collectors.aggregator import AggregatorCollector, check_search_url
from app.collectors.base import CollectedPost, CollectorError
from app.collectors.http import Fetcher
from app.collectors.instagram import InstagramCollector
from app.collectors.krisha import KrishaCollector
from app.collectors.olx import OlxCollector, search_params
from app.collectors.telegram import TelegramCollector
from app.config import Settings, get_settings
from app.models import SourceAccount
from app.models.enums import Platform

FIXTURES = Path(__file__).parent / "fixtures" / "collectors"
DELAY = 2.5
LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC)
Handler = Callable[[httpx.Request], httpx.Response]


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class Site:
    """A fake site: answers requests with `handler`, remembers them and the pauses between them."""

    def __init__(self, handler: Handler) -> None:
        self.requests: list[httpx.Request] = []
        self.pauses: list[float] = []
        self._handler = handler

    def fetcher(self) -> Fetcher:
        client = httpx.Client(transport=httpx.MockTransport(self._answer), headers={"User-Agent": "test-agent"})
        return Fetcher(client, DELAY, self.pauses.append)

    def _answer(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)


def never_known(external_id: str) -> bool:
    return False


def account(platform: Platform, handle: str, url: str | None = None) -> SourceAccount:
    return SourceAccount(platform=platform, handle=handle, url=url)


# ---------------------------------------------------------------- Telegram


def telegram_site() -> Site:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("before") == "101":
            return httpx.Response(200, text=fixture("telegram_page2.html"))
        return httpx.Response(200, text=fixture("telegram_page1.html"))

    return Site(handler)


def collect_telegram(
    site: Site, since: datetime, known: Callable[[str], bool] = never_known, max_pages: int = 3
) -> list[CollectedPost]:
    collector = TelegramCollector(site.fetcher(), max_pages)
    return list(collector.collect(account(Platform.telegram, "zhk_alatau_demo"), since, known))


def test_telegram_messages_become_posts() -> None:
    site = telegram_site()

    posts = collect_telegram(site, LONG_AGO, max_pages=1)

    # The service message without text and photos is left out; the reply's quote is not the reply's text.
    assert [post.external_id for post in posts] == ["zhk_alatau_demo/101", "zhk_alatau_demo/102", "zhk_alatau_demo/103"]
    first, second, third = posts
    assert first.text == (
        "Старт продаж! 🩵\nБронь квартир открыта.\n\nСайт: alatau.test\n"
        "Условия: смотрите здесь (https://alatau.test/terms)\n#алатау"
    )
    assert first.links == ["https://alatau.test/", "https://alatau.test/terms"]
    assert first.media_urls == ["https://cdn.alatau.test/file/photo101.jpg"]
    assert first.url == "https://t.me/zhk_alatau_demo/101" and first.author == "ЖК Алатау (демо)"
    assert first.published_at == datetime(2026, 10, 10, 8, tzinfo=UTC)
    assert second.media_urls == [
        "https://cdn.alatau.test/file/album-a.jpg",
        "https://cdn.alatau.test/file/album-b.jpg",
        "https://cdn.alatau.test/file/video-thumb.jpg",
    ]
    assert second.links == ["https://alatau.test/installment"] and second.text == "Рассрочка без процентов на 24 месяца"
    assert third.text == "Ответ: офис продаж работает ежедневно" and third.media_urls == []
    assert site.requests[0].url.path == "/s/zhk_alatau_demo"
    assert site.requests[0].headers["user-agent"] == "test-agent"


def test_telegram_pages_back_to_since_with_a_pause_between_requests() -> None:
    site = telegram_site()

    posts = collect_telegram(site, datetime(2026, 10, 5, tzinfo=UTC))

    # Page 2 is the oldest one: its only message is older than `since`, so it is read but not returned.
    assert [post.external_id for post in posts] == ["zhk_alatau_demo/101", "zhk_alatau_demo/102", "zhk_alatau_demo/103"]
    assert [request.url.params.get("before") for request in site.requests] == [None, "101"]
    assert site.pauses == [DELAY]


def test_telegram_stops_at_the_page_that_reaches_since() -> None:
    site = telegram_site()

    posts = collect_telegram(site, datetime(2026, 10, 11, tzinfo=UTC))

    assert [post.external_id for post in posts] == ["zhk_alatau_demo/102", "zhk_alatau_demo/103"]
    assert len(site.requests) == 1  # the page has a message older than `since`: nothing further is read
    assert site.pauses == []


def test_telegram_returns_an_old_post_that_is_stored_to_notice_an_edit() -> None:
    site = telegram_site()

    posts = collect_telegram(
        site, datetime(2026, 10, 11, tzinfo=UTC), known=lambda external_id: external_id.endswith("/101")
    )

    assert [post.external_id for post in posts] == ["zhk_alatau_demo/101", "zhk_alatau_demo/102", "zhk_alatau_demo/103"]


def test_telegram_reads_at_most_max_pages() -> None:
    site = telegram_site()

    collect_telegram(site, LONG_AGO, max_pages=1)

    assert len(site.requests) == 1


def test_telegram_channel_without_web_preview_is_a_source_error() -> None:
    site = Site(lambda request: httpx.Response(302, headers={"location": "https://t.me/no_preview_chan"}))

    with pytest.raises(CollectorError, match="нет публичного веб-просмотра"):
        collect_telegram(site, LONG_AGO)

    assert len(site.requests) == 1  # the redirect was not followed


def test_telegram_other_failures_are_source_errors() -> None:
    with pytest.raises(CollectorError, match="HTTP 429"):
        collect_telegram(Site(lambda request: httpx.Response(429)), LONG_AGO)

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(CollectorError, match="ошибка сети"):
        collect_telegram(Site(broken), LONG_AGO)
    with pytest.raises(CollectorError, match="Некорректное имя"):
        list(
            TelegramCollector(telegram_site().fetcher(), 1).collect(
                account(Platform.telegram, "../x"), LONG_AGO, never_known
            )
        )


# ---------------------------------------------------------------- OLX


def test_olx_web_address_is_mapped_to_api_parameters() -> None:
    url = (
        "https://www.olx.kz/nedvizhimost/q-novostroyka-zhk/?search%5Bfilter_enum_tip_zhilya%5D%5B0%5D=novostroyki"
        "&search%5Border%5D=created_at%3Adesc&search%5Bfilter_float_price%3Afrom%5D=1000&city_id=77&utm_source=x"
    )

    assert search_params(url) == {
        "query": "novostroyka zhk",
        "filter_enum_tip_zhilya[0]": "novostroyki",
        "filter_float_price:from": "1000",
        "city_id": "77",
    }
    assert search_params("https://olx.kz/nedvizhimost/?q=бронь") == {"query": "бронь"}
    assert search_params("https://www.olx.kz/api/v1/offers/?query=x&limit=5&offset=9&sort_by=a&category_id=3") == {
        "query": "x",
        "category_id": "3",
    }


def olx_site(first_page: str | None = None) -> Site:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("offset") != "0":
            return httpx.Response(200, json={"data": [], "links": {}})
        return httpx.Response(200, text=first_page or fixture("olx_page1.json"))

    return Site(handler)


def collect_olx(site: Site, since: datetime, known: Callable[[str], bool] = never_known) -> list[CollectedPost]:
    collector = OlxCollector(site.fetcher(), 3)
    return list(
        collector.collect(account(Platform.aggregator, "olx", "https://www.olx.kz/q-novostroyka/"), since, known)
    )


def test_olx_offers_become_posts_without_seller_data() -> None:
    site = olx_site()

    promoted, fresh, old = collect_olx(site, LONG_AGO)

    request = site.requests[0]
    assert request.url.host == "www.olx.kz" and request.url.path == "/api/v1/offers/"
    assert dict(request.url.params) == {
        "query": "novostroyka",
        "limit": "40",
        "offset": "0",
        "sort_by": "created_at:desc",
    }
    # The address is the offer's own; the `reason` parameter of the search is not part of it.
    assert promoted.url == "https://www.olx.kz/d/obyavlenie/promo-kvartira-v-zhk-demo-IDabc1.html"
    assert promoted.external_id == promoted.url
    assert promoted.text == (
        "Квартира в ЖК «Демо-Парк» от застройщика\nЦена: 18 900 000 тг.\nТип жилья: Новостройки\n"
        "Усть-Каменогорск, Восточно-Казахстанская область\n\n"
        "Продажа квартир на этапе котлована.\nБронь за 50 000 тг.\n\nЗвоните!"
    )
    assert promoted.published_at == datetime(2026, 8, 1, 5, tzinfo=UTC)
    assert promoted.media_urls == [
        "https://img.olx.test/image/aaa;s=1000x1000",
        "https://img.olx.test/image/bbb;s=1000x1000",
    ]
    assert fresh.text.startswith("Рассрочка без первого взноса\nЦена: 15 000 000 тг.\nСемей, Абайская область")
    assert old.media_urls == []
    for post in (promoted, fresh, old):
        assert post.author is None
        assert "Продавец" not in post.text and "Не хранить" not in post.text


def test_olx_returns_only_posts_newer_than_since_and_stops_paging() -> None:
    site = olx_site()

    posts = collect_olx(site, datetime(2026, 10, 1, tzinfo=UTC))

    # The paid placement from August floats to the top but is not new; the organic offers show where `since` is.
    assert [post.url for post in posts] == ["https://www.olx.kz/d/obyavlenie/kvartira-bez-pervogo-vznosa-IDabc2.html"]
    assert len(site.requests) == 1


def test_olx_a_paid_placement_does_not_stop_the_paging() -> None:
    site = olx_site()

    posts = collect_olx(site, datetime(2026, 8, 15, tzinfo=UTC))

    assert len(posts) == 2  # the August placement is old, the offers from September and October are not
    assert [request.url.params["offset"] for request in site.requests] == ["0", "40"]
    assert site.pauses == [DELAY]


def test_olx_errors_are_source_errors() -> None:
    with pytest.raises(CollectorError, match="HTTP 403"):
        collect_olx(Site(lambda request: httpx.Response(403, text="<html>blocked</html>")), LONG_AGO)
    with pytest.raises(CollectorError, match="не в формате JSON"):
        collect_olx(Site(lambda request: httpx.Response(200, text="<html></html>")), LONG_AGO)
    with pytest.raises(CollectorError, match="неожиданный"):
        collect_olx(Site(lambda request: httpx.Response(200, json={"error": "x"})), LONG_AGO)
    with pytest.raises(CollectorError, match="нет ни запроса, ни фильтров"):
        list(
            OlxCollector(olx_site().fetcher(), 1).collect(
                account(Platform.aggregator, "x", "https://olx.kz/"), LONG_AGO, never_known
            )
        )


# ---------------------------------------------------------------- Krisha

LIST_URL = "https://krisha.kz/prodazha/kvartiry/demo-gorod/?das[novostroiki]=1"


def krisha_site(statuses: dict[str, int] | None = None) -> Site:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/a/show/"):
            status = (statuses or {}).get(path.rsplit("/", 1)[1], 200)
            if status != 200:
                return httpx.Response(status, text="<html><title id='slg-title'></title>/.safeline/static</html>")
            return httpx.Response(200, text=fixture("krisha_detail.html"))
        if request.url.params.get("page") == "2":
            return httpx.Response(200, text="<html><body>нет объявлений</body></html>")
        return httpx.Response(200, text=fixture("krisha_list.html"))

    return Site(handler)


def collect_krisha(site: Site, known: Callable[[str], bool] = never_known, max_pages: int = 3) -> list[CollectedPost]:
    collector = KrishaCollector(site.fetcher(), max_pages)
    return list(collector.collect(account(Platform.aggregator, "kr", LIST_URL), LONG_AGO, known))


def test_krisha_card_ids_come_from_the_list_page() -> None:
    from selectolax.lexbor import LexborHTMLParser

    assert krisha.list_ids(LexborHTMLParser(fixture("krisha_list.html"))) == ["700001", "700002", "700003"]


def test_krisha_detail_page_becomes_a_post() -> None:
    post = krisha.parse_detail(fixture("krisha_detail.html"), "700001")

    assert post is not None
    assert post.url == "https://krisha.kz/a/show/700001" and post.external_id == post.url
    assert post.text == (
        "1-комнатная квартира · 42 м², ул. Демонстрационная 1\nот 18 900 000 ₸\nУсть-Каменогорск, Центральный р-н\n"
        "Тип дома: монолитный, 2027 г.п.\nЖилой комплекс: Демо-Парк\nРассрочка: да, без переплаты\n\n"
        "Продаётся квартира в строящемся доме.\nБронь по телефону.\n\nРассрочка от застройщика."
    )
    assert post.published_at == datetime(2026, 10, 13, tzinfo=krisha.TIME_ZONE)
    assert post.media_urls == [
        "https://photos.krisha.test/700001/1-full.jpg",
        "https://photos.krisha.test/700001/2-full.jpg",
    ]
    assert post.author is None
    assert krisha.parse_detail("<html><title>Проверка браузера</title></html>", "1") is None


def test_krisha_opens_details_only_of_unseen_listings_and_pages_on() -> None:
    site = krisha_site()

    posts = collect_krisha(site, known=lambda external_id: external_id.endswith("/700001"))

    assert [post.url for post in posts] == ["https://krisha.kz/a/show/700002", "https://krisha.kz/a/show/700003"]
    paths = [(request.url.path, request.url.params.get("page")) for request in site.requests]
    assert paths == [
        ("/prodazha/kvartiry/demo-gorod/", None),
        ("/a/show/700002", None),
        ("/a/show/700003", None),
        ("/prodazha/kvartiry/demo-gorod/", "2"),
    ]
    assert site.requests[0].url.params["das[novostroiki]"] == "1"
    assert len(site.pauses) == 3 and set(site.pauses) == {DELAY}


def test_krisha_stops_on_a_page_of_stored_listings_and_at_the_detail_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    site = krisha_site()
    assert collect_krisha(site, known=lambda external_id: True) == []
    assert len(site.requests) == 1

    monkeypatch.setattr(krisha, "MAX_DETAILS_PER_RUN", 2)
    capped = krisha_site()
    assert len(collect_krisha(capped)) == 2
    assert len(capped.requests) == 3  # the list page and two details; the next page is for the next run


def test_krisha_listing_removed_after_the_list_was_read_is_skipped() -> None:
    posts = collect_krisha(krisha_site({"700002": 404}))

    assert [post.url for post in posts] == ["https://krisha.kz/a/show/700001", "https://krisha.kz/a/show/700003"]


def test_krisha_bot_check_is_a_source_error() -> None:
    with pytest.raises(CollectorError, match=r"HTTP 468.*проверки браузером"):
        collect_krisha(krisha_site({"700001": 468}))
    with pytest.raises(CollectorError, match="HTTP 403"):
        collect_krisha(Site(lambda request: httpx.Response(403)))
    with pytest.raises(CollectorError, match="не удалось разобрать"):
        collect_krisha(Site(lambda request: httpx.Response(200, text=fixture("krisha_list.html"))))


def test_krisha_posts_read_before_a_failure_are_not_lost() -> None:
    delivered: list[CollectedPost] = []
    collector = KrishaCollector(krisha_site({"700002": 468}).fetcher(), 3)

    def receive() -> None:
        for post in collector.collect(account(Platform.aggregator, "kr", LIST_URL), LONG_AGO, never_known):
            delivered.append(post)

    with pytest.raises(CollectorError):
        receive()

    assert [post.url for post in delivered] == ["https://krisha.kz/a/show/700001"]


# ---------------------------------------------------------------- aggregator


def test_search_addresses_are_checked() -> None:
    for url in (
        "https://www.olx.kz/nedvizhimost/q-zhk/",
        "http://olx.kz/",
        "https://krisha.kz/prodazha/kvartiry/almaty/?das[novostroiki]=1&utm_source=x",
        "https://www.krisha.kz/prodazha/kvartiry/",
    ):
        check_search_url(url)
    for url, message in (
        ("ftp://olx.kz/", "http"),
        ("https://example.com/search", r"только поиски на olx\.kz и krisha\.kz"),
        ("https://m.olx.kz/", "только поиски"),
        ("https://krisha.kz/prodazha/kvartiry/?raion=3", "robots.txt"),
        ("https://krisha.kz/prodazha/kvartiry/?sub_cat=1", "robots.txt"),
        ("https://krisha.kz/ajax/search/", "robots.txt"),
    ):
        with pytest.raises(ValueError, match=message):
            check_search_url(url)


def test_aggregator_dispatches_by_the_site_of_the_address() -> None:
    olx_site_ = olx_site()
    krisha_site_ = krisha_site()
    both = AggregatorCollector(
        {"olx": OlxCollector(olx_site_.fetcher(), 1), "krisha": KrishaCollector(krisha_site_.fetcher(), 1)}
    )
    olx_account = account(Platform.aggregator, "a", "https://www.olx.kz/q-novostroyka/")
    krisha_account = account(Platform.aggregator, "b", LIST_URL)

    assert len(list(both.collect(olx_account, LONG_AGO, never_known))) == 3
    assert len(olx_site_.requests) == 1 and krisha_site_.requests == []
    assert len(list(both.collect(krisha_account, LONG_AGO, never_known))) == 3
    assert both.capture_urls is True and both.platform is Platform.aggregator


def test_aggregator_skips_a_site_that_is_off_and_reports_a_foreign_address() -> None:
    only_olx = AggregatorCollector({"olx": OlxCollector(olx_site().fetcher(), 1)})

    assert only_olx.handles(account(Platform.aggregator, "a", "https://olx.kz/q-x/")) is True
    assert only_olx.handles(account(Platform.aggregator, "b", LIST_URL)) is False
    # Without a usable address the account is not skipped silently: its error says what is wrong.
    assert only_olx.handles(account(Platform.aggregator, "c", None)) is True
    with pytest.raises(CollectorError, match=r"только поиски на olx\.kz и krisha\.kz"):
        list(only_olx.collect(account(Platform.aggregator, "c", "https://example.com/"), LONG_AGO, never_known))
    with pytest.raises(CollectorError, match="выключен"):
        list(only_olx.collect(account(Platform.aggregator, "d", LIST_URL), LONG_AGO, never_known))


# ---------------------------------------------------------------- Instagram

IG_USER_ID = "17841400000000099"
IG_TOKEN = "token-of-the-test-app"


def instagram_site(statuses: dict[str, tuple[int, str]] | None = None) -> Site:
    def handler(request: httpx.Request) -> httpx.Response:
        if statuses is not None:
            status, body = statuses["any"]
            return httpx.Response(status, text=body)
        if "after(QVFIUdemoCursor1)" in request.url.params["fields"]:
            return httpx.Response(200, text=fixture("instagram_page2.json"))
        return httpx.Response(200, text=fixture("instagram_page1.json"))

    return Site(handler)


def collect_instagram(site: Site, since: datetime, max_pages: int = 3) -> list[CollectedPost]:
    collector = InstagramCollector(site.fetcher(), max_pages, IG_TOKEN, IG_USER_ID, "v26.0")
    return list(collector.collect(account(Platform.instagram, "zhk_demo.park"), since, never_known))


def test_instagram_media_become_posts() -> None:
    site = instagram_site()

    posts = collect_instagram(site, datetime(2026, 9, 1, tzinfo=UTC))

    # The post without a caption and without a picture is left out.
    assert [post.external_id for post in posts] == ["CdemoAAA1", "CdemoBBB2", "CdemoCCC3"]
    image, video, carousel = posts
    assert (
        image.text.startswith("Старт продаж в ЖК «Демо-Парк»") and image.url == "https://www.instagram.com/p/CdemoAAA1/"
    )
    assert image.media_urls == ["https://scontent.cdn.test/v/image1.jpg?sig=abc"]
    assert image.author == "zhk_demo.park" and image.published_at == datetime(2026, 10, 13, 8, tzinfo=UTC)
    assert video.media_urls == ["https://scontent.cdn.test/v/thumb2.jpg?sig=abc"]  # the cover of the video
    assert carousel.media_urls == [
        "https://scontent.cdn.test/v/child1.jpg?sig=abc",
        "https://scontent.cdn.test/v/child3.jpg?sig=abc",
    ]
    assert InstagramCollector.capture_urls is False


def test_instagram_request_follows_the_graph_api_and_keeps_the_token_out_of_the_address() -> None:
    site = instagram_site()

    collect_instagram(site, datetime(2026, 9, 1, tzinfo=UTC))

    first, second = site.requests
    assert first.url.host == "graph.facebook.com" and first.url.path == f"/v26.0/{IG_USER_ID}"
    assert first.url.params["fields"] == (
        "business_discovery.username(zhk_demo.park){media.limit(25)"
        "{id,caption,permalink,timestamp,media_type,media_url,thumbnail_url,children{id,media_type,media_url}}}"
    )
    assert "after(QVFIUdemoCursor1)" in second.url.params["fields"]
    for request in site.requests:
        assert request.headers["authorization"] == f"Bearer {IG_TOKEN}"
        assert IG_TOKEN not in str(request.url) and "access_token" not in request.url.params


def test_instagram_pages_back_to_since() -> None:
    old = instagram_site()
    assert [post.external_id for post in collect_instagram(old, datetime(2026, 7, 1, tzinfo=UTC))][-1] == "CdemoEEE5"
    assert len(old.requests) == 2  # the second page has no `next`: that is the end

    recent = instagram_site()
    posts = collect_instagram(recent, datetime(2026, 10, 12, 12, tzinfo=UTC))
    assert [post.external_id for post in posts] == ["CdemoAAA1"]
    assert len(recent.requests) == 1  # the first page already reaches `since`

    assert len(collect_instagram(instagram_site(), datetime(2026, 7, 1, tzinfo=UTC), max_pages=1)) == 3


def test_instagram_api_error_becomes_the_source_error() -> None:
    body = '{"error": {"message": "Invalid user id", "type": "GraphMethodException", "code": 110}}'
    with pytest.raises(CollectorError, match="Instagram: Invalid user id") as caught:
        collect_instagram(instagram_site({"any": (400, body)}), LONG_AGO)
    assert IG_TOKEN not in str(caught.value)
    with pytest.raises(CollectorError, match="HTTP 502"):
        collect_instagram(instagram_site({"any": (502, "<html>bad gateway</html>")}), LONG_AGO)
    with pytest.raises(CollectorError, match="не вернул данные"):
        collect_instagram(instagram_site({"any": (200, '{"id": "1"}')}), LONG_AGO)
    with pytest.raises(CollectorError, match="Некорректное имя"):
        list(
            InstagramCollector(instagram_site().fetcher(), 1, IG_TOKEN, IG_USER_ID, "v26.0").collect(
                account(Platform.instagram, "a b)"), LONG_AGO, never_known
            )
        )


# ---------------------------------------------------------------- which collectors are on


def settings_with(**flags: object) -> Settings:
    """Settings with every collector off except what `flags` switch on, whatever the environment says."""
    off = {
        "collect_telegram_enabled": False,
        "collect_olx_enabled": False,
        "collect_krisha_enabled": False,
        "instagram_graph_token": "",
        "instagram_graph_user_id": "",
    }
    return Settings(**{**off, **flags})  # type: ignore[arg-type]


@pytest.fixture
def empty_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base, "_registry", {})


@pytest.mark.usefixtures("empty_registry")
def test_collectors_that_are_off_are_not_registered() -> None:
    client = httpx.Client()

    assert collectors.register_enabled(settings_with(), client) == []
    assert base.registered_platforms() == []
    # A token without the user id (or the reverse) cannot call the API: Instagram stays off.
    assert collectors.register_enabled(settings_with(instagram_graph_token="t"), client) == []
    assert collectors.register_enabled(settings_with(instagram_graph_user_id="1"), client) == []
    assert base.registered_platforms() == []


@pytest.mark.usefixtures("empty_registry")
def test_each_flag_registers_its_collector() -> None:
    client = httpx.Client()

    registered = collectors.register_enabled(
        settings_with(
            collect_telegram_enabled=True,
            instagram_graph_token="t",
            instagram_graph_user_id="1",
            collect_olx_enabled=True,
        ),
        client,
    )

    assert sorted(registered) == sorted([Platform.telegram, Platform.instagram, Platform.aggregator])
    assert isinstance(base.get_collector(Platform.telegram), TelegramCollector)
    assert isinstance(base.get_collector(Platform.instagram), InstagramCollector)
    aggregator = base.get_collector(Platform.aggregator)
    assert isinstance(aggregator, AggregatorCollector)
    assert aggregator.handles(account(Platform.aggregator, "a", "https://olx.kz/q-x/")) is True
    assert aggregator.handles(account(Platform.aggregator, "b", LIST_URL)) is False  # Krisha is off


@pytest.mark.usefixtures("empty_registry")
def test_krisha_flag_alone_registers_the_aggregator() -> None:
    collectors.register_enabled(settings_with(collect_krisha_enabled=True), httpx.Client())

    aggregator = base.get_collector(Platform.aggregator)
    assert aggregator is not None and base.registered_platforms() == [Platform.aggregator]
    assert aggregator.handles(account(Platform.aggregator, "a", LIST_URL)) is True
    assert aggregator.handles(account(Platform.aggregator, "b", "https://olx.kz/q-x/")) is False


def test_the_state_of_a_platform_follows_the_settings() -> None:
    nothing = settings_with()
    krisha_only = settings_with(collect_krisha_enabled=True)

    assert not any(collectors.platform_enabled(platform, nothing) for platform in collectors.COLLECTOR_PLATFORMS)
    assert collectors.platform_enabled(Platform.aggregator, krisha_only) is True
    assert collectors.platform_enabled(Platform.telegram, krisha_only) is False
    assert collectors.platform_enabled(Platform.tiktok, settings_with(collect_telegram_enabled=True)) is False
    assert collectors.account_enabled(account(Platform.aggregator, "a", LIST_URL), krisha_only) is True
    assert collectors.account_enabled(account(Platform.aggregator, "b", "https://olx.kz/q-x/"), krisha_only) is False
    assert collectors.account_enabled(account(Platform.aggregator, "c", None), krisha_only) is False


def test_default_client_sends_the_configured_user_agent_and_follows_no_redirects() -> None:
    collectors.default_client.cache_clear()
    try:
        client = collectors.default_client()
        assert client.headers["user-agent"] == get_settings().collect_user_agent
        assert client.follow_redirects is False
    finally:
        collectors.default_client.cache_clear()
