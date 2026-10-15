import logging

from fastapi import APIRouter, Request

from app import audit
from app.config import get_settings
from app.deps import GlobalAdmin, SessionDep, StaffUser
from app.errors import api_error
from app.modules.registry_sync.schemas import SyncStarted, SyncStatus
from app.modules.registry_sync.service import load_last_sync
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/registry-sync", tags=["registry-sync"])


@router.post("/homeportal", response_model=SyncStarted, status_code=202)
def start_homeportal_sync(session: SessionDep, user: GlobalAdmin, request: Request) -> SyncStarted:
    """Queue a run of the housing portal registry sync. The result appears in `GET /registry-sync/status`."""
    try:
        task = celery_app.send_task(
            "registry.sync_homeportal", kwargs={"scheduled": False}, queue="collect", retry=False
        )
    except Exception as exc:
        logger.exception("Failed to enqueue registry.sync_homeportal")
        raise api_error(503, "queue_unavailable", "Очередь задач недоступна") from exc
    audit.record(session, user, "registry_sync.start", "registry_sync", None, None, {"task_id": task.id}, request)
    session.commit()
    return SyncStarted(task_id=task.id)


@router.get("/status", response_model=SyncStatus)
def homeportal_sync_status(session: SessionDep, user: StaffUser) -> SyncStatus:
    return SyncStatus(scheduled_enabled=get_settings().homeportal_sync_enabled, last_sync=load_last_sync(session))
