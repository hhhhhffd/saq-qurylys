"""The Telegram handlers of the bot driven with hand-made updates and a recording bot: no connection to Telegram.

The database session of the test is lent to the handlers, so what they store can be read back and is rolled back
with the test."""

import asyncio
import itertools
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from telegram import Bot, Update, User
from telegram.ext import Application

from app.bot import handlers, service
from app.bot.ratelimit import RateLimiter
from app.models import AdPost, Complaint, Evidence, Notification
from app.models.enums import AdOrigin, CaptureStatus, ComplaintSource, Platform
from tests.conftest import PNG_BYTES, World, make_object

REDIS_URL = "redis://localhost:6379/0"
USER_ID = 500
CHANNEL = {"id": -1001, "type": "channel", "title": "Новостройки", "username": "novostroyki_vko"}


@dataclass
class Sent:
    chat_id: int
    text: str
    buttons: list[tuple[str, str]]


class BorrowedSession:
    """The test session in place of a short-lived one: not closed, so the test can read the rows back."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def __enter__(self) -> Session:
        return self.session

    def __exit__(self, *exc_info: object) -> None:
        return None


class FakeFile:
    def __init__(self, file_id: str) -> None:
        self.file_id = file_id

    async def download_as_bytearray(self) -> bytearray:
        return bytearray(PNG_BYTES + self.file_id.encode())


@dataclass
class Harness:
    application: Application
    sent: list[Sent] = field(default_factory=list)
    ids: Iterator[int] = field(default_factory=lambda: itertools.count(1))

    def _envelope(self, user_id: int, lang: str) -> dict[str, Any]:
        return {
            "from": {"id": user_id, "is_bot": False, "first_name": "Гражданин", "language_code": lang},
        }

    async def send(self, text: str | None = None, *, user_id: int = USER_ID, lang: str = "ru", **fields: Any) -> None:
        number = next(self.ids)
        message = {
            "message_id": number,
            "date": 1760000000,
            "chat": {"id": user_id, "type": "private"},
            **self._envelope(user_id, lang),
            **({"text": text} if text is not None else {}),
            **fields,
        }
        await self.application.process_update(
            Update.de_json({"update_id": number, "message": message}, self.application.bot)
        )

    async def press(self, data: str, *, user_id: int = USER_ID, lang: str = "ru") -> None:
        number = next(self.ids)
        query = {
            "id": str(number),
            "chat_instance": "test",
            "data": data,
            **self._envelope(user_id, lang),
            "message": {"message_id": number, "date": 1760000000, "chat": {"id": user_id, "type": "private"}},
        }
        await self.application.process_update(
            Update.de_json({"update_id": number, "callback_query": query}, self.application.bot)
        )

    async def open_menu(self, action: str, city: str = "Усть-Каменогорск") -> None:
        """/start, the city, then a menu action."""
        await self.send("/start", entities=[{"type": "bot_command", "offset": 0, "length": 6}])
        await self.press(self.button(city))
        await self.press(f"menu:{action}")

    def button(self, label: str) -> str:
        """The callback data of the button with the label in the last message."""
        return next(data for text, data in self.sent[-1].buttons if text == label)

    @property
    def last(self) -> str:
        return self.sent[-1].text

    @property
    def texts(self) -> str:
        return "\n".join(item.text for item in self.sent)


@pytest.fixture
def harness(db: Session, bucket: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    monkeypatch.setattr(handlers, "get_sessionmaker", lambda: lambda: BorrowedSession(db))
    monkeypatch.setattr(handlers, "ALBUM_WAIT_S", 0.05)

    bot = Bot("123456:TEST-TOKEN")
    bot._bot_user = User(id=1, first_name="SAQ", is_bot=True, username="saq_test_bot")  # what `get_me` would set
    application = Application.builder().bot(bot).build()
    client = Redis.from_url(REDIS_URL)
    prefix = f"test-bot-handlers-{id(application)}:"
    secret = "test-secret-test-secret-test-secret-0123456789"
    application.bot_data["limiter"] = RateLimiter(client, secret, 100, prefix)
    application.bot_data["search_limiter"] = RateLimiter(client, secret, 100, f"{prefix}search:")
    application.bot_data["albums"] = {}
    handlers.register(application)
    harness = Harness(application)

    async def send_message(self: Bot, chat_id: int, text: str, reply_markup: Any = None, **kwargs: Any) -> None:
        buttons = (
            [(b.text, str(b.callback_data)) for row in reply_markup.inline_keyboard for b in row]
            if reply_markup
            else []
        )
        harness.sent.append(Sent(chat_id, text, buttons))

    async def nothing(self: Bot, *args: Any, **kwargs: Any) -> None:
        return None

    async def get_file(self: Bot, file_id: str, **kwargs: Any) -> FakeFile:
        return FakeFile(file_id)

    monkeypatch.setattr(Bot, "send_message", send_message)
    monkeypatch.setattr(Bot, "answer_callback_query", nothing)
    monkeypatch.setattr(Bot, "initialize", nothing)
    monkeypatch.setattr(Bot, "shutdown", nothing)
    monkeypatch.setattr(Bot, "get_file", get_file)
    yield harness
    for key in client.scan_iter(f"{prefix}*"):
        client.delete(key)
    client.close()


def run(harness: Harness, scenario: Callable[[Harness], Awaitable[None]]) -> None:
    async def main() -> None:
        await harness.application.initialize()
        await scenario(harness)
        await harness.application.shutdown()

    asyncio.run(main())


def citizen_ads(db: Session) -> list[AdPost]:
    return list(db.scalars(select(AdPost).where(AdPost.origin == AdOrigin.citizen).order_by(AdPost.id)))


def test_start_offers_the_cities_and_the_privacy_note(harness: Harness, world: World) -> None:
    async def scenario(h: Harness) -> None:
        await h.send("/start", entities=[{"type": "bot_command", "offset": 0, "length": 6}])
        assert "не сохраняем ваше имя, username и номер телефона" in h.last
        labels = [label for label, _ in h.sent[-1].buttons]
        assert labels == sorted(labels)
        assert {"Усть-Каменогорск", "Семей"} <= set(labels)

    run(harness, scenario)


def test_kazakh_client_gets_kazakh_texts(harness: Harness, world: World) -> None:
    async def scenario(h: Harness) -> None:
        await h.send("/start", lang="kk", entities=[{"type": "bot_command", "offset": 0, "length": 6}])
        assert "Сәлеметсіз бе" in h.last
        await h.press(h.button("Семей"), lang="kk")
        assert h.sent[-1].buttons[0][0] == "Жарнама туралы хабарлау"

    run(harness, scenario)


def test_message_before_the_city_is_chosen_asks_for_start(harness: Harness, world: World, db: Session) -> None:
    async def scenario(h: Harness) -> None:
        await h.send("Акция на квартиры")
        assert "/start" in h.last

    run(harness, scenario)
    assert citizen_ads(db) == []


def test_text_with_a_link_becomes_a_report(harness: Harness, world: World, db: Session) -> None:
    link = "https://www.instagram.com/p/AbC123/"
    text = f"Бронь квартир {link} до конца месяца"

    async def scenario(h: Harness) -> None:
        await h.open_menu("report")
        await h.send(text, entities=[{"type": "url", "offset": 14, "length": len(link)}])

    run(harness, scenario)

    ad = citizen_ads(db)[0]
    assert (ad.text, ad.url, ad.platform, ad.territory_id) == (text, link, Platform.instagram, world.ust.id)
    assert ad.capture_status is CaptureStatus.pending
    assert harness.last == f"Спасибо! Сообщение №{ad.id} передано специалистам МИО."
    assert [label for label, _ in harness.sent[-1].buttons] == [
        "Сообщить о рекламе",
        "Пожаловаться на ЖК",
        "Проверить ЖК",
    ]


def test_link_to_another_site_stays_in_the_text_and_is_not_captured(
    harness: Harness, world: World, db: Session
) -> None:
    """The capture browser opens only the public platforms: a citizen's link to any other address is not sent there."""
    link = "http://127.0.0.1:8000/admin"
    text = f"Бронь квартир {link}"

    async def scenario(h: Harness) -> None:
        await h.open_menu("report")
        await h.send(text, entities=[{"type": "url", "offset": 14, "length": len(link)}])

    run(harness, scenario)

    ad = citizen_ads(db)[0]
    assert (ad.text, ad.url, ad.platform, ad.capture_status) == (text, None, Platform.other, None)
    assert harness.last == f"Спасибо! Сообщение №{ad.id} передано специалистам МИО."


