import hashlib
import io
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import Select, exists, func, select
from sqlalchemy.orm import Session, aliased

from app import storage
from app.config import get_settings
from app.deps import PageParams
from app.errors import api_error
from app.geo import make_point
from app.models import (
    AppUser,
    ConstructionObject,
    Territory,
    VisionAsset,
    VisionFinding,
    VisionFrame,
    VisionJob,
    VisionReview,
    VisionSession,
)
from app.models.enums import (
    VisionAssetKind,
    VisionAssetStatus,
    VisionFindingStatus,
    VisionJobKind,
    VisionJobStatus,
    VisionReviewAction,
    VisionReviewState,
)
from app.modules.objects.service import get_object_in_scope
from app.modules.vision.schemas import (
    AssetOut,
    FindingOut,
    ObjectRef,
    ReviewOut,
    SessionDetail,
    SessionListItem,
)
from app.scope import TerritoryScope
from app.uploads import sniff_content_type
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

READ_CHUNK_BYTES = 1024 * 1024
PREVIEW_MAX_SIDE = 640
PREVIEW_QUALITY = 85
# Decoding allocates width * height * 4 bytes; a larger picture is refused before it is loaded.
MAX_PHOTO_PIXELS = 100_000_000
PHOTO_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
EXIF_IFD = 0x8769
GPS_IFD = 0x8825
EXIF_DATETIME_ORIGINAL = 36867
EXIF_OFFSET_TIME_ORIGINAL = 36880
_OFFSET = re.compile(r"^([+-])(\d{2}):(\d{2})$")

REVIEW_TRANSITIONS: dict[VisionReviewAction, VisionReviewState] = {
    VisionReviewAction.confirm: VisionReviewState.confirmed,
    VisionReviewAction.reject: VisionReviewState.rejected,
    VisionReviewAction.needs_more_evidence: VisionReviewState.needs_more_evidence,
    # A finding declared not applicable leaves the work queue the same way a rejected one does.
    VisionReviewAction.not_applicable: VisionReviewState.rejected,
}


# ---------------------------------------------------------------- access


def _visible_session(db: Session, scope: TerritoryScope, session_id: int) -> VisionSession | None:
    vision_session = db.get(VisionSession, session_id)
    if vision_session is None or not scope.contains(vision_session.territory_id):
        return None
    return vision_session


def get_session_in_scope(db: Session, scope: TerritoryScope, session_id: int) -> VisionSession:
    """Out-of-scope sessions are reported as missing so their existence is not disclosed."""
    vision_session = _visible_session(db, scope, session_id)
    if vision_session is None:
        raise api_error(404, "vision_session_not_found", "Сессия съёмки не найдена")
    return vision_session


def get_asset_in_scope(db: Session, scope: TerritoryScope, asset_id: int) -> VisionAsset:
    asset = db.get(VisionAsset, asset_id)
    if asset is None or _visible_session(db, scope, asset.session_id) is None:
        raise api_error(404, "vision_asset_not_found", "Файл съёмки не найден")
    return asset


def get_frame_in_scope(db: Session, scope: TerritoryScope, frame_id: int) -> tuple[VisionFrame, VisionAsset]:
    frame = db.get(VisionFrame, frame_id)
    asset = db.get(VisionAsset, frame.asset_id) if frame is not None else None
    if frame is None or asset is None or _visible_session(db, scope, asset.session_id) is None:
        raise api_error(404, "vision_frame_not_found", "Кадр не найден")
    return frame, asset


def get_finding_in_scope(db: Session, scope: TerritoryScope, finding_id: int) -> VisionFinding:
    finding = db.get(VisionFinding, finding_id)
    if finding is None or _visible_session(db, scope, finding.session_id) is None:
        raise api_error(404, "vision_finding_not_found", "Находка не найдена")
    return finding


def resolve_territory(
    db: Session, scope: TerritoryScope, user: AppUser, object_id: int | None, territory_id: int | None
) -> tuple[int, int | None]:
    """Territory and object of a new session: the territory of the object, else the one named, else the user's."""
    if object_id is not None:
        obj = get_object_in_scope(db, scope, object_id)
        if territory_id is not None and territory_id != obj.territory_id:
            raise api_error(422, "territory_mismatch", "Территория не совпадает с территорией объекта")
        return obj.territory_id, obj.id
    if territory_id is not None:
        if not scope.contains(territory_id) or db.get(Territory, territory_id) is None:
            raise api_error(404, "territory_not_found", "Территория не найдена")
        return territory_id, None
    if user.territory_id is None:
        raise api_error(422, "territory_required", "Укажите объект или территорию")
    return user.territory_id, None


# ---------------------------------------------------------------- response building


