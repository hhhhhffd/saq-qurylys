"""The citizen bot without Telegram: the business functions over a session, the rate limiter on the real Redis, the
language choice and the start-up check."""

import string
from collections.abc import Iterator
from datetime import UTC, date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bot import main as bot_main
from app.bot import service
from app.bot.ratelimit import RateLimiter
from app.bot.texts import KK, RU, pick_language, render_facts, t
from app.config import get_settings
from app.models import AdPost, Complaint, Developer, Document, Evidence, Notification
from app.models.enums import (
    AdOrigin,
    CaptureStatus,
    CheckSource,
    CheckStatus,
    ComplaintSource,
    ComplaintStatus,
    ConstructionStatus,
    DocType,
    EvidenceKind,
    KeyStatus,
    NotificationKind,
    OcrStatus,
    Platform,
    Zone,
)
from app.modules.ads import service as ads_service
from tests.conftest import PNG_BYTES, World, make_object
from tests.support_ads import add_ad

REDIS_URL = "redis://localhost:6379/0"


@pytest.fixture
def pipelines(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, bool, int | None]]:
    """Record the pipelines the bot would queue instead of touching the Celery broker."""
    queued: list[tuple[int, bool, int | None]] = []

    def record(ad_post_id: int, *, capture: bool, requested_by: int | None) -> bool:
        queued.append((ad_post_id, capture, requested_by))
        return True

    monkeypatch.setattr(ads_service, "dispatch_pipeline", record)
    return queued


def notified(db: Session, world: World, **filters: object) -> set[str]:
    """Usernames of the users that have a notification matching the filters."""
    rows = db.scalars(select(Notification).filter_by(**filters))
    by_id = {user.id: name for name, user in world.users.items()}
    return {by_id[row.user_id] for row in rows}


# ---------------------------------------------------------------- language and texts


@pytest.mark.parametrize(
    ("language_code", "expected"),
    [("kk", "kk"), ("kk-KZ", "kk"), ("KK", "kk"), ("ru", "ru"), ("en", "ru"), ("uk", "ru"), ("", "ru"), (None, "ru")],
)
def test_language_follows_the_telegram_client(language_code: str | None, expected: str) -> None:
    assert pick_language(language_code) == expected


def test_both_languages_have_the_same_texts() -> None:
    assert RU.keys() == KK.keys()
    for key in RU:
        fields = [{name for _, name, _, _ in string.Formatter().parse(texts[key]) if name} for texts in (RU, KK)]
        assert fields[0] == fields[1], key


def test_missing_token_stops_the_bot_with_a_clear_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "telegram_bot_token", "")
    with pytest.raises(SystemExit) as stopped:
        bot_main.main()
    assert "TELEGRAM_BOT_TOKEN" in str(stopped.value)
    assert stopped.value.code != 0


def test_application_is_wired_without_a_connection() -> None:
    application = bot_main.build_application("123456:TEST-TOKEN")
    assert isinstance(application.bot_data["limiter"], RateLimiter)
    searches = application.bot_data["search_limiter"]
    assert isinstance(searches, RateLimiter) and searches._limit == bot_main.SEARCHES_PER_HOUR
    assert searches._prefix != application.bot_data["limiter"]._prefix  # separate counters
    assert application.bot_data["albums"] == {}


# ---------------------------------------------------------------- links


def test_forwarded_post_url_needs_a_public_channel() -> None:
    assert service.forwarded_post_url("novostroyki_vko", 42) == "https://t.me/novostroyki_vko/42"
    assert service.forwarded_post_url(None, 42) is None