def test_forwarded_channel_post_is_reported_by_its_link(harness: Harness, world: World, db: Session) -> None:
    async def scenario(h: Harness) -> None:
        await h.open_menu("report", city="Семей")
        await h.send(
            "Старт продаж, бронь 100 000",
            forward_origin={"type": "channel", "date": 1760000000, "chat": CHANNEL, "message_id": 77},
        )

    run(harness, scenario)

    ad = citizen_ads(db)[0]
    assert (ad.url, ad.platform, ad.territory_id) == (
        "https://t.me/novostroyki_vko/77",
        Platform.telegram,
        world.semey.id,
    )


@pytest.mark.filterwarnings("ignore::telegram.warnings.PTBUserWarning")
def test_album_is_one_report_with_all_photos(harness: Harness, world: World, db: Session) -> None:
    def photo_message(number: int) -> dict[str, Any]:
        return {
            "media_group_id": "album-1",
            "photo": [
                {
                    "file_id": f"small-{number}",
                    "file_unique_id": f"s{number}",
                    "width": 90,
                    "height": 90,
                    "file_size": 900,
                },
                {
                    "file_id": f"large-{number}",
                    "file_unique_id": f"l{number}",
                    "width": 800,
                    "height": 800,
                    "file_size": 9000,
                },
            ],
        }

    async def scenario(h: Harness) -> None:
        await h.open_menu("report")
        await h.send(**photo_message(1))
        await h.send(**photo_message(2), caption="Рассрочка без процентов")
        await h.send(**photo_message(3))
        assert "Спасибо" not in h.texts  # the album is not complete yet
        await asyncio.sleep(0.4)

    run(harness, scenario)

    [ad] = citizen_ads(db)
    assert ad.text == "Рассрочка без процентов"
    assert db.scalar(select(func.count()).select_from(Evidence).where(Evidence.ad_post_id == ad.id)) == 3
    assert harness.texts.count("Спасибо") == 1


