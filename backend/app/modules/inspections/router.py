from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from sqlalchemy import select

from app import audit, storage
from app.deps import ScopeDep, SessionDep, StaffUser
from app.errors import api_error
from app.events import object_changed
from app.geo import make_point
from app.models import Inspection
from app.models.enums import EvidenceKind
from app.modules.inspections.schemas import InspectionOut
from app.modules.objects.service import get_object_in_scope
from app.storage import EvidenceLink
from app.uploads import PHOTO_TYPES, read_upload

router = APIRouter(tags=["inspections"])

MAX_PHOTOS = 20
MAX_TOTAL_PHOTO_BYTES = 100 * 1024 * 1024


@router.post("/objects/{object_id}/inspections", response_model=InspectionOut, status_code=201)
def create_inspection(
    object_id: int,
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    request: Request,
    inspected_at: Annotated[date, Form()],
    readiness_pct: Annotated[int, Form(ge=0, le=100)],
    lat: Annotated[float | None, Form(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Form(ge=-180, le=180)] = None,
    note: Annotated[str | None, Form()] = None,
    photos: Annotated[list[UploadFile] | None, File()] = None,
    photos_brackets: Annotated[list[UploadFile] | None, File(alias="photos[]")] = None,
) -> InspectionOut:
    if (lat is None) != (lon is None):
        raise api_error(422, "validation_error", "Координаты lat и lon указываются вместе")
    obj = get_object_in_scope(session, scope, object_id)
    uploads = [upload for upload in (*(photos or []), *(photos_brackets or [])) if upload.filename]
    if len(uploads) > MAX_PHOTOS:
        raise api_error(422, "too_many_photos", f"Не более {MAX_PHOTOS} фотографий за одну фотофиксацию")
    # Validate every file before anything is written to storage.
    payloads: list[tuple[bytes, str]] = []
    total_bytes = 0
    for upload in uploads:
        data, content_type = read_upload(upload, PHOTO_TYPES)
        total_bytes += len(data)
        if total_bytes > MAX_TOTAL_PHOTO_BYTES:
            raise api_error(413, "request_too_large", "Суммарный размер фотографий больше 100 МБ")
        payloads.append((data, content_type))

    inspection = Inspection(
        object_id=obj.id,
        inspected_at=inspected_at,
        readiness_pct=readiness_pct,
        location=make_point(lat, lon),
        inspector_id=user.id,
        note=note,
    )
    session.add(inspection)
    session.flush()
    evidence_ids = [
        storage.put_evidence(
            session,
            data,
            EvidenceKind.photo,
            content_type,
            link=EvidenceLink(inspection_id=inspection.id),
            created_by=user.id,
        ).id
        for data, content_type in payloads
    ]

    # The object's actual readiness always follows the most recent inspection by date.
    latest = session.scalar(
        select(Inspection)
        .where(Inspection.object_id == obj.id)
        .order_by(Inspection.inspected_at.desc(), Inspection.id.desc())
        .limit(1)
    )
    if latest is not None:
        obj.readiness_actual_pct = latest.readiness_pct
    session.flush()
    session.refresh(inspection)
    audit.record(
        session,
        user,
        "inspection.create",
        "inspection",
        inspection.id,
        None,
        {**audit.snapshot(inspection), "evidence_ids": evidence_ids},
        request,
    )
    result = InspectionOut.model_validate(inspection)
    session.commit()
    object_changed(obj.id)
    return result
