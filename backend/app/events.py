import logging
from collections.abc import Iterable

from app.config import get_settings
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def objects_changed(object_ids: Iterable[int]) -> None:
    """Ask the risk module to recalculate objects. Call after the change is committed.

    A broker outage must not fail a request whose data is already saved, so it is logged and the
    remaining ids are skipped (each attempt against a dead broker costs a connect timeout); the daily
    `risk.sweep_due` picks the objects up on their next scheduled check.
    """
    if not get_settings().events_enabled:
        return
    for object_id in dict.fromkeys(object_ids):
        try:
            celery_app.send_task("risk.recalc_object", args=[object_id], queue="score", retry=False, ignore_result=True)
        except Exception:
            logger.exception("Failed to enqueue risk.recalc_object for object %s; skipping the rest", object_id)
            return


def object_changed(object_id: int) -> None:
    objects_changed([object_id])