def test_reports_are_limited_per_citizen(harness: Harness, world: World, db: Session) -> None:
    harness.application.bot_data["limiter"]._limit = 1

    async def scenario(h: Harness) -> None:
        await h.open_menu("report")
        await h.send("Первая реклама")
        assert "Спасибо" in h.last
        await h.press("menu:report")
        await h.send("Вторая реклама")
        assert "слишком много сообщений" in h.last

    run(harness, scenario)

    assert [ad.text for ad in citizen_ads(db)] == ["Первая реклама"]


def test_searches_are_limited_per_citizen(harness: Harness, world: World, db: Session) -> None:
    make_object(db, world.ust, "ЖК Самал Парк")
    harness.application.bot_data["search_limiter"]._limit = 2

    async def scenario(h: Harness) -> None:
        await h.open_menu("complaint")
        await h.send("самал")
        assert [label for label, _ in h.sent[-1].buttons] == ["ЖК Самал Парк", "Нет в списке"]
        await h.send("самал парк")
        assert [label for label, _ in h.sent[-1].buttons] == ["ЖК Самал Парк", "Нет в списке"]
        await h.send("самал")
        assert "слишком много сообщений" in h.last and h.sent[-1].buttons == []

    run(harness, scenario)


def test_facts_of_a_complex_are_limited_like_searches(harness: Harness, world: World, db: Session) -> None:
    make_object(db, world.ust, "ЖК Самал Парк")
    harness.application.bot_data["search_limiter"]._limit = 1

    async def scenario(h: Harness) -> None:
        await h.open_menu("check")
        await h.send("самал")  # the one allowed action
        pick = h.button("ЖК Самал Парк")
        await h.press(pick)
        assert "слишком много сообщений" in h.last
        assert "ЖК «ЖК Самал Парк»" not in h.texts

    run(harness, scenario)


