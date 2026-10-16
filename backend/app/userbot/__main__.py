"""Entry point of the Telegram userbot: `python -m app.userbot login` (once, by QR code), then `... run`."""

import argparse
import asyncio
import getpass
import logging

import qrcode
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.custom.qrlogin import QRLogin

from app.config import Settings, get_settings
from app.userbot.watch import run

QR_ATTEMPTS = 5
NOT_CONFIGURED = (
    "Юзербот выключен: задайте TELEGRAM_API_ID и TELEGRAM_API_HASH в .env "
    "(получить на https://my.telegram.org → API development tools) и COLLECT_TELEGRAM_ENABLED=true"
)


def client_of(settings: Settings) -> TelegramClient:
    client = TelegramClient(settings.userbot_session, settings.telegram_api_id, settings.telegram_api_hash)
    # The session file would keep the id, name, username and phone of every member whose message was seen.
    client.session.save_entities = False
    return client


def show_qr(qr: QRLogin) -> None:
    code = qrcode.QRCode()
    code.add_data(qr.url)
    code.print_ascii(invert=True)
    print("Telegram → Настройки → Устройства → Подключить устройство → отсканируйте код выше.")


async def login(settings: Settings) -> None:
    client = client_of(settings)
    await client.connect()
    try:
        if await client.is_user_authorized():
            print("Уже авторизован, повторный вход не нужен.")
            return
        qr = await client.qr_login()
        for _ in range(QR_ATTEMPTS):
            show_qr(qr)
            try:
                await qr.wait()
                break
            except TimeoutError:
                await qr.recreate()
            except SessionPasswordNeededError:
                await client.sign_in(password=getpass.getpass("Пароль двухэтапной проверки (облачный пароль): "))
                break
        else:
            raise SystemExit("Код не отсканирован за отведённое время, запустите вход заново")
        me = await client.get_me()
        print(f"Вход выполнен: {getattr(me, 'first_name', '')}. Сессия сохранена.")
    finally:
        await client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.userbot")
    parser.add_argument("command", nargs="?", choices=["login", "run"], default="run")
    command = parser.parse_args().command
    settings = get_settings()
    if not (settings.telegram_api_id > 0 and settings.telegram_api_hash.strip()):
        raise SystemExit(NOT_CONFIGURED)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if command == "login":
        asyncio.run(login(settings))
    else:
        if not settings.userbot_configured:
            raise SystemExit(NOT_CONFIGURED)
        asyncio.run(run(settings, client_of(settings)))


main()
