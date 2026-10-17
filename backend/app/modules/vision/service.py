import hashlib
import io
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Request, UploadFile
from minio.error import S3Error
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import Select, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app import audit, storage
from app.config import get_settings
from app.deps import PageParams
from app.errors import api_error
from app.geo import make_point
from app.models import (
    AppUser,
    ConstructionObject,
    Territory,
    VisionAsset,
    VisionDetection,
    VisionFinding,
    VisionFrame,
    VisionJob,
    VisionReview,
    VisionRun,
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
    VisionRunStatus,
    VisionSessionStatus,
)
from app.modules.objects.service import get_object_in_scope
from app.modules.vision.detector import CATEGORY_PROMPTS
from app.modules.vision.schemas import (
    AssetOut,
    FindingOut,
    ObjectRef,
    ReviewOut,
    RunOut,
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
MAX_PHOTO_PIXELS = 50_000_000
PHOTO_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
# Major brands of the ISO base media / QuickTime files that hold video. Image containers (heic, avif, mif1) and
# audio-only brands (M4A) share the `ftyp` box and are refused.
VIDEO_BRANDS = frozenset(
    {b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"M4V ", b"qt  ", b"dash"}
    | {b"3gp4", b"3gp5", b"3g2a"}
)
DEFAULT_TIMEZONE = "Asia/Almaty"
EXIF_ORIENTATION = 274
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
    ) | exists().where(
        VisionRun.session_id == VisionSession.id,
        VisionRun.status.in_((VisionRunStatus.queued, VisionRunStatus.running)),
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
                status=review.status,
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
            run_id=finding.run_id,
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
    return SessionDetail(
        **item.model_dump(),
        assets=build_assets(db, assets),
        findings=build_findings(db, findings),
        runs=build_runs(db, session_id),
    )


def build_runs(db: Session, session_id: int) -> list[RunOut]:
    runs = list(db.scalars(select(VisionRun).where(VisionRun.session_id == session_id).order_by(VisionRun.id)))
    found: dict[int, dict[str, int]] = {}
    completed = [run.id for run in runs if run.status is VisionRunStatus.completed]
    if completed:
        rows = db.execute(
            select(
                VisionDetection.run_id,
                VisionDetection.category,
                func.count(func.distinct(VisionDetection.group_key)),
            )
            .where(VisionDetection.run_id.in_(completed))
            .group_by(VisionDetection.run_id, VisionDetection.category)
        )
        for run_id, category, count in rows:
            found.setdefault(run_id, {})[category.value] = count
    categories = [category.value for category in CATEGORY_PROMPTS]
    return [
        RunOut(
            id=run.id,
            asset_id=run.asset_id,
            status=run.status,
            model_version=run.model_version,
            frames_total=run.frames_total,
            frames_done=run.frames_done,
            error_code=run.error_code,
            started_at=run.started_at,
            finished_at=run.finished_at,
            summary={category: found.get(run.id, {}).get(category, 0) for category in categories}
            if run.status is VisionRunStatus.completed
            else {},
        )
        for run in runs
    ]


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
    if head[4:8] == b"ftyp" and head[8:12] in VIDEO_BRANDS:
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


def _exif_taken_at(exif: Image.Exif, local_zone: tzinfo) -> datetime | None:
    ifd = exif.get_ifd(EXIF_IFD)
    raw = ifd.get(EXIF_DATETIME_ORIGINAL)
    if not isinstance(raw, str):
        return None
    try:
        moment = datetime.strptime(raw.strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    # EXIF carries no zone unless OffsetTimeOriginal is present; without it the time is the camera's local time,
    # taken to be that of the territory of the session.
    offset = _OFFSET.match(str(ifd.get(EXIF_OFFSET_TIME_ORIGINAL, "")).strip())
    if offset:
        delta = timedelta(hours=int(offset[2]), minutes=int(offset[3]))
        return moment.replace(tzinfo=timezone(-delta if offset[1] == "-" else delta))
    return moment.replace(tzinfo=local_zone)


def _exif_location(exif: Image.Exif) -> tuple[float | None, float | None]:
    gps = exif.get_ifd(GPS_IFD)
    lat = _gps_coordinate(gps.get(2), gps.get(1), "S")
    lon = _gps_coordinate(gps.get(4), gps.get(3), "W")
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None
    return lat, lon


def decode_photo(file: UploadFile, local_zone: tzinfo) -> PhotoInfo:
    """Decode the picture, read its EXIF and build the preview. An undecodable file stores nothing.

    A JPEG is decoded at a reduced scale (`draft`), so a large photo never takes its full size in memory; the
    dimensions are those of the upright picture, as people (and the marked areas) see it.
    """
    file.file.seek(0)
    try:
        with Image.open(file.file) as image:
            if image.width * image.height > MAX_PHOTO_PIXELS:
                raise api_error(422, "image_too_large", "Изображение слишком большое по числу пикселей")
            exif = image.getexif()
            taken_at = _exif_taken_at(exif, local_zone)
            lat, lon = _exif_location(exif)
            width, height = image.size
            if exif.get(EXIF_ORIENTATION) in {5, 6, 7, 8}:
                width, height = height, width
            if image.format == "JPEG":
                image.draft("RGB", (PREVIEW_MAX_SIDE * 2, PREVIEW_MAX_SIDE * 2))
            upright = ImageOps.exif_transpose(image)
            upright.load()
            preview_image = upright.convert("RGB")
            preview_image.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE))
            buffer = io.BytesIO()
            preview_image.save(buffer, "JPEG", quality=PREVIEW_QUALITY)
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise api_error(422, "image_undecodable", "Не удалось прочитать изображение") from exc
    return PhotoInfo(width=width, height=height, taken_at=taken_at, lat=lat, lon=lon, preview=buffer.getvalue())


