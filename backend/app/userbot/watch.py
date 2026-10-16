"""The `run` command: joins the watched public chats, reads what they said meanwhile and listens to new messages."""

import asyncio
import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial

from sqlalchemy import select
from sqlalchemy.orm import Session
from telethon import TelegramClient, events
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    InviteRequestSentError,
    RPCError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import Channel, Message, MessageEntityTextUrl, MessageMediaPhoto, PeerChannel

from app.collectors.media import MAX_PHOTO_BYTES
from app.config import Settings
from app.db import get_sessionmaker
from app.models import Phrase, SourceAccount
from app.models.enums import Platform
from app.modules.ads.service import record_collection_result
from app.modules.settings.service import load_settings
from app.userbot import service

logger = logging.getLogger(__name__)

SYNC_INTERVAL_S = 300
_USERNAME = re.compile(r"[A-Za-z0-9_]{4,64}")


class UserbotSourceError(Exception):
    """The source cannot be read; the message is shown to staff as the account's last error (short, in Russian)."""


@dataclass(frozen=True)
class Watched:
    account_id: int
    username: str
    is_channel: bool
    title: str


def albums_of(messages: Sequence[Message]) -> list[list[Message]]:
    """The messages grouped by album (`grouped_id`), in the order of their first message; the rest stay alone."""
    groups: dict[object, list[Message]] = {}
    for message in messages:
        groups.setdefault(message.grouped_id or ("single", message.id), []).append(message)
    return list(groups.values())


async def _with_session[T](work: Callable[[Session], T]) -> T:
    """Run blocking work (database, storage) in a thread with a session that lives for this call only."""

    def run_work() -> T:
        with get_sessionmaker()() as session:
            return work(session)

    return await asyncio.to_thread(run_work)


