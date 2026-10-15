"""The `run` command: joins the watched public chats, reads what they said meanwhile and listens to new messages."""

import asyncio
import logging
import re
from collections.abc import Callable
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
from telethon.tl.types import Channel, Message, MessageEntityTextUrl, PeerChannel

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
        self._phrases: list[Phrase] = []
        # Messages are stored one at a time: the backfill and the live handlers meet on the same posts.
        self._lock = asyncio.Lock()

    async def sync(self) -> None:
        """Join the sources that are not joined yet, read what was missed and refresh the dictionary."""

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
        joined = {dialog.entity.id async for dialog in self._client.iter_dialogs() if dialog.is_channel}
        watched: dict[int, Watched] = {}
        for account_id, handle, last_collected_at in accounts:
            started_at = datetime.now(UTC)
            error: str | None = None
            try:
                chat = await self._resolve(handle.lstrip("@"))
                if chat.id not in joined:
                    await self._join(chat)
                    joined.add(chat.id)
                watched[chat.id] = Watched(account_id, chat.username.lower(), bool(chat.broadcast), chat.title)
                await self._backfill(chat, watched[chat.id], last_collected_at or window_start)
            except FloodWaitError as exc:
                # Not the source's fault: the account is tried again by the next sync.
                logger.warning("Telegram asks to wait %s s", exc.seconds)
                await asyncio.sleep(exc.seconds)
                continue
            except UserbotSourceError as exc:
                error = str(exc)
            except Exception:
                logger.exception("Reading source account %s failed", account_id)
                error = "Непредвиденная ошибка сбора, подробности в журнале сервера"
            await _with_session(partial(self._record, account_id=account_id, started_at=started_at, error=error))
        self._watched = watched

    @staticmethod
    def _record(session: Session, account_id: int, started_at: datetime, error: str | None) -> None:
        account = session.get(SourceAccount, account_id)
        if account is not None:
            record_collection_result(session, account, started_at, error)
            session.commit()

    async def _resolve(self, username: str) -> Channel:
        if not _USERNAME.fullmatch(username):
            raise UserbotSourceError("Некорректное имя канала Telegram")
        try:
            chat = await self._client.get_entity(username)
        except (UsernameNotOccupiedError, UsernameInvalidError, ValueError) as exc:
            raise UserbotSourceError("Канал или группа не найдены в Telegram") from exc
        if not isinstance(chat, Channel) or not chat.username:
            raise UserbotSourceError("Это не публичный канал или группа")
        return chat

    async def _join(self, chat: Channel) -> None:
        try:
            await self._client(JoinChannelRequest(chat))
        except (ChannelPrivateError, InviteRequestSentError) as exc:
            raise UserbotSourceError("Чат закрытый: поддерживаются только публичные каналы и группы") from exc
        except RPCError as exc:
            logger.warning("Joining %s failed: %s", chat.username, exc)
            raise UserbotSourceError("Telegram не разрешил вступить в чат") from exc
        await asyncio.sleep(self._settings.userbot_join_delay_s)

    async def _backfill(self, chat: Channel, watched: Watched, since: datetime) -> None:
        async for message in self._client.iter_messages(chat, limit=self._settings.userbot_backfill_limit):
            if message.date <= since:
                break
            await self.handle(message, watched)

    async def on_message(self, event: events.NewMessage.Event | events.MessageEdited.Event) -> None:
        message = event.message
        # Private dialogs and small groups have no channel peer: they are never read.
        if not isinstance(message.peer_id, PeerChannel):
            return
        watched = self._watched.get(message.peer_id.channel_id)
        if watched is not None:
            await self.handle(message, watched)

    async def handle(self, message: Message, watched: Watched) -> None:
        text = message.message or ""
        links = [entity.url for entity, _ in message.get_entities_text(MessageEntityTextUrl) if entity.url]
        post = service.build_post(
            username=watched.username,
            message_id=message.id,
            text=text,
            links=links,
            published_at=message.date,
            has_photo=message.photo is not None,
            is_channel=watched.is_channel,
            channel_title=watched.title,
            phrases=self._phrases,
        )
        if post is None:
            return
        try:
            async with self._lock:
                known = await _with_session(lambda session: service.is_stored(session, watched.username, message.id))
                photos: list[bytes] = []
                if message.photo is not None and not known and (message.file.size or 0) <= MAX_PHOTO_BYTES:
                    photos.append(await self._client.download_media(message, file=bytes))
                await _with_session(
                    lambda session: service.store_message(
                        session, watched.account_id, post, photos, capture=watched.is_channel
                    )
                )
        except Exception:
            logger.exception("A message of source account %s was not stored", watched.account_id)


async def run(settings: Settings, client: TelegramClient) -> None:
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise SystemExit(
                "Юзербот не авторизован. Сначала: docker compose run --rm userbot python -m app.userbot login"
            )
        watcher = Watcher(client, settings)
        client.add_event_handler(watcher.on_message, events.NewMessage())
        client.add_event_handler(watcher.on_message, events.MessageEdited())
        while True:
            try:
                await watcher.sync()
            except Exception:
                logger.exception("The sync of the watched chats failed")
            await asyncio.sleep(SYNC_INTERVAL_S)
    finally:
        await client.disconnect()
