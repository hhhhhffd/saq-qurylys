"""Celery tasks of SAQ VISION, run by the `vision-worker` (queue `vision`).

Frames and previews are written to the Object Lock bucket, where objects cannot be deleted. Every attempt therefore
writes under keys of its own (`<job id>-<attempt>-...`); the objects of an abandoned attempt stay as unreferenced
orphans (their rows never existed, see below) and are never overwritten.

The `vision_frame` rows of a video are inserted in one transaction at the very end, so a crashed or failed attempt
leaves no rows: nobody can attach a finding to a frame of an unfinished run, and a redelivery starts from nothing.
"""

import io
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import urllib3.exceptions
from celery.exceptions import SoftTimeLimitExceeded
from minio.error import S3Error
from PIL import Image
from pytesseract import TesseractError
from sqlalchemy import delete, exists
from sqlalchemy.orm import Session

from app import storage
from app.db import get_sessionmaker
from app.models import VisionAsset, VisionFinding, VisionFrame, VisionJob
from app.models.enums import OcrStatus, VisionAssetStatus, VisionJobKind, VisionJobStatus
from app.modules.nlp.ocr import ocr_image
from app.modules.vision import media
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

SOFT_LIMIT_S = 1800
HARD_LIMIT_S = 1860
OCR_SOFT_LIMIT_S = 120
OCR_HARD_LIMIT_S = 150
MAX_RETRIES = 3
RETRY_DELAY_S = 30
PROGRESS_STEP = 10  # frames between committed progress updates
TRANSIENT_S3_CODES = frozenset(
    {"InternalError", "SlowDown", "ServiceUnavailable", "RequestTimeout", "RequestTimeTooSkewed"}
)


class TransientStorageError(Exception):
    """MinIO is unreachable or overloaded; the same work is worth repeating a little later."""


def _transient(exc: Exception) -> bool:
    if isinstance(exc, S3Error):
        return exc.code in TRANSIENT_S3_CODES
    return isinstance(exc, urllib3.exceptions.HTTPError | ConnectionError | TimeoutError)


def _fail_job(session: Session, job_id: int, code: str, message: str) -> None:
    session.rollback()
    job = session.get(VisionJob, job_id)
    if job is None:
        return
    asset = session.get(VisionAsset, job.asset_id)
    job.status = VisionJobStatus.failed
    job.error_code, job.error_message = code, message
    job.finished_at = datetime.now(UTC)
    if asset is not None:
        asset.status = VisionAssetStatus.failed
        asset.error_code = code
    session.commit()
    logger.warning("vision.extract_frames: job %s failed: %s", job_id, code)


def _set_progress(session: Session, job: VisionJob, progress: int) -> None:
    job.progress = min(progress, 99)
    session.commit()


