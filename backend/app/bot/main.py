"""Entry point of the citizen bot: `python -m app.bot` (long polling)."""

import logging

from redis import Redis
from telegram import Update
from telegram.ext import Application

from app.bot import handlers
from app.bot.ratelimit import RateLimiter
from app.config import get_settings

SEARCHES_PER_HOUR = 60


def build_application(token: str) -> Application:
    settings = get_settings()
    application = Application.builder().token(token).build()
    redis = Redis.from_url(settings.redis_url)
    application.bot_data["limiter"] = RateLimiter(redis, settings.jwt_secret, settings.bot_reports_per_hour)
    # Searches and facts do not write anything, but updates are handled one after another: one citizen must not
    # be able to keep the bot busy for the others.
    application.bot_data["search_limiter"] = RateLimiter(
        redis, settings.jwt_secret, SEARCHES_PER_HOUR, prefix="bot:search:"
    )
    application.bot_data["albums"] = {}
    handlers.register(application)
    return application


def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is empty: create a bot with @BotFather and put its token into .env "
            "(see docs/DEVELOPMENT.md)"
        )
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx logs every request at INFO, and the URL of a Telegram request contains the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    build_application(settings.telegram_bot_token).run_polling(allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY])
