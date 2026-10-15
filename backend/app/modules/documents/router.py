from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile

from app import audit, storage
from app.deps import ScopeDep, SessionDep, StaffUser
from app.errors import api_error
from app.events import object_changed
from app.models import AppUser, Document
from app.models.enums import CheckSource, CheckStatus, DocType, EvidenceKind
from app.modules.documents.schemas import DocumentOut, DocumentUpdate
from app.modules.objects.service import get_object_in_scope
from app.storage import EvidenceLink
from app.uploads import SCAN_TYPES, read_upload

router = APIRouter(tags=["documents"])

_CHECKED_STATUSES = {CheckStatus.confirmed, CheckStatus.not_found}


def _get_document(session: SessionDep, scope: ScopeDep, document_id: int) -> Document:
    document = session.get(Document, document_id)
    if document is not None:
        get_object_in_scope(session, scope, document.object_id)  # 404 when outside the territory
        return document
    raise api_error(404, "document_not_found", "Документ не найден")


def _mark_checked(document: Document, user: AppUser) -> None:
    if document.check_status in _CHECKED_STATUSES:
        document.checked_by = user.id
        document.checked_at = datetime.now(UTC)
    else:
        document.checked_by = None
        document.checked_at = None


def _attach_scan(session: SessionDep, document: Document, upload: UploadFile, user: AppUser) -> int:
    data, content_type = read_upload(upload, SCAN_TYPES)
    evidence = storage.put_evidence(
        session,
        data,
        EvidenceKind.document_scan,
        content_type,
        link=EvidenceLink(document_id=document.id),
        created_by=user.id,
    )
    return evidence.id


@router.post("/objects/{object_id}/documents", response_model=DocumentOut, status_code=201)
def create_document(
    object_id: int,
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    request: Request,
    doc_type: Annotated[DocType, Form()],
    number: Annotated[str | None, Form(max_length=128)] = None,
    issued_at: Annotated[date | None, Form()] = None,
    issuer: Annotated[str | None, Form(max_length=255)] = None,
    check_status: Annotated[CheckStatus, Form()] = CheckStatus.checking,
    check_source: Annotated[CheckSource | None, Form()] = None,
    note: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> DocumentOut:
    obj = get_object_in_scope(session, scope, object_id)
    document = Document(
        object_id=obj.id,
        doc_type=doc_type,
        number=number,
        issued_at=issued_at,
        issuer=issuer,
        check_status=check_status,
        check_source=check_source,
        note=note,
    )
    _mark_checked(document, user)
    session.add(document)
    session.flush()
    evidence_id = _attach_scan(session, document, file, user) if file is not None and file.filename else None
    session.refresh(document)
    audit.record(
        session,
        user,
        "document.create",
        "document",
        document.id,
        None,
        {**audit.snapshot(document), "evidence_id": evidence_id},
        request,
    )
    result = DocumentOut.model_validate(document)
    session.commit()
    object_changed(obj.id)
    return result


@router.patch("/documents/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: int, body: DocumentUpdate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> DocumentOut:
    document = _get_document(session, scope, document_id)
    before = audit.snapshot(document)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("doc_type") is None and "doc_type" in changes:
        raise api_error(422, "validation_error", "Тип документа не может быть пустым")
    if changes.get("check_status") is None and "check_status" in changes:
        raise api_error(422, "validation_error", "Статус проверки не может быть пустым")
    for field, value in changes.items():
        setattr(document, field, value)
    if "check_status" in changes:
        _mark_checked(document, user)
    session.flush()
    session.refresh(document)
    audit.record(session, user, "document.update", "document", document.id, before, audit.snapshot(document), request)
    result = DocumentOut.model_validate(document)
    session.commit()
    object_changed(document.object_id)
    return result


@router.post("/documents/{document_id}/evidence", response_model=DocumentOut, status_code=201)
def add_document_evidence(
    document_id: int,
    file: Annotated[UploadFile, File()],
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    request: Request,
) -> DocumentOut:
    """Attach another scan or verification screenshot to an existing document."""
    document = _get_document(session, scope, document_id)
    evidence_id = _attach_scan(session, document, file, user)
    session.refresh(document)
    audit.record(
        session, user, "document.add_evidence", "document", document.id, None, {"evidence_id": evidence_id}, request
    )
    result = DocumentOut.model_validate(document)
    session.commit()
    return result
