"""SAQ VISION demo: survey sessions with drone video and photos, frames, detector runs and findings (`--demo`).

`seed_data/demo_vision.json` lists the sessions. The media is synthetic (`app.seed_media`: a stylized site with a
crane, a fence and a billboard drawn with Pillow; the two short flights `seed_data/demo_flight_*.mp4` were assembled
from such frames). The rows have the shape the pipeline leaves behind (`vision.tasks`): originals and previews in the
vision bucket under Object Lock, one frame per photo and per sampled second of a video, a completed run with its raw
detections, findings with the review trail, and the publications that staff made from the findings of outdoor
advertising. Nothing needs the GPU worker: no job is queued.
"""

import hashlib
import io
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from PIL import Image
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.config import get_settings
from app.geo import make_point
from app.models import (
    AdPost,
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
    AdOrigin,
    EvidenceKind,
    LinkMethod,
    OcrStatus,
    Platform,
    VisionAssetKind,
    VisionAssetStatus,
    VisionCategory,
    VisionFindingOrigin,
    VisionFindingStatus,
    VisionJobKind,
    VisionJobStatus,
    VisionReviewAction,
    VisionReviewState,
    VisionRunStatus,
    VisionSessionStatus,
    VisionSource,
)
from app.modules.vision import media
from app.seed import CITY_CODE, SEED_DATA_DIR, RelativeDateTime
from app.seed_media import feature_bbox, site_frame, to_jpeg
from app.storage import EvidenceLink

logger = logging.getLogger("app.seed")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


VISION_FILE = "demo_vision.json"
MODEL_VERSION = "demo-synthetic-1"
_REVIEW_ACTIONS = {
    VisionReviewState.confirmed: VisionReviewAction.confirm,
    VisionReviewState.rejected: VisionReviewAction.reject,
    VisionReviewState.needs_more_evidence: VisionReviewAction.needs_more_evidence,
}


class VisionScene(_Strict):
    name: str
    banner: str
    progress: float


class VisionAssetSpec(_Strict):
    name: str
    kind: VisionAssetKind
    file: str | None = None  # a video of seed_data
    duration_s: float | None = None
    frames_s: list[float] = []  # the sampled seconds of a video
    t: float = 0.0  # the moment of the flight a photo shows
    lat: float
    lon: float


class VisionFindingSpec(_Strict):
    asset: int
    frame_s: float | None = None
    feature: str
    category: VisionCategory
    status: VisionFindingStatus
    confidence: float
    origin: VisionFindingOrigin = VisionFindingOrigin.model
    note: str | None = None
    review: VisionReviewState = VisionReviewState.pending
    review_comment: str | None = None
    ocr_text: str | None = None
    ocr_confidence: float | None = None
    # Text of the publication staff made from the finding (outdoor advertising only).
    publish_text: str | None = None


class VisionSessionSpec(_Strict):
    object: str
    source: VisionSource
    captured_at: RelativeDateTime
    note: str
    status: VisionSessionStatus
    scene: VisionScene
    assets: list[VisionAssetSpec]
    findings: list[VisionFindingSpec]


class VisionData(_Strict):
    sessions: list[VisionSessionSpec]


def _put(key: str, data: bytes, content_type: str) -> None:
    storage.put_vision_object(key, io.BytesIO(data), len(data), content_type)


def _store_frame(
    session: Session, asset: VisionAsset, prefix: str, index: int, image: Image.Image, timestamp_ms: int | None
) -> VisionFrame:
    original = to_jpeg(image)
    key = f"{prefix}-{index:05d}.jpg"
    preview_key = f"{prefix}-{index:05d}-preview.jpg"
    _put(key, original, "image/jpeg")
    _put(preview_key, media.make_preview(image), "image/jpeg")
    frame = VisionFrame(
        asset_id=asset.id,
        timestamp_ms=timestamp_ms,
        bucket=asset.bucket,
        s3_key=key,
        preview_key=preview_key,
        width=image.width,
        height=image.height,
        sharpness=round(media.sharpness(image), 2),
        usable=True,
    )
    session.add(frame)
    session.flush()
    return frame