def session_query() -> Select[Any]:
    creator = aliased(AppUser)
    reviewer = aliased(AppUser)
    assets_count = (
        select(func.count())
        .where(VisionAsset.session_id == VisionSession.id)
        .correlate(VisionSession)
        .scalar_subquery()
    )
    frames_count = (
        select(func.count())
        .select_from(VisionFrame)
        .join(VisionAsset, VisionAsset.id == VisionFrame.asset_id)
        .where(VisionAsset.session_id == VisionSession.id)
        .correlate(VisionSession)
        .scalar_subquery()
    )
    findings_count = (
        select(func.count())
        .where(VisionFinding.session_id == VisionSession.id)
        .correlate(VisionSession)
        .scalar_subquery()
    )
    processing = exists().where(
        VisionAsset.session_id == VisionSession.id,
        VisionAsset.status.in_((VisionAssetStatus.queued, VisionAssetStatus.processing)),
    )
    failed = exists().where(VisionAsset.session_id == VisionSession.id, VisionAsset.status == VisionAssetStatus.failed)
    return (
        select(
            VisionSession,
            ConstructionObject.id,
            ConstructionObject.code,
            ConstructionObject.name,
            creator.full_name,
            reviewer.full_name,
            assets_count,
            frames_count,
            findings_count,
            processing,
            failed,
        )
        .outerjoin(ConstructionObject, ConstructionObject.id == VisionSession.object_id)
        .outerjoin(creator, creator.id == VisionSession.created_by)
        .outerjoin(reviewer, reviewer.id == VisionSession.reviewed_by)
    )


def _list_item(row: Any) -> SessionListItem:
    vs, object_id, object_code, object_name, created_by_name, reviewed_by_name, assets, frames, findings, busy, bad = (
        row
    )
    return SessionListItem(
        id=vs.id,
        object=ObjectRef(id=object_id, code=object_code, name=object_name) if object_id is not None else None,
        territory_id=vs.territory_id,
        source=vs.source,
        captured_at=vs.captured_at,
        status=vs.status,
        is_demo=vs.is_demo,
        note=vs.note,
        created_at=vs.created_at,
        created_by_name=created_by_name,
        reviewed_at=vs.reviewed_at,
        reviewed_by_name=reviewed_by_name,
        assets_count=assets,
        frames_count=frames,
        findings_count=findings,
        processing=busy,
        failed=bad,
    )


def list_sessions(db: Session, stmt: Select[Any], page: PageParams) -> list[SessionListItem]:
    rows = db.execute(stmt.order_by(VisionSession.id.desc()).limit(page.limit).offset(page.offset))
    return [_list_item(row) for row in rows]


def build_assets(db: Session, assets: list[VisionAsset]) -> list[AssetOut]:
    if not assets:
        return []
    ids = [asset.id for asset in assets]
    frame_counts = dict(
        db.execute(
            select(VisionFrame.asset_id, func.count())
            .where(VisionFrame.asset_id.in_(ids))
            .group_by(VisionFrame.asset_id)
        )
        .tuples()
        .all()
    )
    latest_job: dict[int, VisionJob] = {}
    for queued in db.scalars(select(VisionJob).where(VisionJob.asset_id.in_(ids)).order_by(VisionJob.id)):
        latest_job[queued.asset_id] = queued
    result = []
    for asset in assets:
        job = latest_job.get(asset.id)
        if asset.status is VisionAssetStatus.ready:
            progress = 100
        else:
            progress = job.progress if job is not None else 0
        result.append(
            AssetOut(
                id=asset.id,
                session_id=asset.session_id,
                kind=asset.kind,
                original_name=asset.original_name,
                content_type=asset.content_type,
                size_bytes=asset.size_bytes,
                sha256=asset.sha256,
                width=asset.width,
                height=asset.height,
                duration_ms=asset.duration_ms,
                lat=asset.lat,
                lon=asset.lon,
                taken_at=asset.taken_at,
                status=asset.status,
                error_code=asset.error_code,
                progress=progress,
                frames_count=frame_counts.get(asset.id, 0),
                created_at=asset.created_at,
            )
        )
    return result


