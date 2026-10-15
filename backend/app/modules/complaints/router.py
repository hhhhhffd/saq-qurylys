from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import audit
from app.csv_import import ImportResult
from app.deps import ScopeDep, SessionDep, StaffUser
from app.errors import api_error
from app.events import object_changed, objects_changed
from app.models import Complaint
from app.modules.complaints import importer
from app.modules.complaints.schemas import ComplaintCreate, ComplaintOut, ComplaintUpdate
from app.modules.complaints.service import set_verified
from app.modules.objects.service import get_object_in_scope
from app.uploads import read_csv_upload

router = APIRouter(tags=["complaints"])


def _duplicate_error() -> Exception:
    return api_error(409, "complaint_exists", "Обращение с таким источником и номером уже зарегистрировано")


@router.post("/objects/{object_id}/complaints", response_model=ComplaintOut, status_code=201)
def create_complaint(
    object_id: int, body: ComplaintCreate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> Complaint:
    obj = get_object_in_scope(session, scope, object_id)
    if body.external_id and session.scalar(
        select(Complaint.id).where(Complaint.source == body.source, Complaint.external_id == body.external_id)
    ):
        raise _duplicate_error()
    complaint = Complaint(object_id=obj.id, **body.model_dump(exclude={"is_verified"}))
    set_verified(complaint, body.is_verified, user)
    session.add(complaint)
    session.flush()
    audit.record(session, user, "complaint.create", "complaint", complaint.id, None, audit.snapshot(complaint), request)
    session.commit()
    object_changed(obj.id)
    return complaint


@router.patch("/complaints/{complaint_id}", response_model=ComplaintOut)
def update_complaint(
    complaint_id: int, body: ComplaintUpdate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> Complaint:
    complaint = session.get(Complaint, complaint_id)
    if complaint is None:
        raise api_error(404, "complaint_not_found", "Обращение не найдено")
    get_object_in_scope(session, scope, complaint.object_id)
    changes = body.model_dump(exclude_unset=True)
    for field in (
        "received_at",
        "source",
        "is_collective",
        "signatories_count",
        "status",
        "confirmed_payments",
        "is_verified",
    ):
        if field in changes and changes[field] is None:
            raise api_error(422, "validation_error", "Поле не может быть пустым")
    before = audit.snapshot(complaint)
    verified = changes.pop("is_verified", None)
    for field, value in changes.items():
        setattr(complaint, field, value)
    if verified is not None:
        set_verified(complaint, verified, user)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise _duplicate_error() from exc
    audit.record(
        session, user, "complaint.update", "complaint", complaint.id, before, audit.snapshot(complaint), request
    )
    session.commit()
    object_changed(complaint.object_id)
    return complaint


@router.post("/complaints/import", response_model=ImportResult)
def import_complaints(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    request: Request,
    file: Annotated[UploadFile, File()],
) -> ImportResult:
    result, changed_object_ids = importer.import_complaints(session, scope, user, read_csv_upload(file), request)
    session.commit()
    objects_changed(sorted(changed_object_ids))
    return result