def _territory_zone(db: Session, territory_id: int) -> tzinfo:
    territory = db.get(Territory, territory_id)
    try:
        return ZoneInfo(territory.timezone if territory is not None else DEFAULT_TIMEZONE)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE)


def _existing_asset(db: Session, session_id: int, sha256: str) -> VisionAsset | None:
    return db.scalars(
        select(VisionAsset).where(VisionAsset.session_id == session_id, VisionAsset.sha256 == sha256)
    ).first()


def store_upload(db: Session, vision_session: VisionSession, user: AppUser, file: UploadFile) -> StoredUpload:
    """Stream the upload through sha256 and the size limit, store it, then record it. Flushes; the caller commits.

    The file is spooled to disk by the multipart parser and read in chunks: a video never sits in memory whole.
    No database transaction is open while the file is hashed and sent to MinIO (up to the video limit): the
    transaction is ended before, and the rows are inserted afterwards. The cost is that a failure after the upload
    leaves an unreferenced object in the locked bucket (it cannot be deleted); that is logged. Two concurrent
    uploads of the same file both store an object, and the unique (session, sha256) index lets one row through;
    the other request returns the existing asset.
    """
    settings = get_settings()
    session_id, territory_id = vision_session.id, vision_session.territory_id
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

    existing = _existing_asset(db, session_id, sha256)
    if existing is not None:
        return StoredUpload(asset=existing, created=False, job=None)

    photo = decode_photo(file, _territory_zone(db, territory_id)) if kind is VisionAssetKind.photo else None
    # Release the connection for the (possibly long) upload.
    db.commit()
    token = secrets.token_hex(16)
    key = f"session/{session_id}/{token}{storage.extension_for(content_type)}"
    preview_key = f"session/{session_id}/{token}-preview.jpg"
    file.file.seek(0)
    try:
        storage.put_vision_object(key, file.file, size, content_type)
        if photo is not None:
            storage.put_vision_object(preview_key, io.BytesIO(photo.preview), len(photo.preview), "image/jpeg")
    except Exception:
        logger.error("Upload to session %s failed; an unreferenced object %s may remain in the bucket", session_id, key)
        raise

    name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()[:255] or None
    asset = VisionAsset(
        session_id=session_id,
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
    try:
        with db.begin_nested():
            if photo is not None:
                asset.width, asset.height, asset.taken_at = photo.width, photo.height, photo.taken_at
                asset.location = make_point(photo.lat, photo.lon)
            db.add(asset)
            db.flush()
            if photo is not None:
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
                job = VisionJob(
                    asset_id=asset.id, kind=VisionJobKind.extract_frames, idempotency_key=f"extract:{asset.id}:1"
                )
                db.add(job)
            db.flush()
    except IntegrityError:
        # The same file was recorded by a concurrent request; the object stored above stays as an orphan.
        logger.warning(
            "Concurrent upload of sha256 %s to session %s; object %s is unreferenced", sha256, session_id, key
        )
        existing = _existing_asset(db, session_id, sha256)
        if existing is None:
            raise
        return StoredUpload(asset=existing, created=False, job=None)
    db.refresh(asset)
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


def dispatch_ocr(finding_id: int) -> bool:
    """Queue the recognition of a marked area. Call after the status is committed; False when the broker is down."""
    if not get_settings().events_enabled:
        return True
    try:
        celery_app.send_task("vision.ocr_region", args=[finding_id], queue="vision", retry=False, ignore_result=True)
    except Exception:
        logger.exception("Failed to enqueue vision.ocr_region for finding %s", finding_id)
        return False
    return True


def dispatch_detect(run: VisionRun) -> bool:
    """Queue a detector run. Call after the run is committed; False when the broker is down."""
    if not get_settings().events_enabled:
        return True
    try:
        celery_app.send_task("vision.detect", args=[run.id], queue="vision", retry=False, ignore_result=True)
    except Exception:
        logger.exception("Failed to enqueue vision.detect for run %s", run.id)
        return False
    return True


def queue_run(db: Session, run: VisionRun) -> None:
    """Queue a committed run. If the queue is down the run is failed (visible, can be repeated), not lost."""
    if not dispatch_detect(run):
        run.status, run.error_code, run.finished_at = VisionRunStatus.failed, "queue_unavailable", datetime.now(UTC)
        db.commit()


def start_automatic_run(db: Session, session_id: int, asset_id: int) -> None:
    """The run that follows an upload (a photo) or the end of frame extraction (a video), when a detector is on."""
    if get_settings().vision_detector_backend == "disabled":
        return
    run = VisionRun(session_id=session_id, asset_id=asset_id)
    db.add(run)
    db.commit()
    queue_run(db, run)


def mark_job_unqueued(db: Session, job: VisionJob) -> None:
    """Nothing will process the video, so the asset is failed too: the UI stops polling and offers a retry."""
    job.status = VisionJobStatus.failed
    job.error_code = "queue_unavailable"
    job.error_message = "Не удалось поставить обработку видео в очередь"
    asset = db.get(VisionAsset, job.asset_id)
    if asset is not None:
        asset.status = VisionAssetStatus.failed
        asset.error_code = "queue_unavailable"
    db.commit()


# ---------------------------------------------------------------- findings


def apply_review(
    db: Session,
    finding: VisionFinding,
    user: AppUser,
    action: VisionReviewAction,
    comment: str | None,
    status: VisionFindingStatus | None = None,
) -> VisionReview:
    """Record a decision. `status` (the person's new judgement of the finding) is stored with it."""
    if action is VisionReviewAction.not_applicable:
        status = VisionFindingStatus.not_applicable
    elif status is VisionFindingStatus.not_applicable:
        raise api_error(422, "status_not_allowed", "Статус «не применимо» выставляется действием not_applicable")
    if action is VisionReviewAction.confirm and status is None and finding.status is VisionFindingStatus.not_applicable:
        raise api_error(409, "finding_not_applicable", "Находка помечена как неприменимая: укажите новый статус")
    review = VisionReview(finding_id=finding.id, action=action, comment=comment, reviewer_id=user.id, status=status)
    db.add(review)
    new_state = REVIEW_TRANSITIONS.get(action)
    if new_state is not None:
        finding.review_state = new_state
    if status is not None:
        finding.status = status
    db.flush()
    return review


def read_object(bucket: str, key: str) -> bytes:
    """A stored picture as bytes (frames are bounded by the photo limit)."""
    try:
        response = storage.get_client().get_object(bucket, key)
    except S3Error as exc:
        raise api_error(502, "vision_object_missing", "Файл недоступен в хранилище") from exc
    return b"".join(storage.stream_object(response))


def reopen_if_reviewed(db: Session, vision_session: VisionSession, user: AppUser, request: Request | None) -> None:
    """New material in a session a person has marked reviewed puts it back to `open`.

    `reviewed_by/at` are cleared (a reviewed session is one with a current review); the previous values stay in
    the audit record written here.
    """
    if vision_session.status is not VisionSessionStatus.reviewed:
        return
    before = audit.snapshot(vision_session)
    vision_session.status = VisionSessionStatus.open
    vision_session.reviewed_by = None
    vision_session.reviewed_at = None
    db.flush()
    audit.record(
        db,
        user,
        "vision_session.reopen",
        "vision_session",
        vision_session.id,
        before,
        audit.snapshot(vision_session),
        request,
    )
