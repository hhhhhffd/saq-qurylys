import re
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from minio.error import S3Error
from sqlalchemy import func, select

from app import audit, storage
from app.config import get_settings
from app.deps import PageDep, ScopeDep, SessionDep, StaffUser
from app.errors import api_error
from app.models import VisionAsset, VisionFinding, VisionFrame, VisionJob, VisionSession
from app.models.enums import (
    AdOrigin,
    LinkMethod,
    OcrStatus,
    Platform,
    VisionAssetKind,
    VisionAssetStatus,
    VisionCategory,
    VisionFindingOrigin,
    VisionFindingStatus,
    VisionJobKind,
    VisionReviewAction,
    VisionReviewState,
    VisionSessionStatus,
    VisionSource,
)
from app.modules.ads import service as ads_service
from app.modules.nlp.text import strip_ocr_marker
from app.modules.objects.service import get_object_in_scope
from app.modules.vision import media, service
from app.modules.vision.schemas import (
    AssetOut,
    FindingCreate,
    FindingOut,
    FrameOut,
    PublishAdBody,
    PublishAdOut,
    ReviewCreate,
    SessionCreate,
    SessionDetail,
    SessionListItem,
    SessionPatch,
    VisionConfig,
)
from app.schemas import Page

router = APIRouter(prefix="/vision", tags=["vision"])


RANGE_HEADER = re.compile(r"^bytes=(\d*)-(\d*)$")


def _byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    """The inclusive byte range asked for, or None to serve the whole file.

    Only a single range is served; anything else (several ranges, another unit, garbage) is answered with the
    whole file, which RFC 9110 allows. A range that starts beyond the end is 416.
    """
    match = RANGE_HEADER.match(header.strip()) if header else None
    if match is None or (not match[1] and not match[2]):
        return None
    if not match[1]:  # suffix: the last N bytes
        length = int(match[2])
        if length == 0:
            raise _range_not_satisfiable(size)
        return max(0, size - length), size - 1
    start = int(match[1])
    end = min(int(match[2]), size - 1) if match[2] else size - 1
    if start >= size or end < start:
        raise _range_not_satisfiable(size)
    return start, end


def _range_not_satisfiable(size: int) -> HTTPException:
    return HTTPException(
        status_code=416,
        detail={"code": "range_not_satisfiable", "message": "Запрошенный диапазон вне файла"},
        headers={"Content-Range": f"bytes */{size}"},
    )


def _stream(
    bucket: str,
    key: str,
    content_type: str,
    size: int | None,
    filename: str,
    inline: bool,
    byte_range: tuple[int, int] | None = None,
) -> StreamingResponse:
    try:
        if byte_range is None:
            response = storage.get_client().get_object(bucket, key)
        else:
            response = storage.get_client().get_object(
                bucket, key, offset=byte_range[0], length=byte_range[1] - byte_range[0] + 1
            )
    except S3Error as exc:
        raise api_error(502, "vision_object_missing", "Файл недоступен в хранилище") from exc
    headers = {
        "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{filename}"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }
    status_code = 200
    if byte_range is not None and size is not None:
        status_code = 206
        headers["Content-Range"] = f"bytes {byte_range[0]}-{byte_range[1]}/{size}"
        headers["Content-Length"] = str(byte_range[1] - byte_range[0] + 1)
    elif size is not None:
        headers["Content-Length"] = str(size)
    return StreamingResponse(
        storage.stream_object(response), status_code=status_code, media_type=content_type, headers=headers
    )


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
    service.reopen_if_reviewed(session, vision_session, user, request)
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


@router.post("/assets/{asset_id}/retry", response_model=AssetOut)
def retry_asset(asset_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request) -> AssetOut:
    """Process a video again after a failure, or after the queue was unavailable at upload time."""
    service.get_asset_in_scope(session, scope, asset_id)
    # Locked so that a double click creates one job.
    asset = session.scalars(select(VisionAsset).where(VisionAsset.id == asset_id).with_for_update()).one()
    jobs = list(session.scalars(select(VisionJob).where(VisionJob.asset_id == asset_id).order_by(VisionJob.id)))
    if asset.kind is not VisionAssetKind.video or asset.status is not VisionAssetStatus.failed:
        raise api_error(409, "asset_not_failed", "Повторить можно только обработку видео, которая завершилась ошибкой")
    before = audit.snapshot(asset)
    asset.status = VisionAssetStatus.queued
    asset.error_code = None
    job = VisionJob(
        asset_id=asset.id,
        kind=VisionJobKind.extract_frames,
        idempotency_key=f"extract:{asset.id}:{len(jobs) + 1}",
    )
    session.add(job)
    session.flush()
    session.refresh(asset)
    audit.record(
        session,
        user,
        "vision_asset.retry",
        "vision_asset",
        asset.id,
        before,
        {**audit.snapshot(asset), "job_id": job.id},
        request,
    )
    session.commit()
    if not service.dispatch_extract_frames(job):
        service.mark_job_unqueued(session, job)
    return service.build_assets(session, [asset])[0]


