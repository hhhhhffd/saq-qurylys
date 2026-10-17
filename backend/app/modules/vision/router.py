from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from minio.error import S3Error
from sqlalchemy import func, select

from app import audit, storage
from app.config import get_settings
from app.deps import PageDep, ScopeDep, SessionDep, StaffUser
from app.errors import api_error
from app.models import VisionAsset, VisionFinding, VisionFrame, VisionSession
from app.models.enums import (
    VisionAssetKind,
    VisionFindingOrigin,
    VisionReviewAction,
    VisionSessionStatus,
    VisionSource,
)
from app.modules.objects.service import get_object_in_scope
from app.modules.vision import service
from app.modules.vision.schemas import (
    AssetOut,
    FindingCreate,
    FindingOut,
    FrameOut,
    ReviewCreate,
    SessionCreate,
    SessionDetail,
    SessionListItem,
    SessionPatch,
    VisionConfig,
)
from app.schemas import Page

router = APIRouter(prefix="/vision", tags=["vision"])


def _stream(
    bucket: str, key: str, content_type: str, size: int | None, filename: str, inline: bool
) -> StreamingResponse:
    try:
        response = storage.get_client().get_object(bucket, key)
    except S3Error as exc:
        raise api_error(502, "vision_object_missing", "Файл недоступен в хранилище") from exc
    headers = {
        "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{filename}"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }
    if size is not None:
        headers["Content-Length"] = str(size)
    return StreamingResponse(storage.stream_object(response), media_type=content_type, headers=headers)


@router.get("/config", response_model=VisionConfig)
def get_config(user: StaffUser) -> VisionConfig:
    settings = get_settings()
    return VisionConfig(
        enabled=settings.vision_enabled,
        detector_mode=settings.vision_detector_backend,
        ocr_enabled=settings.ocr_enabled,
        max_photo_mb=settings.vision_max_photo_mb,
        max_video_mb=settings.vision_max_video_mb,
        max_duration_seconds=settings.vision_max_duration_seconds,
    )


# ---------------------------------------------------------------- sessions


@router.post("/sessions", response_model=SessionDetail, status_code=201)
def create_session(
    body: SessionCreate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> SessionDetail:
    territory_id, object_id = service.resolve_territory(session, scope, user, body.object_id, body.territory_id)
    vision_session = VisionSession(
        territory_id=territory_id,
        object_id=object_id,
        source=body.source,
        captured_at=body.captured_at,
        note=body.note or None,
        created_by=user.id,
    )
    session.add(vision_session)
    session.flush()
    session.refresh(vision_session)
    audit.record(
        session,
        user,
        "vision_session.create",
        "vision_session",
        vision_session.id,
        None,
        audit.snapshot(vision_session),
        request,
    )
    session.commit()
    return service.build_detail(session, vision_session.id)


@router.get("/sessions", response_model=Page[SessionListItem])
def list_sessions(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    page: PageDep,
    object_id: Annotated[int | None, Query()] = None,
    source: Annotated[VisionSource | None, Query()] = None,
    status: Annotated[VisionSessionStatus | None, Query()] = None,
) -> Page[SessionListItem]:
    stmt = scope.restrict(service.session_query(), VisionSession.territory_id)
    if object_id is not None:
        stmt = stmt.where(VisionSession.object_id == object_id)
    if source is not None:
        stmt = stmt.where(VisionSession.source == source)
    if status is not None:
        stmt = stmt.where(VisionSession.status == status)
    total = session.scalar(select(func.count()).select_from(stmt.with_only_columns(VisionSession.id).subquery())) or 0
    return Page(items=service.list_sessions(session, stmt, page), total=total)


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep) -> SessionDetail:
    service.get_session_in_scope(session, scope, session_id)
    return service.build_detail(session, session_id)