def test_report_url_comes_from_the_forwarded_post_entities_or_text() -> None:
    forwarded = "https://t.me/novostroyki_vko/42"
    assert service.find_report_url("см. https://olx.kz/a", ["https://www.instagram.com/p/b"], forwarded) == forwarded
    assert service.find_report_url("см. https://olx.kz/a", ["https://www.instagram.com/p/b"], None) == (
        "https://www.instagram.com/p/b"
    )
    assert service.find_report_url("Смотрите https://olx.kz/a, там акция", [], None) == "https://olx.kz/a"
    assert service.find_report_url("ссылка t.me/channel/7", [], None) == "https://t.me/channel/7"
    assert service.find_report_url("ссылка www.krisha.kz/x", [], None) == "https://www.krisha.kz/x"
    assert service.find_report_url("ftp://olx.kz/a без ссылки", [], None) is None
    assert service.find_report_url("только текст", [], None) is None
    assert service.find_report_url("", ["https://olx.kz/" + "a" * service.URL_MAX_CHARS], None) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://example.kz/promo",  # a site of the developer: the browser is not sent there on a citizen's word
        "http://127.0.0.1:8000/admin",
        "https://instagram.com.evil.example/p/x",  # only the real host counts
        "https://evil.example/?next=https://instagram.com/p/x",
    ],
)
def test_a_link_to_another_site_is_not_captured_but_stays_in_the_text(url: str) -> None:
    assert service.find_report_url(f"Реклама {url}", [url], None) is None


def test_the_first_link_to_a_captured_platform_is_taken_past_other_links() -> None:
    text = "Сайт https://example.kz/promo и страница https://www.tiktok.com/@dev/video/1"
    assert service.find_report_url(text, ["https://example.kz/promo"], None) == "https://www.tiktok.com/@dev/video/1"


# ---------------------------------------------------------------- report of advertising


def test_report_with_text_link_and_photos(
    db: Session, world: World, bucket: str, pipelines: list[tuple[int, bool, int | None]]
) -> None:
    result = service.submit_citizen_report(
        db,
        territory_id=world.ust.id,
        text="  Квартиры в ЖК Самал, бронь за 50 000 тенге  ",
        url="https://www.instagram.com/p/AbC123/",
        photos=[PNG_BYTES, PNG_BYTES + b"1"],
    )

    ad = db.get(AdPost, result.ad_id)
    assert ad is not None
    assert result.photos_saved == 2
    assert ad.origin is AdOrigin.citizen
    assert ad.territory_id == world.ust.id
    assert ad.author is None
    assert ad.source_account_id is None
    assert ad.external_id is not None and ad.external_id.startswith("citizen-")
    assert ad.text == "Квартиры в ЖК Самал, бронь за 50 000 тенге"
    assert ad.url == "https://www.instagram.com/p/AbC123/"
    assert ad.platform is Platform.instagram
    assert ad.capture_status is CaptureStatus.pending
    assert ad.ocr_status is OcrStatus.pending
    evidence = db.scalars(select(Evidence).where(Evidence.ad_post_id == ad.id)).all()
    assert [(item.kind, item.content_type, item.created_by) for item in evidence] == [
        (EvidenceKind.photo, "image/png", None)
    ] * 2
    assert pipelines == [(ad.id, True, None)]


def test_report_notifies_only_the_officers_covering_the_city(
    db: Session, world: World, pipelines: list[tuple[int, bool, int | None]]
) -> None:
    result = service.submit_citizen_report(
        db, territory_id=world.ust.id, text="Продаём без договора", url=None, photos=[]
    )

    assert notified(db, world, entity_type="ad_post", entity_id=result.ad_id) == {"mio_ust", "mio_region"}
    row = db.scalars(select(Notification).where(Notification.entity_id == result.ad_id)).first()
    assert row is not None
    assert row.kind is NotificationKind.citizen_report
    assert row.payload == {"name": "Сообщение гражданина: реклама"}


def test_text_only_report_has_no_capture_and_no_ocr(
    db: Session, world: World, pipelines: list[tuple[int, bool, int | None]]
) -> None:
    text = "я" * 5000
    result = service.submit_citizen_report(db, territory_id=world.semey.id, text=text, url=None, photos=[])

    ad = db.get(AdPost, result.ad_id)
    assert ad is not None
    assert ad.text == "я" * service.TEXT_MAX_CHARS
    assert ad.platform is Platform.other
    assert ad.capture_status is None
    assert ad.captured_at is not None
    assert ad.ocr_status is None
    assert result.photos_saved == 0
    assert pipelines == [(ad.id, False, None)]