def test_searches_do_not_use_up_the_limit_of_reports(harness: Harness, world: World, db: Session) -> None:
    make_object(db, world.ust, "ЖК Самал Парк")
    harness.application.bot_data["limiter"]._limit = 1

    async def scenario(h: Harness) -> None:
        await h.open_menu("check")
        for _ in range(3):
            await h.send("самал")
            assert "ЖК Самал Парк" in [label for label, _ in h.sent[-1].buttons]
        await h.press("menu:report")
        await h.send("Реклама")
        assert "Спасибо" in h.last

    run(harness, scenario)


def test_complaint_about_a_listed_complex(harness: Harness, world: World, db: Session) -> None:
    obj = make_object(db, world.ust, "ЖК Самал Парк")
    make_object(db, world.semey, "ЖК Самал Семей")

    async def scenario(h: Harness) -> None:
        await h.open_menu("complaint")
        await h.send("самал парк")
        assert [label for label, _ in h.sent[-1].buttons] == ["ЖК Самал Парк", "Нет в списке"]
        await h.press(h.button("ЖК Самал Парк"))
        assert "ЖК Самал Парк" in h.last
        await h.send("Стройка стоит второй год")

    run(harness, scenario)

    complaint = db.scalars(select(Complaint).where(Complaint.object_id == obj.id)).one()
    assert (complaint.source, complaint.summary, complaint.is_verified) == (
        ComplaintSource.telegram,
        "Стройка стоит второй год",
        False,
    )
    assert "зарегистрирована" in harness.last
    assert db.scalar(select(func.count()).select_from(Notification).where(Notification.entity_id == obj.id)) == 2


def test_complaint_needs_a_listed_complex(harness: Harness, world: World, db: Session) -> None:
    make_object(db, world.ust, "ЖК Самал Парк")

    async def scenario(h: Harness) -> None:
        await h.open_menu("complaint")
        await h.send("совсем другой жк")
        assert "ничего не нашлось" in h.last
        await h.press(h.button("Нет в списке"))
        assert "e-Otinish" in h.last

    run(harness, scenario)

    assert db.scalar(select(func.count()).select_from(Complaint)) == 0


def test_check_answers_with_facts_only(harness: Harness, world: World, db: Session) -> None:
    make_object(db, world.ust, "ЖК Самал Парк", score=87, is_demo=True)

    async def scenario(h: Harness) -> None:
        await h.open_menu("check")
        await h.send("Самал")
        await h.press(h.button("ЖК Самал Парк"))

    run(harness, scenario)

    assert "ЖК «ЖК Самал Парк»" in harness.last
    assert "Не вносите деньги" in harness.last
    assert "демонстрационные" not in harness.last
    assert "87" not in harness.last


def test_check_of_an_unknown_complex_points_to_the_portal(harness: Harness, world: World) -> None:
    async def scenario(h: Harness) -> None:
        await h.open_menu("check")
        await h.send("что-то")
        await h.press(h.button("Нет в списке"))
        assert "homeportal.kz" in h.last

    run(harness, scenario)


def test_failure_gets_a_neutral_answer_without_the_exception_text(
    harness: Harness, world: World, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> service.ReportResult:
        raise RuntimeError("password=hunter2 leaked")

    monkeypatch.setattr(service, "submit_citizen_report", broken)

    async def scenario(h: Harness) -> None:
        await h.open_menu("report")
        await h.send("Реклама")
        assert h.last == "Не удалось обработать сообщение, попробуйте позже"

    run(harness, scenario)

    assert "hunter2" not in harness.texts