@router.patch("/sessions/{session_id}", response_model=SessionDetail)
def patch_session(
    session_id: int, body: SessionPatch, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> SessionDetail:
    vision_session = service.get_session_in_scope(session, scope, session_id)
    before = audit.snapshot(vision_session)
    fields = body.model_fields_set
    if "object_id" in fields:
        if body.object_id is None:
            vision_session.object_id = None
        else:
            obj = get_object_in_scope(session, scope, body.object_id)
            vision_session.object_id = obj.id
            vision_session.territory_id = obj.territory_id
    if "note" in fields:
        vision_session.note = body.note or None
    if "source" in fields and body.source is not None:
        vision_session.source = body.source
    if "captured_at" in fields:
        vision_session.captured_at = body.captured_at
    session.flush()
    session.refresh(vision_session)
    audit.record(
        session,
        user,
        "vision_session.update",
        "vision_session",
        session_id,
        before,
        audit.snapshot(vision_session),
        request,
    )
    session.commit()
    return service.build_detail(session, session_id)


@router.post("/sessions/{session_id}/reviewed", response_model=SessionDetail)
def mark_reviewed(
    session_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> SessionDetail:
    """The only way a session becomes reviewed: a person says so. Nothing sets it automatically."""
    vision_session = service.get_session_in_scope(session, scope, session_id)
    if vision_session.status is not VisionSessionStatus.reviewed:
        before = audit.snapshot(vision_session)
        vision_session.status = VisionSessionStatus.reviewed
        vision_session.reviewed_by = user.id
        vision_session.reviewed_at = datetime.now(UTC)
        session.flush()
        session.refresh(vision_session)
        audit.record(
            session,
            user,
            "vision_session.review",
            "vision_session",
            session_id,
            before,
            audit.snapshot(vision_session),
            request,
        )
        session.commit()
    return service.build_detail(session, session_id)


# ---------------------------------------------------------------- assets and frames


@router.post("/sessions/{session_id}/assets", response_model=AssetOut, status_code=201)
def upload_asset(
    session_id: int,
    response: Response,
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    request: Request,
    file: Annotated[UploadFile, File()],
) -> AssetOut:
    """Upload one photo or video. The same file in the same session returns the existing asset (200)."""
    vision_session = service.get_session_in_scope(session, scope, session_id)
    stored = service.store_upload(session, vision_session, user, file)
    if not stored.created:
        response.status_code = 200
        return service.build_assets(session, [stored.asset])[0]
    audit.record(
        session,
        user,
        "vision_asset.upload",
        "vision_asset",
        stored.asset.id,
        None,
        audit.snapshot(stored.asset),
        request,
    )
    session.commit()
    if stored.job is not None and not service.dispatch_extract_frames(stored.job):
        service.mark_job_unqueued(session, stored.job)
    return service.build_assets(session, [stored.asset])[0]


@router.get("/assets/{asset_id}/content")
def get_asset_content(asset_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep) -> StreamingResponse:
    asset = service.get_asset_in_scope(session, scope, asset_id)
    filename = f"vision-asset-{asset.id}{storage.extension_for(asset.content_type)}"
    return _stream(
        asset.bucket, asset.s3_key, asset.content_type, asset.size_bytes, filename, asset.kind is VisionAssetKind.photo
    )


@router.get("/sessions/{session_id}/frames", response_model=Page[FrameOut])
def list_frames(
    session_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep, page: PageDep
) -> Page[FrameOut]:
    service.get_session_in_scope(session, scope, session_id)
    stmt = (
        select(VisionFrame)
        .join(VisionAsset, VisionAsset.id == VisionFrame.asset_id)
        .where(VisionAsset.session_id == session_id)
    )
    total = session.scalar(select(func.count()).select_from(stmt.with_only_columns(VisionFrame.id).subquery())) or 0
    frames = session.scalars(
        stmt.order_by(VisionFrame.asset_id, VisionFrame.timestamp_ms.nulls_first(), VisionFrame.id)
        .limit(page.limit)
        .offset(page.offset)
    )
    return Page(
        items=[
            FrameOut(
                id=frame.id,
                asset_id=frame.asset_id,
                timestamp_ms=frame.timestamp_ms,
                width=frame.width,
                height=frame.height,
                sharpness=frame.sharpness,
                usable=frame.usable,
            )
            for frame in frames
        ],
        total=total,
    )


@router.get("/frames/{frame_id}/content")
def get_frame_content(
    frame_id: int,
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    variant: Annotated[Literal["preview", "original"], Query()] = "preview",
) -> StreamingResponse:
    frame, asset = service.get_frame_in_scope(session, scope, frame_id)
    if variant == "preview":
        return _stream(
            frame.bucket, frame.preview_key, "image/jpeg", None, f"vision-frame-{frame.id}-preview.jpg", True
        )
    # A photo's frame is the uploaded file itself; frames cut from a video are JPEG.
    content_type = asset.content_type if frame.timestamp_ms is None else "image/jpeg"
    filename = f"vision-frame-{frame.id}{storage.extension_for(content_type)}"
    return _stream(frame.bucket, frame.s3_key, content_type, None, filename, True)


# ---------------------------------------------------------------- findings


@router.post("/sessions/{session_id}/findings", response_model=FindingOut, status_code=201)
def create_finding(
    session_id: int, body: FindingCreate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> FindingOut:
    """A finding entered by a person. The status is their judgement; no default is assumed."""
    service.get_session_in_scope(session, scope, session_id)
    if body.frame_id is not None:
        frame_session_id = session.scalar(
            select(VisionAsset.session_id)
            .join(VisionFrame, VisionFrame.asset_id == VisionAsset.id)
            .where(VisionFrame.id == body.frame_id)
        )
        if frame_session_id != session_id:
            raise api_error(422, "frame_not_in_session", "Кадр не относится к этой сессии")
    finding = VisionFinding(
        session_id=session_id,
        frame_id=body.frame_id,
        bbox=body.bbox.model_dump() if body.bbox else None,
        category=body.category,
        status=body.status,
        origin=VisionFindingOrigin.manual,
        note=body.note or None,
        created_by=user.id,
    )
    session.add(finding)
    session.flush()
    session.refresh(finding)
    audit.record(
        session, user, "vision_finding.create", "vision_finding", finding.id, None, audit.snapshot(finding), request
    )
    session.commit()
    return service.build_findings(session, [finding])[0]


@router.get("/findings/{finding_id}", response_model=FindingOut)
def get_finding(finding_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep) -> FindingOut:
    finding = service.get_finding_in_scope(session, scope, finding_id)
    return service.build_findings(session, [finding])[0]


@router.post("/findings/{finding_id}/review", response_model=FindingOut)
def review_finding(
    finding_id: int, body: ReviewCreate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> FindingOut:
    finding = service.get_finding_in_scope(session, scope, finding_id)
    comment = body.comment or None
    if body.action is VisionReviewAction.not_applicable and comment is None:
        raise api_error(422, "comment_required", "Укажите основание, почему требование не применяется")
    if body.action is VisionReviewAction.comment and comment is None:
        raise api_error(422, "comment_required", "Комментарий не может быть пустым")
    before = audit.snapshot(finding)
    service.apply_review(session, finding, user, body.action, comment)
    session.refresh(finding)
    audit.record(
        session,
        user,
        "vision_finding.review",
        "vision_finding",
        finding_id,
        before,
        {**audit.snapshot(finding), "review": {"action": body.action.value, "comment": comment}},
        request,
    )
    session.commit()
    return service.build_findings(session, [finding])[0]