def _add_session(session: Session, spec: VisionSessionSpec, obj: ConstructionObject, mio: AppUser) -> int:
    settings = get_settings()
    now = datetime.now(UTC)
    vision_session = VisionSession(
        territory_id=obj.territory_id,
        object_id=obj.id,
        source=spec.source,
        captured_at=spec.captured_at,
        note=spec.note,
        status=spec.status,
        reviewed_by=mio.id if spec.status is VisionSessionStatus.reviewed else None,
        reviewed_at=min(spec.captured_at + timedelta(days=1), now)
        if spec.status is VisionSessionStatus.reviewed
        else None,
        created_by=mio.id,
        is_demo=True,
    )
    session.add(vision_session)
    session.flush()
    scene = spec.scene

    assets: list[VisionAsset] = []
    frames: dict[tuple[int, float | None], tuple[VisionFrame, Image.Image]] = {}
    for position, asset_spec in enumerate(spec.assets):
        token = secrets.token_hex(16)
        if asset_spec.kind is VisionAssetKind.video:
            if asset_spec.file is None:
                raise SystemExit(f"{VISION_FILE}: a video asset needs a file")
            data, content_type, key = (
                (SEED_DATA_DIR / asset_spec.file).read_bytes(),
                "video/mp4",
                f"session/{vision_session.id}/{token}.mp4",
            )
        else:
            image = site_frame(asset_spec.t, scene.name, scene.banner, scene.progress)
            data, content_type, key = to_jpeg(image), "image/jpeg", f"session/{vision_session.id}/{token}.jpg"
        _put(key, data, content_type)
        asset = VisionAsset(
            session_id=vision_session.id,
            kind=asset_spec.kind,
            original_name=asset_spec.name,
            content_type=content_type,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            bucket=settings.s3_bucket_vision,
            s3_key=key,
            width=960,
            height=540,
            duration_ms=round(asset_spec.duration_s * 1000) if asset_spec.duration_s else None,
            location=make_point(asset_spec.lat, asset_spec.lon),
            taken_at=spec.captured_at,
            status=VisionAssetStatus.ready,
            uploaded_by=mio.id,
        )
        session.add(asset)
        session.flush()
        assets.append(asset)
        if asset_spec.kind is VisionAssetKind.photo:
            frame = VisionFrame(
                asset_id=asset.id,
                timestamp_ms=None,
                bucket=asset.bucket,
                s3_key=key,
                preview_key=f"session/{vision_session.id}/{token}-preview.jpg",
                width=960,
                height=540,
                sharpness=round(media.sharpness(image), 2),
                usable=True,
            )
            _put(frame.preview_key, media.make_preview(image), "image/jpeg")
            session.add(frame)
            session.flush()
            frames[(position, None)] = (frame, image)
        else:
            started = spec.captured_at
            session.add(
                VisionJob(
                    asset_id=asset.id,
                    kind=VisionJobKind.extract_frames,
                    status=VisionJobStatus.completed,
                    progress=100,
                    attempts=1,
                    started_at=started,
                    finished_at=started + timedelta(minutes=2),
                    idempotency_key=f"extract:{asset.id}:1",
                )
            )
            prefix = f"session/{vision_session.id}/frames/{asset.id}-1"
            for index, second in enumerate(asset_spec.frames_s):
                image = site_frame(second, scene.name, scene.banner, scene.progress)
                frames[(position, second)] = (
                    _store_frame(session, asset, prefix, index, image, round(second * 1000)),
                    image,
                )

    model_findings = [f for f in spec.findings if f.origin is VisionFindingOrigin.model]
    run = VisionRun(
        session_id=vision_session.id,
        asset_id=None,
        status=VisionRunStatus.completed,
        model_version=MODEL_VERSION,
        config={"demo": True, "box_threshold": 0.45, "prompts": [c.value for c in VisionCategory]},
        frames_total=len(frames),
        frames_done=len(frames),
        started_at=spec.captured_at,
        finished_at=spec.captured_at + timedelta(minutes=3),
        created_by=None,
    )
    session.add(run)
    session.flush()

    for group_key, item in enumerate(spec.findings, start=1):
        frame, image = frames[(item.asset, item.frame_s)]
        bbox = feature_bbox(item.feature, item.frame_s if item.frame_s is not None else spec.assets[item.asset].t)
        detection_id = None
        if item in model_findings:
            detection = VisionDetection(
                run_id=run.id,
                frame_id=frame.id,
                category=item.category,
                label=item.category.value.replace("_", " "),
                bbox=bbox,
                confidence=item.confidence,
                group_key=group_key,
            )
            session.add(detection)
            session.flush()
            detection_id = detection.id
        finding = VisionFinding(
            session_id=vision_session.id,
            frame_id=frame.id,
            bbox=bbox,
            category=item.category,
            status=item.status,
            origin=item.origin,
            confidence=item.confidence if item.origin is VisionFindingOrigin.model else None,
            model_version=MODEL_VERSION if item.origin is VisionFindingOrigin.model else None,
            note=item.note,
            review_state=item.review,
            ocr_status=OcrStatus.done if item.ocr_text else None,
            ocr_text=item.ocr_text,
            ocr_confidence=item.ocr_confidence,
            run_id=run.id if detection_id else None,
            detection_id=detection_id,
            created_by=None if detection_id else mio.id,
        )
        session.add(finding)
        session.flush()
        if item.ocr_text:
            session.add(
                VisionJob(
                    asset_id=assets[item.asset].id,
                    kind=VisionJobKind.ocr_region,
                    status=VisionJobStatus.completed,
                    progress=100,
                    attempts=1,
                    started_at=spec.captured_at,
                    finished_at=spec.captured_at + timedelta(seconds=20),
                    idempotency_key=f"ocr:{finding.id}:1",
                )
            )
        action = _REVIEW_ACTIONS.get(item.review)
        if action is not None:
            session.add(
                VisionReview(
                    finding_id=finding.id,
                    action=action,
                    comment=item.review_comment,
                    status=item.status,
                    reviewer_id=mio.id,
                )
            )
        if item.publish_text:
            _publish(session, finding, item, spec, obj, assets[item.asset], image, bbox)
    return vision_session.id