def test_only_valid_photos_are_stored(
    db: Session, world: World, bucket: str, pipelines: list[tuple[int, bool, int | None]]
) -> None:
    oversized = PNG_BYTES + b"\x00" * service.PHOTO_MAX_BYTES
    photos = [b"not an image", b"", oversized, b"%PDF-1.4\n" + b"0" * 64]
    photos += [PNG_BYTES + str(number).encode() for number in range(service.PHOTO_LIMIT + 2)]

    result = service.submit_citizen_report(db, territory_id=world.ust.id, text="Фото", url=None, photos=photos)

    assert result.photos_saved == service.PHOTO_LIMIT
    assert db.scalar(select(func.count()).select_from(Evidence).where(Evidence.ad_post_id == result.ad_id)) == 10


def test_report_with_only_rejected_photos_is_empty(
    db: Session, world: World, pipelines: list[tuple[int, bool, int | None]]
) -> None:
    with pytest.raises(service.EmptyReportError):
        service.submit_citizen_report(db, territory_id=world.ust.id, text="  ", url=None, photos=[b"not an image"])

    assert db.scalar(select(func.count()).select_from(AdPost).where(AdPost.origin == AdOrigin.citizen)) == 0
    assert db.scalar(select(func.count()).select_from(Notification)) == 0
    assert pipelines == []


def test_report_stays_saved_when_the_broker_is_down(db: Session, world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ads_service, "dispatch_pipeline", lambda *args, **kwargs: False)

    result = service.submit_citizen_report(
        db, territory_id=world.ust.id, text="Акция", url="https://example.kz/promo", photos=[]
    )

    ad = db.get(AdPost, result.ad_id)
    assert ad is not None
    assert ad.capture_status is CaptureStatus.failed
    assert ad.capture_error


# ---------------------------------------------------------------- search


def test_search_finds_objects_of_the_city_by_name_and_alias(db: Session, world: World) -> None:
    samal = make_object(db, world.ust, "ЖК Самал Парк")
    make_object(db, world.ust, "ЖК Алтын Орда")
    star = make_object(db, world.ust, "ЖК Звёздный", aliases=["Парковый квартал"])
    make_object(db, world.semey, "ЖК Самал Парк Семей")

    assert [match.id for match in service.search_objects(db, world.ust.id, "самал")] == [samal.id]
    assert [match.id for match in service.search_objects(db, world.ust.id, "ЖК Самал-Парк")] == [samal.id]
    assert [match.id for match in service.search_objects(db, world.ust.id, "звездный")] == [star.id]
    assert [match.id for match in service.search_objects(db, world.ust.id, "парковый")] == [star.id]
    assert service.search_objects(db, world.ust.id, "Кокшетау") == []


def test_search_ignores_empty_and_generic_queries(db: Session, world: World) -> None:
    make_object(db, world.ust, "ЖК Самал Парк")

    assert service.search_objects(db, world.ust.id, "") == []
    assert service.search_objects(db, world.ust.id, "ЖК") == []
    assert service.search_objects(db, world.ust.id, "жилой комплекс") == []


def test_search_offers_at_most_three_best_matches(db: Session, world: World) -> None:
    for name in ("Нур Пять", "Нур Раз", "Нур Два", "Нур Три", "Нур Четыре"):
        make_object(db, world.ust, f"ЖК {name}")

    assert [match.name for match in service.search_objects(db, world.ust.id, "нур")] == [
        "ЖК Нур Два",
        "ЖК Нур Пять",
        "ЖК Нур Раз",
    ]


def test_object_belongs_to_the_chosen_city_only(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "ЖК Самал Парк")

    assert service.object_name(db, world.ust.id, obj.id) == "ЖК Самал Парк"
    assert service.object_name(db, world.semey.id, obj.id) is None
    assert service.object_facts(db, world.semey.id, obj.id) is None