def _store_frames(
    session: Session, job: VisionJob, asset: VisionAsset, files: list[Path], interval_s: float
) -> list[VisionFrame]:
    """Upload every kept frame and its preview; the rows are returned (added, not committed) for one final insert."""
    prefix = f"session/{asset.session_id}/frames/{job.id}-{job.attempts}"
    frames: list[VisionFrame] = []
    previous_hash: int | None = None
    for index, path in enumerate(files):
        with Image.open(path) as image:
            image.load()
            score = media.sharpness(image)
            current_hash = media.dhash(image)
            # A still camera or a hover repeats the same view; only the first of a run is kept.
            if previous_hash is not None and media.is_duplicate(previous_hash, current_hash):
                continue
            previous_hash = current_hash
            width, height = image.size
            preview = media.make_preview(image)
        key = f"{prefix}-{index:05d}.jpg"
        preview_key = f"{prefix}-{index:05d}-preview.jpg"
        with path.open("rb") as handle:
            storage.put_vision_object(key, handle, path.stat().st_size, "image/jpeg")
        storage.put_vision_object(preview_key, io.BytesIO(preview), len(preview), "image/jpeg")
        frames.append(
            VisionFrame(
                asset_id=asset.id,
                timestamp_ms=round(index * interval_s * 1000),
                bucket=asset.bucket,
                s3_key=key,
                preview_key=preview_key,
                width=width,
                height=height,
                sharpness=round(score, 2),
                # Blurred frames are kept for the record but marked; the UI offers only usable ones first.
                usable=media.is_sharp(score),
            )
        )
        if len(frames) % PROGRESS_STEP == 0:
            _set_progress(session, job, 40 + 55 * (index + 1) // len(files))
    return frames


def extract_frames_for_job(session: Session, job_id: int) -> None:
    """Process one extraction job. Raises TransientStorageError for storage trouble worth retrying.

    Idempotent: a completed job is left alone; a job found running or failed (redelivery) starts over.
    """
    job = session.get(VisionJob, job_id)
    if job is None or job.kind is not VisionJobKind.extract_frames:
        logger.warning("vision.extract_frames: job %s does not exist", job_id)
        return
    if job.status is VisionJobStatus.completed:
        return
    asset = session.get(VisionAsset, job.asset_id)
    if asset is None:
        logger.warning("vision.extract_frames: asset %s of job %s does not exist", job.asset_id, job_id)
        return

    job.status, job.progress, job.attempts = VisionJobStatus.running, 0, job.attempts + 1
    job.started_at, job.finished_at, job.error_code, job.error_message = datetime.now(UTC), None, None, None
    asset.status, asset.error_code = VisionAssetStatus.processing, None
    # Rows of an earlier run that nothing refers to (normally there are none, see the module docstring).
    session.execute(
        delete(VisionFrame).where(
            VisionFrame.asset_id == asset.id,
            ~exists().where(VisionFinding.frame_id == VisionFrame.id),
        )
    )
    session.commit()

    try:
        with tempfile.TemporaryDirectory(prefix="vision-") as workdir:
            source = Path(workdir) / "source"
            frames_dir = Path(workdir) / "frames"
            frames_dir.mkdir()
            try:
                storage.get_client().fget_object(asset.bucket, asset.s3_key, str(source))
            except S3Error as exc:
                if exc.code in {"NoSuchKey", "NoSuchBucket"}:
                    raise media.MediaError("source_missing", "Исходный файл недоступен в хранилище") from exc
                raise
            _set_progress(session, job, 10)
            info = media.probe_video(source)
            _set_progress(session, job, 15)
            interval_s = media.frame_interval_s(info.duration_s)
            files = media.extract_frames(source, frames_dir, interval_s)
            _set_progress(session, job, 40)
            with Image.open(files[0]) as first:
                # After autorotation, so these are the dimensions people see.
                asset.width, asset.height = first.size
            asset.duration_ms = round(info.duration_s * 1000) if info.duration_s is not None else None
            frames = _store_frames(session, job, asset, files, interval_s)
    except media.MediaError as exc:
        _fail_job(session, job_id, exc.code, exc.message)
        return
    except SoftTimeLimitExceeded:
        _fail_job(session, job_id, "processing_timeout", "Обработка видео не уложилась в отведённое время")
        return
    except (S3Error, urllib3.exceptions.HTTPError, ConnectionError, TimeoutError) as exc:
        if _transient(exc):
            session.rollback()
            raise TransientStorageError(str(exc)) from exc
        logger.exception("vision.extract_frames: storage error in job %s", job_id)
        _fail_job(session, job_id, "storage_error", "Ошибка хранилища при обработке видео")
        return
    except Exception:
        logger.exception("vision.extract_frames: unexpected failure in job %s", job_id)
        _fail_job(session, job_id, "processing_error", "Непредвиденная ошибка обработки видео")
        return

    session.add_all(frames)
    job.status, job.progress, job.finished_at = VisionJobStatus.completed, 100, datetime.now(UTC)
    asset.status = VisionAssetStatus.ready
    session.commit()


@celery_app.task(
    name="vision.extract_frames",
    bind=True,
    soft_time_limit=SOFT_LIMIT_S,
    time_limit=HARD_LIMIT_S,
    max_retries=MAX_RETRIES,
)
def extract_frames(self, job_id: int) -> None:  # type: ignore[no-untyped-def]
    with get_sessionmaker()() as session:
        try:
            extract_frames_for_job(session, job_id)
        except TransientStorageError as exc:
            if self.request.retries >= MAX_RETRIES:
                _fail_job(session, job_id, "storage_unavailable", "Хранилище недоступно, повторите обработку позже")
                return
            raise self.retry(exc=exc, countdown=RETRY_DELAY_S) from exc


def run_ocr(session: Session, finding_id: int) -> None:
    """Recognise the marked area of a finding. Machine output only: a person confirms or edits the text later."""
    finding = session.get(VisionFinding, finding_id)
    if finding is None:
        logger.warning("vision.ocr_region: finding %s does not exist", finding_id)
        return
    if finding.ocr_status is not OcrStatus.pending:
        return  # already done or failed: a redelivery changes nothing
    frame = session.get(VisionFrame, finding.frame_id) if finding.frame_id is not None else None
    if frame is None or finding.bbox is None:
        finding.ocr_status = OcrStatus.failed
        session.commit()
        return
    try:
        response = storage.get_client().get_object(frame.bucket, frame.s3_key)
        data = b"".join(storage.stream_object(response))
        result = ocr_image(media.crop_region(data, finding.bbox))
    except (S3Error, OSError, TesseractError, RuntimeError, Image.DecompressionBombError) as exc:
        # RuntimeError is what pytesseract raises on its timeout; OSError covers a missing binary and broken images.
        logger.warning("vision.ocr_region: finding %s not recognised: %s", finding_id, exc)
        session.rollback()
        finding = session.get(VisionFinding, finding_id)
        if finding is not None:
            finding.ocr_status = OcrStatus.failed
            session.commit()
        return
    finding.ocr_text, finding.ocr_confidence, finding.ocr_engine = result.text, result.confidence, result.engine
    finding.ocr_status = OcrStatus.done
    session.commit()


@celery_app.task(name="vision.ocr_region", soft_time_limit=OCR_SOFT_LIMIT_S, time_limit=OCR_HARD_LIMIT_S)
def ocr_region(finding_id: int) -> None:
    with get_sessionmaker()() as session:
        run_ocr(session, finding_id)
