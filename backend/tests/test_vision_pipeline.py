"""Video pipeline of SAQ VISION: frame quality helpers, the extraction task, retry and Range requests.

Tests that need ffmpeg run only where it is installed (the `vision` image); the rest stub the media layer.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import urllib3.exceptions
from fastapi.testclient import TestClient
from minio.error import S3Error
from PIL import Image, ImageDraw, ImageFilter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import storage
from app.config import get_settings
from app.models import AuditLog, VisionAsset, VisionFrame, VisionJob
from app.models.enums import VisionAssetStatus, VisionJobStatus
from app.modules.vision import media, tasks
from app.worker.celery_app import celery_app
from tests.conftest import World, auth
from tests.test_vision_api import MP4_BYTES, VISION, create_session, make_jpeg, photo_frame, upload

pytestmark = pytest.mark.usefixtures("vision_bucket")

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg is not installed"
)


# ---------------------------------------------------------------- frame quality


def rectangle(left: bool) -> Image.Image:
    image = Image.new("L", (400, 300), 255)
    ImageDraw.Draw(image).rectangle((20, 20, 180, 280) if left else (220, 20, 380, 280), fill=0)
    return image


def gradient(bright_to_dark: bool) -> Image.Image:
    image = Image.new("L", (400, 300))
    image.putdata([255 - x * 255 // 399 if bright_to_dark else x * 255 // 399 for _ in range(300) for x in range(400)])
    return image


def test_sharpness_separates_detailed_from_blurred_frames() -> None:
    sharp = media.sharpness(rectangle(True))
    blurred = media.sharpness(rectangle(True).filter(ImageFilter.GaussianBlur(25)))
    assert sharp > media.BLUR_THRESHOLD > blurred
    assert media.is_sharp(sharp) and not media.is_sharp(blurred)
    assert media.sharpness(Image.new("L", (100, 100), 128)) == 0


def test_dhash_finds_repeated_views() -> None:
    first = media.dhash(rectangle(True))
    assert media.is_duplicate(first, media.dhash(rectangle(True)))
    # JPEG noise or a tiny shift does not make a new view...
    assert media.is_duplicate(first, media.dhash(rectangle(True).filter(ImageFilter.GaussianBlur(1))))
    # ...a different view does.
    assert not media.is_duplicate(first, media.dhash(rectangle(False)))
    assert not media.is_duplicate(first, media.dhash(gradient(True)))


def test_preview_is_bounded() -> None:
    preview = media.make_preview(Image.new("RGB", (2000, 1000)))
    with Image.open(__import__("io").BytesIO(preview)) as image:
        assert image.size == (640, 320)


def test_frame_interval_stretches_to_cover_the_whole_video(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "vision_frame_interval_seconds", 3)
    monkeypatch.setattr(settings, "vision_max_frames", 400)
    assert media.frame_interval_s(60) == 3
    assert media.frame_interval_s(None) == 3
    assert media.frame_interval_s(1800) == 4.5  # 400 frames over 30 minutes


def probe_json(*streams: dict[str, Any], duration: str | None = "10.0") -> str:
    return json.dumps({"streams": list(streams), "format": {"duration": duration} if duration else {}})


VIDEO_STREAM = {"codec_type": "video", "width": 1920, "height": 1080}


def test_probe_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    info = media.parse_probe(probe_json(VIDEO_STREAM, {"codec_type": "audio"}))
    assert (info.width, info.height, info.duration_s) == (1920, 1080, 10.0)
    assert media.parse_probe(probe_json(VIDEO_STREAM, duration=None)).duration_s is None

    def code(output: str) -> str:
        with pytest.raises(media.MediaError) as caught:
            media.parse_probe(output)
        return caught.value.code

    assert code(probe_json({"codec_type": "audio"})) == "video_no_stream"
    cover = {**VIDEO_STREAM, "disposition": {"attached_pic": 1}}
    assert code(probe_json(cover)) == "video_no_stream"
    assert code("not json") == "video_undecodable"
    assert code(probe_json({"codec_type": "video", "width": 0, "height": 0})) == "video_bad_dimensions"
    assert code(probe_json({"codec_type": "video", "width": 20000, "height": 100})) == "video_bad_dimensions"
    monkeypatch.setattr(get_settings(), "vision_max_duration_seconds", 5)
    assert code(probe_json(VIDEO_STREAM)) == "video_too_long"


def test_missing_ffmpeg_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def absent(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(media.subprocess, "run", absent)
    with pytest.raises(media.MediaError) as caught:
        media.probe_video(tmp_path / "x")
    assert caught.value.code == "ffmpeg_missing"


# ---------------------------------------------------------------- the extraction task


def make_video_job(
    client: TestClient, db: Session, user: Any, data: bytes = MP4_BYTES
) -> tuple[VisionAsset, VisionJob]:
    session = create_session(client, user)
    response = upload(client, user, session["id"], data, "flight.mp4")
    assert response.status_code == 201, response.text
    asset = db.get(VisionAsset, response.json()["id"])
    assert asset is not None
    job = db.scalars(select(VisionJob).where(VisionJob.asset_id == asset.id)).one()
    return asset, job


@pytest.fixture
def stub_media(monkeypatch: pytest.MonkeyPatch) -> list[Image.Image]:
    """Four 'frames' for a 10 s video: a view, the same view, a blurred one, and another sharp view."""
    views = [
        rectangle(True),
        rectangle(True),
        gradient(True).filter(ImageFilter.GaussianBlur(3)),
        rectangle(False),
    ]
    monkeypatch.setattr(media, "probe_video", lambda path: media.VideoInfo(width=400, height=300, duration_s=10.0))

    def fake_extract(path: Path, out_dir: Path, interval_s: float) -> list[Path]:
        paths = []
        for index, view in enumerate(views):
            target = out_dir / f"frame_{index + 1:05d}.jpg"
            view.convert("RGB").save(target, "JPEG")
            paths.append(target)
        return paths

    monkeypatch.setattr(media, "extract_frames", fake_extract)
    return views


def frames_of(db: Session, asset: VisionAsset) -> list[VisionFrame]:
    return list(db.scalars(select(VisionFrame).where(VisionFrame.asset_id == asset.id).order_by(VisionFrame.id)))


def test_task_extracts_filters_and_stores_frames(
    client: TestClient, db: Session, world: World, stub_media: list[Image.Image]
) -> None:
    asset, job = make_video_job(client, db, world.users["mio_ust"])
    tasks.extract_frames_for_job(db, job.id)
    db.refresh(asset)
    db.refresh(job)

    assert (job.status, job.progress, job.attempts) == (VisionJobStatus.completed, 100, 1)
    assert job.started_at is not None and job.finished_at is not None and job.error_code is None
    assert asset.status is VisionAssetStatus.ready
    assert (asset.width, asset.height, asset.duration_ms) == (400, 300, 10000)
    frames = frames_of(db, asset)
    # The repeated view is dropped; the blurred one is kept but marked.
    assert [(f.timestamp_ms, f.usable) for f in frames] == [(0, True), (6000, False), (9000, True)]
    assert all(f.sharpness is not None for f in frames)
    for frame in frames:
        assert (storage.get_client().stat_object(frame.bucket, frame.s3_key).size or 0) > 0
        assert (storage.get_client().stat_object(frame.bucket, frame.preview_key).size or 0) > 0

    shown = client.get(f"{VISION}/sessions/{asset.session_id}/frames", headers=auth(world.users["mio_ust"])).json()
    assert shown["total"] == 3


def test_completed_job_is_not_processed_again(
    client: TestClient, db: Session, world: World, stub_media: list[Image.Image]
) -> None:
    asset, job = make_video_job(client, db, world.users["mio_ust"])
    tasks.extract_frames_for_job(db, job.id)
    first = [(f.id, f.s3_key) for f in frames_of(db, asset)]
    tasks.extract_frames_for_job(db, job.id)
    db.refresh(job)
    assert job.attempts == 1
    assert [(f.id, f.s3_key) for f in frames_of(db, asset)] == first


def test_redelivery_of_an_unfinished_job_starts_over_with_fresh_keys(
    client: TestClient, db: Session, world: World, stub_media: list[Image.Image]
) -> None:
    asset, job = make_video_job(client, db, world.users["mio_ust"])
    tasks.extract_frames_for_job(db, job.id)
    old_keys = {f.s3_key for f in frames_of(db, asset)}
    # The worker died after the frames were written but before the job was marked completed.
    job.status = VisionJobStatus.running
    db.commit()
    tasks.extract_frames_for_job(db, job.id)
    db.refresh(job)
    frames = frames_of(db, asset)
    assert (job.status, job.attempts) == (VisionJobStatus.completed, 2)
    assert len(frames) == 3
    assert not old_keys & {f.s3_key for f in frames}


def test_unknown_job_is_ignored(db: Session) -> None:
    tasks.extract_frames_for_job(db, 987654)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (media.MediaError("video_no_stream", "нет дорожки"), "video_no_stream"),
        (media.MediaError("video_too_long", "длинное"), "video_too_long"),
        (media.MediaError("ffmpeg_missing", "нет ffmpeg"), "ffmpeg_missing"),
    ],
)
def test_media_errors_fail_the_job_and_the_asset(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch, error: media.MediaError, code: str
) -> None:
    def refuse(path: Path) -> media.VideoInfo:
        raise error

    monkeypatch.setattr(media, "probe_video", refuse)
    asset, job = make_video_job(client, db, world.users["mio_ust"])
    tasks.extract_frames_for_job(db, job.id)
    db.refresh(asset)
    db.refresh(job)
    assert (job.status, job.error_code, job.error_message) == (VisionJobStatus.failed, code, error.message)
    assert (asset.status, asset.error_code) == (VisionAssetStatus.failed, code)
    assert frames_of(db, asset) == []
    detail = client.get(f"{VISION}/sessions/{asset.session_id}", headers=auth(world.users["mio_ust"])).json()
    assert (detail["failed"], detail["processing"]) == (True, False)


def test_unexpected_failure_is_recorded_without_details(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(path: Path) -> media.VideoInfo:
        raise ValueError("secret internals")

    monkeypatch.setattr(media, "probe_video", explode)
    _, job = make_video_job(client, db, world.users["mio_ust"])
    tasks.extract_frames_for_job(db, job.id)
    db.refresh(job)
    assert job.error_code == "processing_error"
    assert "secret" not in (job.error_message or "")


def test_storage_trouble_is_transient_but_a_missing_source_is_not(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset, job = make_video_job(client, db, world.users["mio_ust"])

    class Broken:
        def __init__(self, error: Exception) -> None:
            self.error = error

        def fget_object(self, *args: object) -> None:
            raise self.error

    monkeypatch.setattr(storage, "get_client", lambda: Broken(urllib3.exceptions.MaxRetryError(None, "/x")))  # type: ignore[arg-type]
    with pytest.raises(tasks.TransientStorageError):
        tasks.extract_frames_for_job(db, job.id)
    db.refresh(asset)
    assert asset.status is VisionAssetStatus.processing  # not failed: the task will be retried

    missing = S3Error(None, "NoSuchKey", "gone", "/x", "r", "h")  # type: ignore[arg-type]
    monkeypatch.setattr(storage, "get_client", lambda: Broken(missing))
    tasks.extract_frames_for_job(db, job.id)
    db.refresh(job)
    assert job.error_code == "source_missing"


def test_task_names_and_queue() -> None:
    assert "vision.extract_frames" in celery_app.tasks
    assert "vision.ocr_region" in celery_app.tasks
    assert celery_app.amqp.router.route({}, "vision.ocr_region")["queue"].name == "vision"


# ---------------------------------------------------------------- real ffmpeg


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args], check=True, timeout=120)  # noqa: S603, S607


@pytest.fixture
def test_video(tmp_path: Path) -> bytes:
    target = tmp_path / "test.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc2=duration=8:size=320x240:rate=10", "-pix_fmt", "yuv420p", str(target))
    return target.read_bytes()


@needs_ffmpeg
def test_real_video_is_decoded(client: TestClient, db: Session, world: World, test_video: bytes) -> None:
    asset, job = make_video_job(client, db, world.users["mio_ust"], test_video)
    tasks.extract_frames_for_job(db, job.id)
    db.refresh(asset)
    assert asset.status is VisionAssetStatus.ready
    assert (asset.width, asset.height) == (320, 240)
    assert asset.duration_ms is not None and 7500 <= asset.duration_ms <= 8500
    frames = frames_of(db, asset)
    assert frames and frames[0].timestamp_ms == 0
    assert all(frame.timestamp_ms % 3000 == 0 for frame in frames if frame.timestamp_ms is not None)
    body = storage.get_client().get_object(frames[0].bucket, frames[0].s3_key).read()
    assert body.startswith(b"\xff\xd8")


@needs_ffmpeg
def test_real_video_rotation_metadata_is_applied(
    client: TestClient, db: Session, world: World, test_video: bytes, tmp_path: Path
) -> None:
    source, rotated = tmp_path / "in.mp4", tmp_path / "rotated.mp4"
    source.write_bytes(test_video)
    ffmpeg("-i", str(source), "-c", "copy", "-metadata:s:v:0", "rotate=90", str(rotated))
    asset, job = make_video_job(client, db, world.users["mio_ust"], rotated.read_bytes())
    tasks.extract_frames_for_job(db, job.id)
    db.refresh(asset)
    assert (asset.width, asset.height) == (240, 320)


@needs_ffmpeg
def test_real_audio_only_file_has_no_video_stream(
    client: TestClient, db: Session, world: World, tmp_path: Path
) -> None:
    target = tmp_path / "audio.mp4"
    ffmpeg("-f", "lavfi", "-i", "sine=duration=2", "-c:a", "aac", str(target))
    _, job = make_video_job(client, db, world.users["mio_ust"], target.read_bytes())
    tasks.extract_frames_for_job(db, job.id)
    db.refresh(job)
    assert job.error_code == "video_no_stream"


@needs_ffmpeg
def test_real_video_over_the_duration_limit(
    client: TestClient, db: Session, world: World, test_video: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "vision_max_duration_seconds", 5)
    _, job = make_video_job(client, db, world.users["mio_ust"], test_video)
    tasks.extract_frames_for_job(db, job.id)
    db.refresh(job)
    assert job.error_code == "video_too_long"


@needs_ffmpeg
def test_real_garbage_is_undecodable(client: TestClient, db: Session, world: World) -> None:
    _, job = make_video_job(client, db, world.users["mio_ust"])
    tasks.extract_frames_for_job(db, job.id)
    db.refresh(job)
    assert job.error_code == "video_undecodable"


# ---------------------------------------------------------------- retry


def failed_video(client: TestClient, db: Session, user: Any) -> tuple[int, int]:
    asset, job = make_video_job(client, db, user)
    asset.status, asset.error_code = VisionAssetStatus.failed, "video_undecodable"
    job.status, job.error_code = VisionJobStatus.failed, "video_undecodable"
    db.commit()
    return asset.id, asset.session_id


def test_retry_creates_a_new_job_and_queues_it(
    client: TestClient, db: Session, world: World, sent_tasks: list[tuple[str, tuple[object, ...]]]
) -> None:
    user = world.users["mio_ust"]
    asset_id, _ = failed_video(client, db, user)
    sent_tasks.clear()
    response = client.post(f"{VISION}/assets/{asset_id}/retry", headers=auth(user))
    assert response.status_code == 200, response.text
    assert (response.json()["status"], response.json()["error_code"]) == ("queued", None)
    jobs = list(db.scalars(select(VisionJob).where(VisionJob.asset_id == asset_id).order_by(VisionJob.id)))
    assert [j.idempotency_key for j in jobs] == [f"extract:{asset_id}:1", f"extract:{asset_id}:2"]
    assert (jobs[1].status, jobs[1].attempts) == (VisionJobStatus.queued, 0)
    assert sent_tasks == [("vision.extract_frames", (jobs[1].id,))]
    assert db.scalars(select(AuditLog.action).where(AuditLog.action == "vision_asset.retry")).all() == [
        "vision_asset.retry"
    ]
    # Already queued again: a second click is refused.
    again = client.post(f"{VISION}/assets/{asset_id}/retry", headers=auth(user))
    assert (again.status_code, again.json()["detail"]["code"]) == (409, "asset_not_failed")


def test_retry_only_for_failed_videos(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    photo = photo_frame(client, user, session["id"])
    queued, _ = make_video_job(client, db, user)
    for asset_id in (photo["asset_id"], queued.id):
        response = client.post(f"{VISION}/assets/{asset_id}/retry", headers=auth(user))
        assert (response.status_code, response.json()["detail"]["code"]) == (409, "asset_not_failed")


def test_retry_access(client: TestClient, db: Session, world: World) -> None:
    asset_id, _ = failed_video(client, db, world.users["mio_ust"])
    url = f"{VISION}/assets/{asset_id}/retry"
    assert client.post(url, headers=auth(world.users["gask"])).status_code == 403
    assert client.post(url, headers=auth(world.users["law"])).status_code == 403
    assert client.post(url, headers=auth(world.users["mio_semey"])).status_code == 404
    assert client.post(url).status_code == 401


def test_retry_after_the_queue_was_down_at_upload(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = world.users["mio_ust"]
    monkeypatch.setattr(get_settings(), "events_enabled", True)

    def down(*args: object, **kwargs: object) -> None:
        raise ConnectionError("broker is down")

    monkeypatch.setattr(celery_app, "send_task", down)
    session = create_session(client, user)
    asset = upload(client, user, session["id"], MP4_BYTES).json()
    assert (asset["status"], asset["error_code"]) == ("failed", "queue_unavailable")

    sent: list[str] = []
    monkeypatch.setattr(celery_app, "send_task", lambda name, *a, **k: sent.append(name))
    response = client.post(f"{VISION}/assets/{asset['id']}/retry", headers=auth(user))
    assert response.status_code == 200
    assert (response.json()["status"], sent) == ("queued", ["vision.extract_frames"])

    # And when the broker is still down, the asset fails visibly again.
    monkeypatch.setattr(celery_app, "send_task", down)
    stored = db.get(VisionAsset, asset["id"])
    assert stored is not None
    stored.status = VisionAssetStatus.failed
    db.commit()
    again = client.post(f"{VISION}/assets/{asset['id']}/retry", headers=auth(user))
    assert (again.json()["status"], again.json()["error_code"]) == ("failed", "queue_unavailable")
    assert db.scalar(select(func.count()).select_from(VisionJob)) == 3


# ---------------------------------------------------------------- Range requests


@pytest.fixture
def video_asset(client: TestClient, db: Session, world: World) -> tuple[int, bytes, dict[str, str]]:
    data = MP4_BYTES + bytes(range(256)) * 8
    user = world.users["mio_ust"]
    session = create_session(client, user)
    asset = upload(client, user, session["id"], data).json()
    return asset["id"], data, auth(user)


def test_video_content_without_range_advertises_ranges(
    client: TestClient, video_asset: tuple[int, bytes, dict[str, str]]
) -> None:
    asset_id, data, headers = video_asset
    response = client.get(f"{VISION}/assets/{asset_id}/content", headers=headers)
    assert (response.status_code, response.content) == (200, data)
    assert response.headers["accept-ranges"] == "bytes"


@pytest.mark.parametrize(
    ("header", "start", "end"),
    [("bytes=0-9", 0, 9), ("bytes=100-", 100, -1), ("bytes=-16", -16, -1), ("bytes=10-99999999", 10, -1)],
)
def test_video_single_range(
    client: TestClient, video_asset: tuple[int, bytes, dict[str, str]], header: str, start: int, end: int
) -> None:
    asset_id, data, headers = video_asset
    response = client.get(f"{VISION}/assets/{asset_id}/content", headers={**headers, "Range": header})
    assert response.status_code == 206
    first = start if start >= 0 else len(data) + start
    last = len(data) - 1 if end == -1 else end
    assert response.content == data[first : last + 1]
    assert response.headers["content-range"] == f"bytes {first}-{last}/{len(data)}"
    assert response.headers["content-length"] == str(last - first + 1)


@pytest.mark.parametrize("header", ["bytes=999999-", "bytes=-0", "bytes=9-3"])
def test_unsatisfiable_range(client: TestClient, video_asset: tuple[int, bytes, dict[str, str]], header: str) -> None:
    asset_id, data, headers = video_asset
    response = client.get(f"{VISION}/assets/{asset_id}/content", headers={**headers, "Range": header})
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(data)}"


@pytest.mark.parametrize("header", ["bytes=0-1,5-6", "items=0-5", "bytes=abc", "bytes=-"])
def test_unsupported_range_serves_the_whole_file(
    client: TestClient, video_asset: tuple[int, bytes, dict[str, str]], header: str
) -> None:
    asset_id, data, headers = video_asset
    response = client.get(f"{VISION}/assets/{asset_id}/content", headers={**headers, "Range": header})
    assert (response.status_code, response.content) == (200, data)


def test_photo_ignores_range(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    data = make_jpeg()
    asset = upload(client, user, session["id"], data).json()
    response = client.get(f"{VISION}/assets/{asset['id']}/content", headers={**auth(user), "Range": "bytes=0-9"})
    assert (response.status_code, response.content) == (200, data)


def test_range_respects_territory(
    client: TestClient, video_asset: tuple[int, bytes, dict[str, str]], world: World
) -> None:
    asset_id, _, _ = video_asset
    response = client.get(
        f"{VISION}/assets/{asset_id}/content", headers={**auth(world.users["mio_semey"]), "Range": "bytes=0-9"}
    )
    assert response.status_code == 404