def _publish(
    session: Session,
    finding: VisionFinding,
    item: VisionFindingSpec,
    spec: VisionSessionSpec,
    obj: ConstructionObject,
    asset: VisionAsset,
    image: Image.Image,
    bbox: dict[str, float],
) -> None:
    """The publication staff made from a finding of outdoor advertising: the frame and the cut-out area as photos."""
    ad = AdPost(
        territory_id=obj.territory_id,
        platform=Platform.outdoor,
        external_id=f"vision-finding-{finding.id}",
        text=item.publish_text,
        captured_at=spec.captured_at,
        object_id=obj.id,
        link_method=LinkMethod.manual,
        link_confidence=1.0,
        is_outdoor=True,
        location=make_point(asset.lat, asset.lon),
        origin=AdOrigin.vision,
        ocr_status=OcrStatus.done if item.ocr_text else None,
        is_demo=True,
    )
    session.add(ad)
    session.flush()
    original = to_jpeg(image)
    for data in (original, media.crop_region(original, bbox)):
        storage.put_evidence(
            session,
            data,
            EvidenceKind.photo,
            "image/jpeg",
            link=EvidenceLink(ad_post_id=ad.id),
            created_by=finding.created_by,
            captured_at=spec.captured_at,
        )
    finding.confirmed_text = item.publish_text
    finding.ad_post_id = ad.id
    session.flush()


def seed_demo_vision(session: Session) -> list[tuple[int, int | None]]:
    """Create the missing demo sessions; returns the publications they made (id, object id) for the processing chain.
    A session is found again by its note. Flushed, not committed."""
    path = SEED_DATA_DIR / VISION_FILE
    if not path.exists():
        logger.warning("%s not found: no demo vision sessions loaded", path)
        return []
    try:
        data = VisionData.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise SystemExit(f"{VISION_FILE} is invalid:\n{exc}") from exc
    mio = session.scalar(select(AppUser).where(AppUser.username == "demo_mio"))
    city = session.scalar(select(Territory.id).where(Territory.code == CITY_CODE))
    if mio is None or city is None:
        raise SystemExit("the demo vision sessions need the demo users and the city: run the demo seed first")
    objects: dict[str, ConstructionObject] = {
        obj.name: obj for obj in session.scalars(select(ConstructionObject).where(ConstructionObject.is_demo))
    }
    created: list[Any] = []
    for spec in data.sessions:
        obj = objects.get(spec.object)
        if obj is None:
            raise SystemExit(f"{VISION_FILE}: unknown demo object {spec.object!r}")
        if session.scalar(select(VisionSession.id).where(VisionSession.is_demo, VisionSession.note == spec.note)):
            continue
        session_id = _add_session(session, spec, obj, mio)
        created.append(session_id)
    ads = session.execute(
        select(AdPost.id, AdPost.object_id).where(AdPost.origin == AdOrigin.vision, AdPost.is_demo)
    ).all()
    logger.info("Demo vision ready: %s new sessions", len(created))
    return [(row.id, row.object_id) for row in ads] if created else []
