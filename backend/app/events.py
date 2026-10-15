import logging

from app.config import get_settings
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def object_changed(object_id: int) -> None:
    """Ask the risk module to recalculate an object. Call after the change is committed.

    A broker outage must not fail a request whose data is already saved, so it is logged;
    the daily `risk.sweep_due` picks the object up on its next scheduled check.
    """
    if not get_settings().events_enabled:
        return
    try:
        celery_app.send_task("risk.recalc_object", args=[object_id], queue="score")
    except Exception:
        logger.exception("Failed to enqueue risk.recalc_object for object %s", object_id)
