import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import storage
from app.config import get_settings
from app.deps import SessionDep
from app.errors import api_error, register_error_handlers
from app.modules.activity.router import router as activity_router
from app.modules.ads.router import router as ads_router
from app.modules.assignments.router import router as assignments_router
from app.modules.assistant.router import router as assistant_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.complaints.router import router as complaints_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.developers.router import router as developers_router
from app.modules.documents.router import router as documents_router
from app.modules.evidence.router import router as evidence_router
from app.modules.graph.router import router as graph_router
from app.modules.holidays.router import router as holidays_router
from app.modules.inspections.router import router as inspections_router
from app.modules.linked_entities.router import router as linked_entities_router
from app.modules.nlp.router import router as nlp_router
from app.modules.notifications.router import router as notifications_router
from app.modules.objects.router import router as objects_router
from app.modules.registry_sync.router import router as registry_sync_router
from app.modules.risk.router import router as risk_router
from app.modules.search.router import router as search_router
from app.modules.settings.router import router as settings_router
from app.modules.signals.router import router as signals_router
from app.modules.territories.router import router as territories_router
from app.modules.users.router import router as users_router
from app.modules.vision.limits import UploadSizeLimitMiddleware
from app.modules.vision.router import router as vision_router

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
STORAGE_RETRIES = 10
STORAGE_RETRY_DELAY_S = 2


def _ensure_storage() -> None:
    """Create the evidence bucket; MinIO may still be starting, so retry briefly."""
    for attempt in range(1, STORAGE_RETRIES + 1):
        try:
            storage.ensure_bucket()
            return
        except RuntimeError:
            raise  # existing bucket without Object Lock: retrying will not help
        except Exception:
            if attempt == STORAGE_RETRIES:
                raise
            logger.warning("Storage not ready (attempt %s/%s), retrying", attempt, STORAGE_RETRIES, exc_info=True)
            time.sleep(STORAGE_RETRY_DELAY_S)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _ensure_storage()
    yield


app = FastAPI(title="SAQ QURYLYS", version="0.1.0", lifespan=lifespan)
register_error_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix=API_PREFIX)


@api.get("/health", tags=["health"])
def health(session: SessionDep) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.exception("Health check: database unavailable")
        raise api_error(503, "db_unavailable", "База данных недоступна") from exc
    return {"status": "ok"}


for module_router in (
    auth_router,
    users_router,
    territories_router,
    settings_router,
    holidays_router,
    developers_router,
    objects_router,
    search_router,
    documents_router,
    inspections_router,
    complaints_router,
    linked_entities_router,
    evidence_router,
    registry_sync_router,
    notifications_router,
    audit_router,
    activity_router,
    # Implemented by other modules; routers are empty stubs until then.
    dashboard_router,
    graph_router,
    ads_router,
    nlp_router,
    risk_router,
    signals_router,
    assignments_router,
):
    api.include_router(module_router)

# Optional module: while it is off there are no /api/v1/vision routes at all (404).
if get_settings().vision_enabled:
    api.include_router(vision_router)
    app.add_middleware(UploadSizeLimitMiddleware)

# Optional module: while it is off there are no /api/v1/assistant routes at all (404).
if get_settings().assistant_enabled:
    api.include_router(assistant_router)

app.include_router(api)