def build_findings(db: Session, findings: list[VisionFinding]) -> list[FindingOut]:
    if not findings:
        return []
    reviews: dict[int, list[ReviewOut]] = {}
    review_rows = db.execute(
        select(VisionReview, AppUser.full_name)
        .outerjoin(AppUser, AppUser.id == VisionReview.reviewer_id)
        .where(VisionReview.finding_id.in_([finding.id for finding in findings]))
        .order_by(VisionReview.id)
    )
    for review, reviewer_name in review_rows:
        reviews.setdefault(review.finding_id, []).append(
            ReviewOut(
                id=review.id,
                action=review.action,
                comment=review.comment,
                reviewer_name=reviewer_name,
                created_at=review.created_at,
            )
        )
    creator_ids = {finding.created_by for finding in findings if finding.created_by is not None}
    names = dict(db.execute(select(AppUser.id, AppUser.full_name).where(AppUser.id.in_(creator_ids))).tuples().all())
    return [
        FindingOut(
            id=finding.id,
            session_id=finding.session_id,
            frame_id=finding.frame_id,
            bbox=finding.bbox,
            category=finding.category,
            status=finding.status,
            origin=finding.origin,
            confidence=finding.confidence,
            model_version=finding.model_version,
            note=finding.note,
            review_state=finding.review_state,
            ocr_status=finding.ocr_status,
            ocr_text=finding.ocr_text,
            ocr_confidence=finding.ocr_confidence,
            ocr_engine=finding.ocr_engine,
            confirmed_text=finding.confirmed_text,
            ad_post_id=finding.ad_post_id,
            created_at=finding.created_at,
            created_by_name=names.get(finding.created_by) if finding.created_by is not None else None,
            reviews=reviews.get(finding.id, []),
        )
        for finding in findings
    ]


def build_detail(db: Session, session_id: int) -> SessionDetail:
    row = db.execute(session_query().where(VisionSession.id == session_id)).one()
    item = _list_item(row)
    assets = list(db.scalars(select(VisionAsset).where(VisionAsset.session_id == session_id).order_by(VisionAsset.id)))
    findings = list(
        db.scalars(select(VisionFinding).where(VisionFinding.session_id == session_id).order_by(VisionFinding.id))
    )
    return SessionDetail(**item.model_dump(), assets=build_assets(db, assets), findings=build_findings(db, findings))


# ---------------------------------------------------------------- upload


@dataclass(frozen=True)
class StoredUpload:
    asset: VisionAsset
    created: bool
    job: VisionJob | None  # a video waiting for frame extraction


@dataclass(frozen=True)
class PhotoInfo:
    width: int
    height: int
    taken_at: datetime | None
    lat: float | None
    lon: float | None
    preview: bytes


def sniff_media(head: bytes) -> tuple[VisionAssetKind, str]:
    """Kind and content type from magic bytes; the declared type and the file name are not trusted."""
    photo_type = sniff_content_type(head)
    if photo_type in PHOTO_TYPES:
        return VisionAssetKind.photo, photo_type
    if head[4:8] == b"ftyp":
        return VisionAssetKind.video, "video/quicktime" if head[8:12] == b"qt  " else "video/mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return VisionAssetKind.video, "video/webm" if b"webm" in head[:64] else "video/x-matroska"
    raise api_error(415, "unsupported_media_type", "Допустимы фото JPEG, PNG, WebP и видео MP4, MOV, WebM, MKV")


def _gps_coordinate(value: Any, ref: Any, negative_ref: str) -> float | None:
    try:
        degrees, minutes, seconds = (float(part) for part in value)
    except (TypeError, ValueError):
        return None
    result = degrees + minutes / 60 + seconds / 3600
    return -result if ref == negative_ref else result


def _exif_taken_at(exif: Image.Exif) -> datetime | None:
    ifd = exif.get_ifd(EXIF_IFD)
    raw = ifd.get(EXIF_DATETIME_ORIGINAL)
    if not isinstance(raw, str):
        return None
    try:
        moment = datetime.strptime(raw.strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    # EXIF carries no zone unless OffsetTimeOriginal is present; without it the time is kept as written, as UTC.
    offset = _OFFSET.match(str(ifd.get(EXIF_OFFSET_TIME_ORIGINAL, "")).strip())
    if offset:
        delta = timedelta(hours=int(offset[2]), minutes=int(offset[3]))
        return moment.replace(tzinfo=timezone(-delta if offset[1] == "-" else delta))
    return moment.replace(tzinfo=UTC)


def _exif_location(exif: Image.Exif) -> tuple[float | None, float | None]:
    gps = exif.get_ifd(GPS_IFD)
    lat = _gps_coordinate(gps.get(2), gps.get(1), "S")
    lon = _gps_coordinate(gps.get(4), gps.get(3), "W")
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None
    return lat, lon


def decode_photo(file: UploadFile) -> PhotoInfo:
    """Decode the picture, read its EXIF and build the preview. An undecodable file stores nothing."""
    file.file.seek(0)
    try:
        with Image.open(file.file) as image:
            if image.width * image.height > MAX_PHOTO_PIXELS:
                raise api_error(422, "image_too_large", "Изображение слишком большое по числу пикселей")
            exif = image.getexif()
            taken_at = _exif_taken_at(exif)
            lat, lon = _exif_location(exif)
            upright = ImageOps.exif_transpose(image)
            upright.load()
            width, height = upright.size
            preview_image = upright.convert("RGB")
            preview_image.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE))
            buffer = io.BytesIO()
            preview_image.save(buffer, "JPEG", quality=PREVIEW_QUALITY)
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise api_error(422, "image_undecodable", "Не удалось прочитать изображение") from exc
    return PhotoInfo(width=width, height=height, taken_at=taken_at, lat=lat, lon=lon, preview=buffer.getvalue())


