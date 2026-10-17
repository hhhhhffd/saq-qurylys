from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, File, Query, Request, Response, UploadFile
from sqlalchemy import func, select

from app import audit
from app.csv_import import ImportResult
from app.deps import PageDep, ScopeDep, SessionDep, StaffUser
from app.events import object_changed, objects_changed
from app.geo import make_point
from app.models import AdPost, ConstructionObject, Developer, District
from app.models.enums import Zone
from app.modules.complaints.schemas import ComplaintOut
from app.modules.developers.schemas import DeveloperOut
from app.modules.documents.schemas import DocumentOut
from app.modules.inspections.schemas import InspectionOut
from app.modules.linked_entities.schemas import LinkedEntityOut
from app.modules.objects import dossier, importer
from app.modules.objects.schemas import (
    LatestScore,
    ObjectCreate,
    ObjectDetail,
    ObjectPassport,
    ObjectRow,
    ObjectUpdate,
)
from app.modules.objects.service import (
    apply_status_rules,
    check_references,
    get_object_in_scope,
    key_status_detail,
    object_rows_stmt,
)
from app.modules.risk.queries import latest_score_stmt
from app.modules.settings.service import load_settings
from app.schemas import Page
from app.uploads import read_csv_upload

router = APIRouter(prefix="/objects", tags=["objects"])


def to_row(obj: ConstructionObject, developer_name: str | None, district_name: str | None) -> ObjectRow:
    return ObjectRow(
        id=obj.id,
        code=obj.code,
        name=obj.name,
        developer_name=developer_name,
        score=obj.score,
        zone=obj.zone,
        key_status=obj.key_status,
        key_status_detail=key_status_detail(obj),
        district_name=district_name,
        lat=obj.lat,
        lon=obj.lon,
        is_demo=obj.is_demo,
    )


def build_detail(session: SessionDep, obj: ConstructionObject) -> ObjectDetail:
    developer = session.get(Developer, obj.developer_id) if obj.developer_id else None
    district = session.get(District, obj.district_id) if obj.district_id else None
    window_start = datetime.now(UTC) - timedelta(days=load_settings(session).ad_window_days)
    ads_count = session.scalar(
        select(func.count())
        .select_from(AdPost)
        .where(
            AdPost.object_id == obj.id,
            func.coalesce(AdPost.published_at, AdPost.captured_at, AdPost.created_at) >= window_start,
        )
    )
    latest = session.scalar(latest_score_stmt(obj.id))
    gap = (
        obj.readiness_claimed_pct - obj.readiness_actual_pct
        if obj.readiness_claimed_pct is not None and obj.readiness_actual_pct is not None
        else None
    )
    return ObjectDetail(
        **ObjectPassport.model_validate(obj).model_dump(),
        district_name=district.name if district else None,
        key_status_detail=key_status_detail(obj),
        developer=DeveloperOut.model_validate(developer) if developer else None,
        documents=[DocumentOut.model_validate(item) for item in obj.documents],
        inspections=[InspectionOut.model_validate(item) for item in obj.inspections],
        complaints=[ComplaintOut.model_validate(item) for item in obj.complaints],
        linked_entities=[LinkedEntityOut.model_validate(item) for item in obj.linked_entities],
        ads_7d_count=ads_count or 0,
        readiness_gap_pp=gap,
        latest_score=LatestScore.model_validate(latest) if latest else None,
    )


@router.get("", response_model=Page[ObjectRow])
def list_objects(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    page: PageDep,
    zone: Annotated[Zone | None, Query()] = None,
    district_id: Annotated[int | None, Query()] = None,
    territory_id: Annotated[int | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> Page[ObjectRow]:
    stmt = object_rows_stmt(scope, zone=zone, district_id=district_id, territory_id=territory_id, q=q)
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = session.execute(
        stmt.order_by(ConstructionObject.score.desc().nulls_last(), ConstructionObject.id)
        .limit(page.limit)
        .offset(page.offset)
    )
    return Page(
        items=[to_row(obj, developer_name, district_name) for obj, developer_name, district_name in rows], total=total
    )


@router.post("", response_model=ObjectDetail, status_code=201)
def create_object(
    body: ObjectCreate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> ObjectDetail:
    check_references(session, scope, body.territory_id, body.district_id, body.developer_id)
    data = body.model_dump(exclude={"lat", "lon"})
    obj = ConstructionObject(**data, location=make_point(body.lat, body.lon))
    apply_status_rules(session, obj)
    session.add(obj)
    session.flush()
    session.refresh(obj)
    audit.record(session, user, "object.create", "object", obj.id, None, audit.snapshot(obj), request)
    detail = build_detail(session, obj)
    session.commit()
    object_changed(obj.id)
    return detail


@router.post("/import", response_model=ImportResult)
def import_objects(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    request: Request,
    file: Annotated[UploadFile, File()],
) -> ImportResult:
    result, changed_ids = importer.import_objects(session, scope, user, read_csv_upload(file), request)
    session.commit()
    objects_changed(changed_ids)
    return result


@router.get("/{object_id}", response_model=ObjectDetail)
def get_object(object_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep) -> ObjectDetail:
    return build_detail(session, get_object_in_scope(session, scope, object_id))


@router.get("/{object_id}/dossier.pdf")
def object_dossier(object_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request) -> Response:
    obj = get_object_in_scope(session, scope, object_id)
    document = dossier.render_pdf(session, obj, user, user.locale.value)
    audit.record(session, user, "object.dossier", "object", obj.id, None, None, request)
    session.commit()
    return Response(
        content=document,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{obj.code}-dossier.pdf"', "Cache-Control": "no-store"},
    )


@router.patch("/{object_id}", response_model=ObjectDetail)
def update_object(
    object_id: int, body: ObjectUpdate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> ObjectDetail:
    obj = get_object_in_scope(session, scope, object_id)
    changes = body.model_dump(exclude_unset=True)
    check_references(
        session,
        scope,
        changes.get("territory_id", obj.territory_id),
        changes.get("district_id", obj.district_id),
        changes.get("developer_id", obj.developer_id),
    )
    before = audit.snapshot(obj)
    lat, lon = changes.pop("lat", None), changes.pop("lon", None)
    if "lat" in body.model_fields_set:
        obj.location = make_point(lat, lon)
    for field, value in changes.items():
        setattr(obj, field, value)
    if "construction_status" in changes or "stalled_since" in changes:
        apply_status_rules(session, obj)
    session.flush()
    session.refresh(obj)
    audit.record(session, user, "object.update", "object", obj.id, before, audit.snapshot(obj), request)
    detail = build_detail(session, obj)
    session.commit()
    object_changed(obj.id)
    return detail