def test_cities_are_listed_by_name(db: Session, world: World) -> None:
    names = [city.name for city in service.list_cities(db)]

    assert names == sorted(names)
    assert {"Усть-Каменогорск", "Семей"} <= set(names)
    assert service.find_city(db, world.ust.id) is not None
    assert service.find_city(db, world.region.id) is None


# ---------------------------------------------------------------- complaint


def test_complaint_is_registered_unverified_and_officers_are_told(
    db: Session, world: World, sent_tasks: list[tuple[str, tuple[object, ...]]]
) -> None:
    obj = make_object(db, world.ust, "ЖК Самал Парк")

    name = service.submit_complaint(db, object_id=obj.id, text="  Стройка стоит второй год  ")

    assert name == "ЖК Самал Парк"
    complaint = db.scalars(select(Complaint).where(Complaint.object_id == obj.id)).one()
    assert complaint.source is ComplaintSource.telegram
    assert complaint.received_at == datetime.now(ZoneInfo(world.ust.timezone)).date()
    assert (complaint.is_collective, complaint.signatories_count) == (False, 1)
    assert complaint.summary == "Стройка стоит второй год"
    assert complaint.status is ComplaintStatus.new
    assert complaint.is_verified is False
    assert complaint.external_id is None
    assert notified(db, world, entity_type="object", entity_id=obj.id) == {"mio_ust", "mio_region"}
    row = db.scalars(select(Notification).where(Notification.entity_id == obj.id)).first()
    assert row is not None
    assert row.kind is NotificationKind.citizen_report
    assert row.payload == {"object_name": "ЖК Самал Парк"}
    assert ("risk.recalc_object", (obj.id,)) in sent_tasks


def test_complaint_about_a_missing_object_is_an_error(db: Session) -> None:
    with pytest.raises(LookupError):
        service.submit_complaint(db, object_id=0, text="Жалоба")


# ---------------------------------------------------------------- facts


def red_demo_object(db: Session, world: World) -> int:
    developer = Developer(bin="123456789012", name="ТОО Вымышленный Строй")
    db.add(developer)
    db.flush()
    obj = make_object(
        db,
        world.ust,
        "ЖК Демо Парк",
        developer_id=developer.id,
        construction_status=ConstructionStatus.stalled,
        score=87,
        zone=Zone.red,
        key_status=KeyStatus.no_legal_basis_with_offer,
        is_demo=True,
    )
    db.add_all(
        [
            Document(
                object_id=obj.id,
                doc_type=DocType.guarantee,
                check_status=CheckStatus.not_found,
                checked_at=datetime(2026, 10, 1, 8, 0, tzinfo=UTC),
                check_source=CheckSource.housing_portal,
            ),
            Document(object_id=obj.id, doc_type=DocType.dsu_permit, check_status=CheckStatus.checking),
            Complaint(object_id=obj.id, received_at=date(2026, 10, 2), is_collective=True, signatories_count=40),
        ]
    )
    add_ad(db, world.ust, "Бронь квартир без договора", object_id=obj.id)
    db.flush()
    return obj.id


def test_facts_answer_lists_registry_facts_without_a_demo_marker(db: Session, world: World) -> None:
    facts = service.object_facts(db, world.ust.id, red_demo_object(db, world))
    assert facts is not None

    text = render_facts(facts, "ru")

    assert "ЖК «ЖК Демо Парк»" in text
    assert "Застройщик: ТОО Вымышленный Строй, БИН 123456789012" in text
    assert "Стадия строительства: работы приостановлены" in text
    assert "Гарантия АО «КЖК»: не найдено (проверено 01.10.2026, источник: Жилищный портал)" in text
    assert "Разрешение МИО на привлечение средств дольщиков: на проверке" in text
    assert "Не вносите деньги, пока у ЖК нет подтверждённой гарантии АО «КЖК» или разрешения МИО" in text
    assert "homeportal.kz" in text
    assert "демонстрационные" not in text


