from typing import Annotated

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.db import get_sessionmaker
from app.deps import CurrentUser
from app.modules.assistant import service
from app.modules.assistant.schemas import AssistantConfig, ChatRequest

router = APIRouter(prefix="/assistant", tags=["assistant"])


def get_session_factory() -> service.SessionFactory:
    """The answer is streamed after the handler returned, when the request's session may already be closed, so the
    stream opens its own. A dependency (not a direct call) so tests can hand it their transactional session."""
    return get_sessionmaker()


def get_llm_client() -> httpx.Client | None:
    """None: the client creates an HTTP client of its own. Tests substitute one with a mocked transport."""
    return None


SessionFactoryDep = Annotated[service.SessionFactory, Depends(get_session_factory)]
LlmClientDep = Annotated[httpx.Client | None, Depends(get_llm_client)]


@router.get("/config", response_model=AssistantConfig)
def get_config(user: CurrentUser) -> AssistantConfig:
    settings = get_settings()
    return AssistantConfig(enabled=settings.assistant_enabled, model=settings.assistant_model)


@router.post("/chat")
def chat(
    body: ChatRequest, user: CurrentUser, session_factory: SessionFactoryDep, http: LlmClientDep
) -> StreamingResponse:
    return StreamingResponse(
        service.run_chat(body, user.id, session_factory, http),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
