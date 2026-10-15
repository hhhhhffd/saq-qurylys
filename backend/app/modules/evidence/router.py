from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from minio.error import S3Error

from app import storage
from app.deps import CurrentUser, ScopeDep, SessionDep
from app.errors import api_error
from app.models import Evidence
from app.modules.evidence.schemas import EvidenceOut
from app.modules.evidence.service import can_access_evidence

router = APIRouter(prefix="/evidence", tags=["evidence"])


def get_accessible_evidence(session: SessionDep, user: CurrentUser, scope: ScopeDep, evidence_id: int) -> Evidence:
    evidence = session.get(Evidence, evidence_id)
    if evidence is None or not can_access_evidence(session, user, scope, evidence):
        raise api_error(404, "evidence_not_found", "Доказательство не найдено")
    return evidence


@router.get("/{evidence_id}", response_model=EvidenceOut)
def get_evidence(evidence_id: int, session: SessionDep, user: CurrentUser, scope: ScopeDep) -> Evidence:
    return get_accessible_evidence(session, user, scope, evidence_id)


@router.get("/{evidence_id}/content")
def get_evidence_content(
    evidence_id: int, session: SessionDep, user: CurrentUser, scope: ScopeDep
) -> StreamingResponse:
    evidence = get_accessible_evidence(session, user, scope, evidence_id)
    try:
        response = storage.open_evidence(evidence)
    except S3Error as exc:
        raise api_error(502, "evidence_object_missing", "Файл доказательства недоступен в хранилище") from exc
    inline = evidence.content_type in storage.INLINE_CONTENT_TYPES
    filename = f"evidence-{evidence.id}{storage.extension_for(evidence.content_type)}"
    return StreamingResponse(
        storage.stream_object(response),
        media_type=evidence.content_type,
        headers={
            "Content-Length": str(evidence.size_bytes),
            "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
            "Cache-Control": "private, max-age=3600",
            "X-Evidence-SHA256": evidence.sha256,
        },
    )