@pytest.mark.parametrize(
    ("lang", "forbidden"),
    [
        ("ru", ["87", "red", "зон", "балл", "риск", "красн", "жалоб", "реклам", "признак"]),
        ("kk", ["87", "red", "аймақ", "балл", "қауіп", "қызыл", "шағым", "жарнама"]),
    ],
)
def test_facts_answer_never_reveals_the_assessment(db: Session, world: World, lang: str, forbidden: list[str]) -> None:
    facts = service.object_facts(db, world.ust.id, red_demo_object(db, world))
    assert facts is not None

    text = render_facts(facts, lang).lower()

    assert [word for word in forbidden if word in text] == []
    assert "демонстрациялық" not in text and "демонстрационные" not in text


def test_facts_of_an_object_without_records_say_so(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "ЖК Новый")

    facts = service.object_facts(db, world.ust.id, obj.id)
    assert facts is not None
    text = render_facts(facts, "ru")

    assert "Застройщик: сведений нет" in text
    assert "Гарантия АО «КЖК»: сведений о проверке нет" in text
    assert "Разрешение МИО на привлечение средств дольщиков: сведений о проверке нет" in text
    assert "демонстрационные" not in text


def test_facts_use_the_confirmed_check_and_the_local_date(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "ЖК Подтверждённый")
    db.add_all(
        [
            Document(
                object_id=obj.id,
                doc_type=DocType.guarantee,
                check_status=CheckStatus.not_found,
                checked_at=datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
                check_source=CheckSource.manual,
            ),
            # 20:00 UTC is already the next day in Almaty (UTC+5).
            Document(
                object_id=obj.id,
                doc_type=DocType.guarantee,
                check_status=CheckStatus.confirmed,
                checked_at=datetime(2026, 10, 10, 20, 0, tzinfo=UTC),
                check_source=CheckSource.kazreestr,
            ),
        ]
    )
    db.flush()

    facts = service.object_facts(db, world.ust.id, obj.id)
    assert facts is not None
    guarantee, permit = facts.checks

    assert (guarantee.doc_type, guarantee.status) == (DocType.guarantee, "confirmed")
    assert guarantee.checked_on == date(2026, 10, 11)
    assert guarantee.source is CheckSource.kazreestr
    assert (permit.doc_type, permit.status, permit.checked_on, permit.source) == (
        DocType.dsu_permit,
        "none",
        None,
        None,
    )
    assert "Гарантия АО «КЖК»: подтверждено (проверено 11.10.2026, источник: Казреестр)" in render_facts(facts, "ru")


def test_texts_format_with_their_fields() -> None:
    assert t("ru", "report_thanks", id=17) == "Спасибо! Сообщение №17 передано специалистам МИО."
    assert t("ru", "error") == "Не удалось обработать сообщение, попробуйте позже"


# ---------------------------------------------------------------- rate limit


@pytest.fixture
def limiter() -> Iterator[RateLimiter]:
    client = Redis.from_url(REDIS_URL)
    prefix = f"test-bot-rate-{uuid4().hex}:"
    yield RateLimiter(client, "test-secret-test-secret-test-secret-0123456789", limit=3, prefix=prefix)
    for key in client.scan_iter(f"{prefix}*"):
        client.delete(key)
    client.close()


def test_limiter_refuses_after_the_limit_and_counts_citizens_apart(limiter: RateLimiter) -> None:
    assert [limiter.allow(1001) for _ in range(5)] == [True, True, True, False, False]
    assert limiter.allow(1002) is True


def test_limiter_keys_hide_the_telegram_id_and_expire(limiter: RateLimiter) -> None:
    limiter.allow(123456789)
    key = limiter.key(123456789)

    assert "123456789" not in key
    assert len(key.removeprefix(limiter._prefix)) == 64
    assert limiter.key(123456789) == key != limiter.key(123456780)
    ttl = limiter._client.ttl(key)
    assert isinstance(ttl, int) and 0 < ttl <= 3600
