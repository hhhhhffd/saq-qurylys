import logging
from typing import Any

from app.config import get_settings
from app.db import get_sessionmaker
from app.modules.registry_sync.service import sync_homeportal
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="registry.sync_homeportal")
def sync_homeportal_task(scheduled: bool = False) -> dict[str, Any] | None:
    """Beat starts it daily with `scheduled=True`; it then does nothing unless HOMEPORTAL_SYNC_ENABLED is true.
    An administrator's request (`scheduled=False`) always runs."""
    if scheduled and not get_settings().homeportal_sync_enabled:
        logger.info("registry.sync_homeportal: scheduled run skipped, HOMEPORTAL_SYNC_ENABLED is not true")
        return None
    with get_sessionmaker()() as session:
        return sync_homeportal(session).model_dump(mode="json")