class Watcher:
    def __init__(self, client: TelegramClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings
        self._watched: dict[int, Watched] = {}  # Telegram channel id -> the source it serves
        self._chats: dict[str, Channel] = {}  # username -> chat; resolving a name is a request that Telegram limits
        self._phrases: list[Phrase] = []
        # Messages are stored one at a time: the backfill and the live handlers meet on the same posts.
        self._lock = asyncio.Lock()

    async def sync(self) -> int:
        """Join the sources that are not joined yet, read what was missed and refresh the dictionary.

        Returns the seconds Telegram asked to wait before more requests (0 when it did not).
        """

        def load(session: Session) -> tuple[list[tuple[int, str, datetime | None]], list[Phrase], datetime]:
            accounts = session.scalars(
                select(SourceAccount)
                .where(SourceAccount.is_watched, SourceAccount.platform == Platform.telegram)
                .order_by(SourceAccount.id)
            )
            window_start = datetime.now(UTC) - timedelta(days=load_settings(session).ad_window_days)
            return (
                [(account.id, account.handle, account.last_collected_at) for account in accounts],
                service.load_phrases(session),
                window_start,
            )

        accounts, self._phrases, window_start = await _with_session(load)
        joined: set[str] = set()
        async for dialog in self._client.iter_dialogs():
            chat = dialog.entity
            if isinstance(chat, Channel) and chat.username:
                self._chats[chat.username.lower()] = chat
                joined.add(chat.username.lower())
        # Public chats the account was joined to by hand: staff can add them as sources.
        unwatched = sorted(joined - {handle.lstrip("@").lower() for _, handle, _ in accounts})
        if unwatched:
            logger.info(
                "Public chats of the account that are not sources: %s", ", ".join(f"@{name}" for name in unwatched)
            )
        watched: dict[int, Watched] = {}
        wait_s = 0
        for account_id, handle, last_collected_at in accounts:
            started_at = datetime.now(UTC)
            error: str | None = None
            try:
                chat = await self._join(handle.lstrip("@").lower(), joined)
                watched[chat.id] = Watched(account_id, chat.username.lower(), bool(chat.broadcast), chat.title)
                await self._backfill(chat, watched[chat.id], last_collected_at or window_start)
            except FloodWaitError as exc:
                # Not the source's fault: the rest waits for the next sync, after the pause Telegram asked for.
                logger.warning("Telegram asks to wait %s s", exc.seconds)
                wait_s = exc.seconds
                break
            except UserbotSourceError as exc:
                error = str(exc)
            except Exception:
                logger.exception("Reading source account %s failed", account_id)
                error = "Непредвиденная ошибка сбора, подробности в журнале сервера"
            await _with_session(partial(self._record, account_id=account_id, started_at=started_at, error=error))
        # After a stop the sources not reached keep what they had, so that their live messages are still read.
        self._watched = {**self._watched, **watched} if wait_s else watched
        return wait_s

    @staticmethod
    def _record(session: Session, account_id: int, started_at: datetime, error: str | None) -> None:
        account = session.get(SourceAccount, account_id)
        if account is not None:
            record_collection_result(session, account, started_at, error)
            session.commit()

    async def _join(self, username: str, joined: set[str]) -> Channel:
        """The public chat of the name, joined when it is not yet."""
        if not _USERNAME.fullmatch(username):
            raise UserbotSourceError("Некорректное имя канала Telegram")
        chat = self._chats.get(username)
        if chat is None:
            try:
                resolved = await self._client.get_entity(username)
            except (UsernameNotOccupiedError, UsernameInvalidError, ValueError) as exc:
                raise UserbotSourceError("Канал или группа не найдены в Telegram") from exc
            if not isinstance(resolved, Channel) or not resolved.username:
                raise UserbotSourceError("Это не публичный канал или группа")
            chat = self._chats[username] = resolved
        if username in joined:
            return chat
        try:
            await self._client(JoinChannelRequest(chat))
        except FloodWaitError:
            raise
        except (ChannelPrivateError, InviteRequestSentError) as exc:
            raise UserbotSourceError("Чат закрытый: поддерживаются только публичные каналы и группы") from exc
        except RPCError as exc:
            logger.warning("Joining %s failed: %s", username, exc)
            raise UserbotSourceError("Telegram не разрешил вступить в чат") from exc
        joined.add(username)
        await asyncio.sleep(self._settings.userbot_join_delay_s)
        return chat

    async def _backfill(self, chat: Channel, watched: Watched, since: datetime) -> None:
        """Store the messages newer than `since`; a failure to store one fails the source, so it is read again."""
        missed: list[Message] = []
        async for message in self._client.iter_messages(chat, limit=self._settings.userbot_backfill_limit):
            if message.date <= since:
                break
            if isinstance(message, Message):  # not a service message (a joined member, a changed photo)
                missed.append(message)
        for album in reversed(albums_of(missed)):
            await self.handle(album, watched)

    async def on_message(self, event: events.NewMessage.Event | events.MessageEdited.Event) -> None:
        message = event.message
        # An album arrives as one event of its own; an edit of its caption is the edit of that message.
        if message.grouped_id and (not message.message or not isinstance(event, events.MessageEdited.Event)):
            return
        await self._live([message])

    async def on_album(self, event: events.Album.Event) -> None:
        await self._live(event.messages)

    async def _live(self, messages: Sequence[Message]) -> None:
        peer = messages[0].peer_id
        # Private dialogs and small groups have no channel peer: they are never read.
        watched = self._watched.get(peer.channel_id) if isinstance(peer, PeerChannel) else None
        if watched is None:
            return
        try:
            await self.handle(messages, watched)
        except Exception:
            logger.exception("A message of source account %s was not stored", watched.account_id)

    async def handle(self, messages: Sequence[Message], watched: Watched) -> None:
        """Store a message, or an album as one post: of the message that has the caption, else of the first."""
        messages = sorted(messages, key=lambda message: message.id)
        main = next((message for message in messages if message.message), messages[0])
        photo_messages = [message for message in messages if isinstance(message.media, MessageMediaPhoto)]
        post = await asyncio.to_thread(
            service.build_post,
            username=watched.username,
            message_id=main.id,
            text=main.message or "",
            links=[entity.url for entity, _ in main.get_entities_text(MessageEntityTextUrl) if entity.url],
            published_at=main.date,
            has_photo=bool(photo_messages),
            is_channel=watched.is_channel,
            channel_title=watched.title,
            phrases=self._phrases,
        )
        if post is None:
            return
        async with self._lock:
            known = await _with_session(lambda session: service.is_stored(session, watched.username, main.id))
            photos: list[bytes] = []
            for message in [] if known else photo_messages:
                if (message.file.size if message.file else 0) > MAX_PHOTO_BYTES:
                    continue
                data = await self._client.download_media(message, file=bytes)
                if data:
                    photos.append(data)
            await _with_session(
                lambda session: service.store_message(
                    session, watched.account_id, post, photos, capture=watched.is_channel
                )
            )


async def run(settings: Settings, client: TelegramClient) -> None:
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise SystemExit(
                "Юзербот не авторизован. Сначала: docker compose --profile userbot run --rm userbot "
                "python -m app.userbot login"
            )
        watcher = Watcher(client, settings)
        client.add_event_handler(watcher.on_message, events.NewMessage())
        client.add_event_handler(watcher.on_message, events.MessageEdited())
        client.add_event_handler(watcher.on_album, events.Album())
        while True:
            if not client.is_connected():
                try:
                    await client.connect()
                except Exception as exc:
                    # The container restarts and connects again.
                    raise SystemExit("Нет соединения с Telegram, юзербот остановлен") from exc
            wait_s = 0
            try:
                wait_s = await watcher.sync()
            except Exception:
                logger.exception("The sync of the watched chats failed")
            await asyncio.sleep(max(SYNC_INTERVAL_S, wait_s))
    finally:
        await client.disconnect()