def store_upload(db: Session, vision_session: VisionSession, user: AppUser, file: UploadFile) -> StoredUpload:
    """Stream the upload through sha256 and the size limit, then store it. Flushes; the caller commits.

    The file is spooled to disk by the multipart parser and read in chunks: a video never sits in memory whole.
    """
    settings = get_settings()
    head = file.file.read(READ_CHUNK_BYTES)
    if not head:
        raise api_error(422, "empty_file", "Файл пуст")
    kind, content_type = sniff_media(head)
    limit_mb = settings.vision_max_photo_mb if kind is VisionAssetKind.photo else settings.vision_max_video_mb
    digest = hashlib.sha256()
    size = 0
    chunk = head
    while chunk:
        size += len(chunk)
        if size > limit_mb * 1024 * 1024:
            raise api_error(413, "file_too_large", f"Файл больше {limit_mb} МБ")
        digest.update(chunk)
        chunk = file.file.read(READ_CHUNK_BYTES)
    sha256 = digest.hexdigest()

    existing = db.scalars(
        select(VisionAsset).where(VisionAsset.session_id == vision_session.id, VisionAsset.sha256 == sha256)
    ).first()
    if existing is not None:
        return StoredUpload(asset=existing, created=False, job=None)

    photo = decode_photo(file) if kind is VisionAssetKind.photo else None
    token = secrets.token_hex(16)
    key = f"session/{vision_session.id}/{token}{storage.extension_for(content_type)}"
    name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()[:255] or None
    asset = VisionAsset(
        session_id=vision_session.id,
        kind=kind,
        original_name=name,
        content_type=content_type,
        size_bytes=size,
        sha256=sha256,
        bucket=settings.s3_bucket_vision,
        s3_key=key,
        uploaded_by=user.id,
        status=VisionAssetStatus.ready if photo else VisionAssetStatus.queued,
    )
    job = None
    if photo is not None:
        asset.width, asset.height, asset.taken_at = photo.width, photo.height, photo.taken_at
        asset.location = make_point(photo.lat, photo.lon)
    db.add(asset)
    db.flush()
    if photo is not None:
        preview_key = f"session/{vision_session.id}/{token}-preview.jpg"
        db.add(
            VisionFrame(
                asset_id=asset.id,
                bucket=asset.bucket,
                s3_key=key,
                preview_key=preview_key,
                width=photo.width,
                height=photo.height,
            )
        )
    else:
        job = VisionJob(asset_id=asset.id, kind=VisionJobKind.extract_frames, idempotency_key=f"extract:{asset.id}:1")
        db.add(job)
    db.flush()
    db.refresh(asset)

    # Rows are flushed first so a constraint violation surfaces before anything reaches the locked bucket.
    file.file.seek(0)
    storage.put_vision_object(key, file.file, size, content_type)
    if photo is not None:
        storage.put_vision_object(preview_key, io.BytesIO(photo.preview), len(photo.preview), "image/jpeg")
    return StoredUpload(asset=asset, created=True, job=job)


def dispatch_extract_frames(job: VisionJob) -> bool:
    """Queue frame extraction of a video (Stage 2 worker). Call after the job is committed.

    Returns False when the broker is unreachable; the upload itself is already saved.
    """
    if not get_settings().events_enabled:
        return True
    try:
        celery_app.send_task("vision.extract_frames", args=[job.id], queue="vision", retry=False, ignore_result=True)
    except Exception:
        logger.exception("Failed to enqueue vision.extract_frames for job %s", job.id)
        return False
    return True


def mark_job_unqueued(db: Session, job: VisionJob) -> None:
    """The asset stays queued so that the processing can be requested again; the job records why it did not start."""
    job.status = VisionJobStatus.failed
    job.error_code = "queue_unavailable"
    job.error_message = "Не удалось поставить обработку видео в очередь"
    db.commit()


# ---------------------------------------------------------------- findings


def apply_review(
    db: Session, finding: VisionFinding, user: AppUser, action: VisionReviewAction, comment: str | None
) -> VisionReview:
    review = VisionReview(finding_id=finding.id, action=action, comment=comment, reviewer_id=user.id)
    db.add(review)
    new_state = REVIEW_TRANSITIONS.get(action)
    if new_state is not None:
        finding.review_state = new_state
    if action is VisionReviewAction.not_applicable:
        finding.status = VisionFindingStatus.not_applicable
    db.flush()
    return review