@router.get("/assets/{asset_id}/content")
def get_asset_content(
    asset_id: int,
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> StreamingResponse:
    """The original. A video honours a single `Range: bytes=a-b` so that a player can seek."""
    asset = service.get_asset_in_scope(session, scope, asset_id)
    filename = f"vision-asset-{asset.id}{storage.extension_for(asset.content_type)}"
    is_photo = asset.kind is VisionAssetKind.photo
    byte_range = None if is_photo else _byte_range(range_header, asset.size_bytes)
    response = _stream(asset.bucket, asset.s3_key, asset.content_type, asset.size_bytes, filename, is_photo, byte_range)
    if not is_photo:
        response.headers["Accept-Ranges"] = "bytes"
    return response


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
    vision_session = service.get_session_in_scope(session, scope, session_id)
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
    service.reopen_if_reviewed(session, vision_session, user, request)
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
    service.apply_review(session, finding, user, body.action, comment, body.status)
    session.refresh(finding)
    audit.record(
        session,
        user,
        "vision_finding.review",
        "vision_finding",
        finding_id,
        before,
        {
            **audit.snapshot(finding),
            "review": {"action": body.action.value, "comment": comment, "status": body.status},
        },
        request,
    )
    session.commit()
    return service.build_findings(session, [finding])[0]


# ---------------------------------------------------------------- OCR and publication


def _outdoor_ad_with_area(finding: VisionFinding) -> None:
    if finding.category is not VisionCategory.outdoor_ad:
        raise api_error(422, "finding_not_outdoor_ad", "Распознавание текста доступно только для наружной рекламы")
    if finding.frame_id is None or finding.bbox is None:
        raise api_error(422, "frame_required", "Отметьте область с рекламой на кадре")


@router.post("/findings/{finding_id}/ocr", response_model=FindingOut)
def run_finding_ocr(
    finding_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> FindingOut:
    """Read the text of the marked area. The result is machine output and overwrites a previous run."""
    finding = service.get_finding_in_scope(session, scope, finding_id)
    _outdoor_ad_with_area(finding)
    if not get_settings().ocr_enabled:
        raise api_error(409, "ocr_unavailable", "Распознавание текста отключено")
    before = audit.snapshot(finding)
    previous_status = finding.ocr_status
    finding.ocr_status = OcrStatus.pending
    session.flush()
    audit.record(
        session, user, "vision_finding.ocr", "vision_finding", finding.id, before, audit.snapshot(finding), request
    )
    session.commit()
    if not service.dispatch_ocr(finding.id):
        # Nothing will end `pending`, so the status goes back to what it was.
        finding.ocr_status = previous_status
        audit.record(
            session,
            user,
            "vision_finding.ocr_unqueued",
            "vision_finding",
            finding.id,
            None,
            {"ocr_status": previous_status.value if previous_status else None},
            request,
        )
        session.commit()
        raise api_error(503, "queue_unavailable", "Очередь обработки недоступна, повторите позже")
    return service.build_findings(session, [finding])[0]


@router.post("/findings/{finding_id}/publish-ad", response_model=PublishAdOut)
def publish_ad(
    finding_id: int,
    body: PublishAdBody,
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    request: Request,
) -> PublishAdOut:
    """Turn a confirmed outdoor advertisement into a publication of the ads module.

    The row is locked, so concurrent requests create one publication; a repeat returns the same `ad_id`. The
    publication goes through the ordinary pipeline: nothing is scored until a person confirms the link to an object.
    """
    service.get_finding_in_scope(session, scope, finding_id)
    finding = session.scalars(
        select(VisionFinding)
        .where(VisionFinding.id == finding_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if finding.ad_post_id is not None:
        return PublishAdOut(ad_id=finding.ad_post_id)
    if finding.category is not VisionCategory.outdoor_ad:
        raise api_error(422, "finding_not_outdoor_ad", "Опубликовать можно только наружную рекламу")
    if finding.review_state is not VisionReviewState.confirmed:
        raise api_error(409, "finding_not_confirmed", "Сначала подтвердите находку")
    if finding.status is VisionFindingStatus.not_applicable:
        raise api_error(409, "finding_not_applicable", "Находка помечена как неприменимая")
    if finding.frame_id is None:
        raise api_error(422, "frame_required", "У находки нет кадра")
    text = strip_ocr_marker(body.text)
    if not text:
        raise api_error(422, "validation_error", "Текст публикации не может быть пустым")

    frame, asset = service.get_frame_in_scope(session, scope, finding.frame_id)
    vision_session = service.get_session_in_scope(session, scope, finding.session_id)
    fields: dict[str, object] = {"territory_id": vision_session.territory_id}
    if body.object_id is not None:
        # The link is made only by the person who passed the object.
        obj = get_object_in_scope(session, scope, body.object_id)
        fields = {
            "object_id": obj.id,
            "territory_id": obj.territory_id,
            "link_method": LinkMethod.manual,
            "link_confidence": 1.0,
        }
    original = service.read_object(frame.bucket, frame.s3_key)
    photos = [(original, asset.content_type if frame.timestamp_ms is None else "image/jpeg")]
    if finding.bbox is not None:
        photos.append((media.crop_region(original, finding.bbox), "image/jpeg"))
    before = audit.snapshot(finding)
    ad = ads_service.create_manual_ad(
        session,
        user,
        request,
        platform=Platform.outdoor,
        url=None,
        external_id=f"vision-finding-{finding.id}",
        text=text,
        published_at=None,
        is_outdoor=True,
        lat=asset.lat,
        lon=asset.lon,
        photos=photos,
        # The area was read before the person confirmed it; the pipeline must not read the photos again.
        ocr_status=OcrStatus.done if finding.ocr_status is OcrStatus.done else None,
        fields=fields,
        origin=AdOrigin.vision,
        audit_action="ad.vision_create",
    )
    finding.confirmed_text = text
    finding.ad_post_id = ad.id
    session.flush()
    audit.record(
        session,
        user,
        "vision_finding.publish_ad",
        "vision_finding",
        finding.id,
        before,
        audit.snapshot(finding),
        request,
    )
    session.commit()
    if not ads_service.dispatch_pipeline(ad.id, capture=False, requested_by=user.id):
        ads_service.mark_capture_unqueued(session, ad)
    return PublishAdOut(ad_id=ad.id)
