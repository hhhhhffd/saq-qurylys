"""Telegram handlers of the citizen bot. They translate updates into calls of `service`; the state of a dialog is
kept in `context.user_data`, in memory only (nothing about a citizen is persisted)."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    MessageEntity,
    MessageOriginChannel,
    Update,
)
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.bot import service
from app.bot.ratelimit import RateLimiter
from app.bot.texts import pick_language, render_facts, t
from app.db import get_sessionmaker

logger = logging.getLogger(__name__)

# The messages of an album arrive as separate updates; the album is processed this long after the last of them.
ALBUM_WAIT_S = 2.0

# Keys of `context.user_data` and the steps of a dialog.
CITY = "city_id"
MODE = "mode"
OBJECT = "object_id"
REPORT, COMPLAINT_NAME, COMPLAINT_TEXT, CHECK_NAME = "report", "complaint_name", "complaint_text", "check_name"
MENU_MODES = {"report": REPORT, "complaint": COMPLAINT_NAME, "check": CHECK_NAME}
NOT_LISTED = 0  # the id of the «Нет в списке» button


@dataclass(frozen=True)
class Sender:
    chat_id: int
    user_id: int
    lang: str


@dataclass
class Album:
    sender: Sender
    city_id: int
    messages: list[Message]
    arrived: asyncio.Event = field(default_factory=asyncio.Event)  # set by every further message


async def _with_session[T](work: Callable[[Session], T]) -> T:
    """Run blocking work (database, storage) in a thread with a session that lives for this call only."""

    def run() -> T:
        with get_sessionmaker()() as session:
            return work(session)

    return await asyncio.to_thread(run)


def _sender(update: Update) -> Sender:
    chat, user = update.effective_chat, update.effective_user
    if chat is None or user is None:
        raise RuntimeError("update without a chat or a user")
    return Sender(chat.id, user.id, pick_language(user.language_code))


def _state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    if context.user_data is None:
        raise RuntimeError("update without a user")
    return context.user_data


async def _callback_value(update: Update) -> str:
    """Acknowledge a pressed button and return the part of its data after the colon."""
    query = update.callback_query
    if query is None or query.data is None:
        raise RuntimeError("update without callback data")
    await query.answer()
    return query.data.partition(":")[2]


async def _say(
    bot: Bot, sender: Sender, key: str, markup: InlineKeyboardMarkup | None = None, **fields: object
) -> None:
    await bot.send_message(sender.chat_id, t(sender.lang, key, **fields), reply_markup=markup)


def _menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t(lang, f"menu_{action}"), callback_data=f"menu:{action}")] for action in MENU_MODES]
    )


# ---------------------------------------------------------------- start, city, menu


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sender = _sender(update)
    _state(context).clear()
    cities = await _with_session(service.list_cities)
    if not cities:
        await _say(context.bot, sender, "no_cities")
        return
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(city.name, callback_data=f"city:{city.id}")] for city in cities]
    )
    await context.bot.send_message(
        sender.chat_id, f"{t(sender.lang, 'greeting')}\n\n{t(sender.lang, 'choose_city')}", reply_markup=keyboard
    )


async def on_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    city_id = int(await _callback_value(update))
    sender, state = _sender(update), _state(context)
    if await _with_session(lambda session: service.find_city(session, city_id)) is None:
        await _say(context.bot, sender, "stale")
        return
    state.clear()
    state[CITY] = city_id
    await _say(context.bot, sender, "menu", _menu(sender.lang))


async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mode = MENU_MODES[await _callback_value(update)]
    sender, state = _sender(update), _state(context)
    if CITY not in state:
        await _say(context.bot, sender, "need_start")
        return
    state[MODE] = mode
    await _say(context.bot, sender, f"{mode}_prompt")


# ---------------------------------------------------------------- messages


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    sender, state = _sender(update), _state(context)
    albums: dict[tuple[int, str], Album] = context.application.bot_data["albums"]
    album_key = (sender.chat_id, message.media_group_id or "")
    if message.media_group_id and album_key in albums:
        albums[album_key].messages.append(message)
        albums[album_key].arrived.set()
        return
    if CITY not in state:
        await _say(context.bot, sender, "need_start")
        return
    mode = state.get(MODE)
    if mode == REPORT:
        state[MODE] = None
        if message.media_group_id:
            albums[album_key] = Album(sender, state[CITY], [message])
            context.application.create_task(
                _flush_album(context.bot, context.application.bot_data, album_key), update=update
            )
        else:
            await _submit_report(context.bot, context.application.bot_data, sender, state[CITY], [message])
    elif mode in {COMPLAINT_NAME, CHECK_NAME}:
        await _offer_objects(context.bot, context.application.bot_data, sender, state[CITY], message)
    elif mode == COMPLAINT_TEXT:
        await _submit_complaint(context, sender, message)
    else:
        await _say(context.bot, sender, "menu", _menu(sender.lang))


async def _offer_objects(bot: Bot, shared: dict[str, Any], sender: Sender, city_id: int, message: Message) -> None:
    name = message.text
    if not name:
        await _say(bot, sender, "name_expected")
        return
    if not await _within_limit(shared, sender, "search_limiter"):
        await _say(bot, sender, "rate_limited")
        return
    matches = await _with_session(lambda session: service.search_objects(session, city_id, name))
    buttons = [[InlineKeyboardButton(match.name, callback_data=f"pick:{match.id}")] for match in matches]
    buttons.append([InlineKeyboardButton(t(sender.lang, "not_listed"), callback_data=f"pick:{NOT_LISTED}")])
    await _say(bot, sender, "search_found" if matches else "search_none", InlineKeyboardMarkup(buttons))


async def on_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    object_id = int(await _callback_value(update))
    sender, state = _sender(update), _state(context)
    mode = state.get(MODE)
    if mode not in {COMPLAINT_NAME, CHECK_NAME} or CITY not in state:
        await _say(context.bot, sender, "stale", _menu(sender.lang))
        return
    city_id = state[CITY]
    if object_id == NOT_LISTED:
        state[MODE] = None
        key = "not_listed_complaint" if mode == COMPLAINT_NAME else "not_listed_check"
        await _say(context.bot, sender, key, _menu(sender.lang))
    elif mode == CHECK_NAME:
        if not await _within_limit(context.application.bot_data, sender, "search_limiter"):
            await _say(context.bot, sender, "rate_limited", _menu(sender.lang))
            return
        facts = await _with_session(lambda session: service.object_facts(session, city_id, object_id))
        if facts is None:
            await _say(context.bot, sender, "object_missing")
            return
        state[MODE] = None
        await context.bot.send_message(
            sender.chat_id, render_facts(facts, sender.lang), reply_markup=_menu(sender.lang)
        )
    else:
        name = await _with_session(lambda session: service.object_name(session, city_id, object_id))
        if name is None:
            await _say(context.bot, sender, "object_missing")
            return
        state[MODE] = COMPLAINT_TEXT
        state[OBJECT] = object_id
        await _say(context.bot, sender, "complaint_text_prompt", name=name)


async def _submit_complaint(context: ContextTypes.DEFAULT_TYPE, sender: Sender, message: Message) -> None:
    text = (message.text or "").strip()
    if not text:
        await _say(context.bot, sender, "complaint_text_missing")
        return
    state = _state(context)
    object_id = state.pop(OBJECT)
    state[MODE] = None
    if not await _within_limit(context.application.bot_data, sender):
        await _say(context.bot, sender, "rate_limited")
        return
    name = await _with_session(lambda session: service.submit_complaint(session, object_id=object_id, text=text))
    await _say(context.bot, sender, "complaint_thanks", _menu(sender.lang), name=name)


# ---------------------------------------------------------------- report of advertising


async def _within_limit(shared: dict[str, Any], sender: Sender, kind: str = "limiter") -> bool:
    """Count one more action of the citizen against `shared[kind]`: "limiter" for reports and complaints,
    "search_limiter" for searches and the facts of a complex."""
    limiter: RateLimiter = shared[kind]
    return await asyncio.to_thread(limiter.allow, sender.user_id)


async def _flush_album(bot: Bot, shared: dict[str, Any], key: tuple[int, str]) -> None:
    """Wait until no message of the album has arrived for `ALBUM_WAIT_S`, then report the whole album."""
    album: Album = shared["albums"][key]
    while True:
        album.arrived.clear()
        try:
            await asyncio.wait_for(album.arrived.wait(), ALBUM_WAIT_S)
        except TimeoutError:
            break
    del shared["albums"][key]
    await _submit_report(bot, shared, album.sender, album.city_id, album.messages)


def _message_urls(message: Message) -> list[str]:
    urls: list[str] = []
    for entities, parse in (
        (message.entities, message.parse_entity),
        (message.caption_entities, message.parse_caption_entity),
    ):
        for entity in entities:
            if entity.type == MessageEntity.TEXT_LINK and entity.url:
                urls.append(entity.url)
            elif entity.type == MessageEntity.URL:
                urls.append(parse(entity))
    return urls


def _forwarded_url(message: Message) -> str | None:
    origin = message.forward_origin
    if isinstance(origin, MessageOriginChannel):
        return service.forwarded_post_url(origin.chat.username, origin.message_id)
    return None


async def _submit_report(
    bot: Bot, shared: dict[str, Any], sender: Sender, city_id: int, messages: list[Message]
) -> None:
    """One report from a message or from all messages of an album."""
    if not await _within_limit(shared, sender):
        await _say(bot, sender, "rate_limited")
        return
    ordered = sorted(messages, key=lambda message: message.message_id)
    text = next((message.text or message.caption for message in ordered if message.text or message.caption), "")
    forwarded = next((link for message in ordered if (link := _forwarded_url(message))), None)
    entity_urls = [link for message in ordered for link in _message_urls(message)]
    url = service.find_report_url(text or "", entity_urls, forwarded)
    photos: list[bytes] = []
    offered = 0
    for message in ordered:
        if not message.photo:
            continue
        offered += 1
        largest = max(message.photo, key=lambda size: size.width * size.height)
        if len(photos) < service.PHOTO_LIMIT and (largest.file_size or 0) <= service.PHOTO_MAX_BYTES:
            file = await bot.get_file(largest.file_id)
            photos.append(bytes(await file.download_as_bytearray()))
    try:
        result = await _with_session(
            lambda session: service.submit_citizen_report(
                session, territory_id=city_id, text=text or "", url=url, photos=photos
            )
        )
    except service.EmptyReportError:
        await _say(bot, sender, "report_empty")
        return
    if result.photos_saved < offered:
        await _say(bot, sender, "report_photos_partial", saved=result.photos_saved, offered=offered)
    await _say(bot, sender, "report_thanks", _menu(sender.lang), id=result.ad_id)


# ---------------------------------------------------------------- errors


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the failure and give the citizen a neutral answer; the text of the exception is never sent."""
    logger.error("The bot failed to handle an update", exc_info=context.error)
    if not isinstance(update, Update) or update.effective_chat is None:
        return
    language_code = update.effective_user.language_code if update.effective_user else None
    try:
        await context.bot.send_message(update.effective_chat.id, t(pick_language(language_code), "error"))
    except TelegramError:
        logger.exception("The bot could not send the error notice")


def register(application: Application) -> None:
    private = filters.ChatType.PRIVATE
    application.add_handler(CommandHandler("start", on_start, filters=private))
    application.add_handler(CallbackQueryHandler(on_city, pattern=r"^city:\d+$"))
    application.add_handler(CallbackQueryHandler(on_menu, pattern=r"^menu:(report|complaint|check)$"))
    application.add_handler(CallbackQueryHandler(on_pick, pattern=r"^pick:\d+$"))
    application.add_handler(
        MessageHandler(private & ~filters.COMMAND & (filters.TEXT | filters.PHOTO | filters.CAPTION), on_message)
    )
    application.add_error_handler(on_error)
