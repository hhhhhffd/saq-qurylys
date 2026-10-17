"""Object detector of SAQ VISION (Stage 4): grouping, runs, status rules, reanalysis.

The detector itself is replaced by `FakeDetector`, a test double that returns scripted boxes: these tests check what
SAQ does with detections, not what the model sees. The real model is exercised by `test_real_model_*`, which is
skipped unless torch, transformers and the weights are present (the `vision` image).
"""

import re
from collections.abc import Callable, Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditLog, VisionAsset, VisionDetection, VisionFinding, VisionFrame, VisionRun
from app.models.enums import VisionAssetKind, VisionAssetStatus, VisionCategory, VisionFindingStatus, VisionRunStatus
from app.modules.vision import detector, service, tasks
from app.modules.vision.detector import Box, Detection
from tests.conftest import World, auth
from tests.test_vision_api import VISION, create_session, make_jpeg, photo_frame, upload
from tests.test_vision_pipeline import make_video_job, stub_media  # noqa: F401  (fixture)

pytestmark = pytest.mark.usefixtures("vision_bucket")

CAT = VisionCategory


def det(
    category: VisionCategory, x: float = 0.1, y: float = 0.1, w: float = 0.3, h: float = 0.3, c: float = 0.8
) -> Detection:
    return Detection(category=category, label=detector.CATEGORY_PROMPTS[category][0], box=Box(x, y, w, h), confidence=c)


# ---------------------------------------------------------------- pure functions


def test_iou() -> None:
    a = Box(0, 0, 0.5, 0.5)
    assert detector.iou(a, a) == pytest.approx(1.0)
    assert detector.iou(a, Box(0.5, 0.5, 0.5, 0.5)) == 0
    assert detector.iou(a, Box(0.25, 0, 0.5, 0.5)) == pytest.approx(1 / 3)


def test_boxes_are_clipped_to_the_frame_and_empty_ones_dropped() -> None:
    assert detector.box_from_corners(-0.1, 0.2, 0.5, 1.2) == Box(0, 0.2, 0.5, pytest.approx(0.8))  # type: ignore[arg-type]
    assert detector.box_from_corners(0.5, 0.5, 0.5, 0.9) is None
    assert detector.box_from_corners(1.1, 0.1, 1.5, 0.9) is None


def test_model_boxes_are_mapped_to_fractions_of_the_frame() -> None:
    """The model answers with fractions (target size 1x1), so they hold for the original frame of any size."""
    model = object.__new__(detector.GroundingDinoDetector)
    found = model._detections(
        {
            "scores": [0.9, 0.6, 0.5],
            "boxes": [[0.1, 0.2, 0.5, 0.6], [0.0, 0.0, 1.0, 1.0], [0.1, 0.1, 0.2, 0.2]],
            "text_labels": ["construction fence", "pile of construction debris", "an unknown thing"],
        }
    )
    assert [(d.category, d.label) for d in found] == [
        (CAT.fence, "construction fence"),
        (CAT.debris, "pile of construction debris"),
    ]
    assert found[0].box == Box(0.1, 0.2, pytest.approx(0.4), pytest.approx(0.4))  # type: ignore[arg-type]
    assert found[0].confidence == pytest.approx(0.9)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("billboard", CAT.outdoor_ad),
        ("advertising banner", CAT.outdoor_ad),
        ("banner", CAT.outdoor_ad),  # part of a phrase
        ("skip", CAT.waste_container),
        ("fence", CAT.fence),
        ("garbage pile", CAT.debris),
        ("fence gate", None),  # two categories: not guessed
        ("", None),
        ("cat", None),
    ],
)
def test_labels_are_mapped_to_categories(label: str, expected: VisionCategory | None) -> None:
    match = detector.match_label(label)
    assert (match[0] if match else None) is expected


def test_prompt_lists_every_phrase_once() -> None:
    text = detector.prompt_text()
    assert text.count(".") == len(detector.PHRASE_CATEGORY) == 12
    assert text.startswith("billboard. advertising banner.")


def test_boxes_of_one_object_on_adjacent_frames_share_a_group() -> None:
    frames = [
        [det(CAT.fence, 0.10, 0.1)],
        [det(CAT.fence, 0.12, 0.1)],
        [det(CAT.fence, 0.14, 0.1), det(CAT.fence, 0.7, 0.6)],
        [det(CAT.fence, 0.7, 0.6)],
    ]
    keys = detector.assign_groups(frames)
    assert keys == [[1], [1], [1, 2], [2]]


def test_grouping_needs_the_same_category_and_enough_overlap() -> None:
    keys = detector.assign_groups(
        [[det(CAT.fence)], [det(CAT.debris)], [det(CAT.debris, 0.2, 0.1)], [det(CAT.debris, 0.8, 0.8, 0.1, 0.1)]]
    )
    # fence != debris; IoU of the two debris boxes is 0.5 -> grouped; the far one starts a new group.
    assert keys == [[1], [2], [2], [3]]


def test_a_box_joins_only_one_group_and_each_previous_box_is_used_once() -> None:
    one = det(CAT.waste_container, 0.1, 0.1, 0.4, 0.4)
    near_a = det(CAT.waste_container, 0.1, 0.1, 0.4, 0.4, 0.9)
    near_b = det(CAT.waste_container, 0.15, 0.1, 0.4, 0.4, 0.7)
    assert detector.assign_groups([[one], [near_a, near_b]]) == [[1], [1, 2]]


def test_photos_are_never_merged_and_keys_continue() -> None:
    assert detector.assign_groups([[det(CAT.fence), det(CAT.fence)]]) == [[1, 2]]
    assert detector.assign_groups([[det(CAT.fence)]], first_key=7) == [[7]]


# ---------------------------------------------------------------- test double and helpers


class FakeDetector:
    """A test double of the detector: answers frame by frame from a script, loads nothing."""

    model_version = "fake-detector@000000000000"
    device = "cpu"
    precision = "fp32"

    def __init__(self, script: Sequence[Sequence[Detection]] = ()) -> None:
        self.script = list(script)
        self.seen: list[tuple[int, int]] = []

    def detect(self, images: Sequence[Image.Image]) -> list[list[Detection]]:
        answers = []
        for image in images:
            self.seen.append(image.size)
            answers.append(list(self.script.pop(0)) if self.script else [])
        return answers


@pytest.fixture
def enable(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    """Turns the detector on when called: uploads made before that do not start automatic runs."""
    return lambda: monkeypatch.setattr(get_settings(), "vision_detector_backend", "grounding_dino")


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[Any, ...]]]:
    tasks_sent: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(get_settings(), "events_enabled", True)
    monkeypatch.setattr(
        service.celery_app, "send_task", lambda name, args=(), **kw: tasks_sent.append((name, tuple(args)))
    )
    return tasks_sent


def use(monkeypatch: pytest.MonkeyPatch, fake: FakeDetector) -> FakeDetector:
    monkeypatch.setattr(detector, "get_detector", lambda: fake)
    return fake


def detail(client: TestClient, user: Any, session_id: int) -> dict[str, Any]:
    response = client.get(f"{VISION}/sessions/{session_id}", headers=auth(user))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def reanalyze(client: TestClient, user: Any, session_id: int) -> Any:
    return client.post(f"{VISION}/sessions/{session_id}/reanalyze", headers=auth(user))


# ---------------------------------------------------------------- config and access


def test_config_reports_the_detector(client: TestClient, world: World, enable: Callable[[], None]) -> None:
    enable()
    body = client.get(f"{VISION}/config", headers=auth(world.users["mio_ust"])).json()
    assert body["detector_mode"] == "experimental_pretrained"
    assert body["detector_model"] == "IDEA-Research/grounding-dino-tiny"


def test_config_when_disabled(client: TestClient, world: World) -> None:
    body = client.get(f"{VISION}/config", headers=auth(world.users["mio_ust"])).json()
    assert (body["detector_mode"], body["detector_model"]) == ("disabled", None)


def test_reanalyze_is_refused_while_the_detector_is_disabled(client: TestClient, world: World) -> None:
    session = create_session(client, world.users["mio_ust"])
    response = reanalyze(client, world.users["mio_ust"], session["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "detector_disabled"


def test_reanalyze_access_matrix(
    client: TestClient, db: Session, world: World, enable: Callable[[], None], sent: list[Any]
) -> None:
    session = create_session(client, world.users["mio_ust"])
    enable()
    assert client.post(f"{VISION}/sessions/{session['id']}/reanalyze").status_code == 401
    assert reanalyze(client, world.users["gask"], session["id"]).status_code == 403
    assert reanalyze(client, world.users["law"], session["id"]).status_code == 403
    assert reanalyze(client, world.users["mio_semey"], session["id"]).status_code == 404
    assert reanalyze(client, world.users["mio_ust"], 987654).status_code == 404
    assert db.scalar(select(func.count()).select_from(VisionRun)) == 0
    assert reanalyze(client, world.users["mio_region"], session["id"]).status_code == 200


def test_reanalyze_queues_one_run_and_audits(
    client: TestClient, db: Session, world: World, enable: Callable[[], None], sent: list[Any]
) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    photo_frame(client, user, session["id"])
    sent.clear()
    enable()
    body = reanalyze(client, user, session["id"]).json()
    assert [(r["status"], r["asset_id"], r["summary"]) for r in body["runs"]] == [("queued", None, {})]
    assert body["processing"] is True
    assert sent == [("vision.detect", (body["runs"][0]["id"],))]
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "vision_run.create")) == 1
    again = reanalyze(client, user, session["id"])
    assert (again.status_code, again.json()["detail"]["code"]) == (409, "run_in_progress")


def test_run_fails_visibly_when_the_queue_is_down(
    client: TestClient, world: World, enable: Callable[[], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise ConnectionError("broker")

    monkeypatch.setattr(get_settings(), "events_enabled", True)
    monkeypatch.setattr(service.celery_app, "send_task", broken)
    session = create_session(client, world.users["mio_ust"])
    enable()
    run = reanalyze(client, world.users["mio_ust"], session["id"]).json()["runs"][0]
    assert (run["status"], run["error_code"]) == ("failed", "queue_unavailable")


# ---------------------------------------------------------------- a run


def make_run(db: Session, session_id: int, asset_id: int | None = None) -> VisionRun:
    run = VisionRun(session_id=session_id, asset_id=asset_id)
    db.add(run)
    db.commit()
    return run


def test_status_rules_and_absence_is_not_a_finding(
    client: TestClient, db: Session, world: World, enable: Callable[[], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    frame = photo_frame(client, user, session["id"])
    fake = use(
        monkeypatch,
        FakeDetector([[det(CAT.fence, c=0.7), det(CAT.debris, 0.5, 0.5, c=0.5), det(CAT.outdoor_ad, 0.6, 0.1, c=0.9)]]),
    )
    enable()
    run = make_run(db, session["id"])
    tasks.run_detection(db, run.id)
    db.refresh(run)

    assert (run.status, run.frames_total, run.frames_done, run.error_code) == (VisionRunStatus.completed, 1, 1, None)
    assert run.model_version == fake.model_version
    assert run.config["device"] == "cpu" and run.config["prompts"]["debris"]
    assert run.started_at is not None and run.finished_at is not None
    findings = {f.category: f for f in db.scalars(select(VisionFinding).where(VisionFinding.run_id == run.id))}
    # Only what was seen becomes a finding; nothing about waste containers, gates or wheel washing.
    assert set(findings) == {CAT.fence, CAT.debris, CAT.outdoor_ad}
    assert findings[CAT.fence].status is VisionFindingStatus.observed
    assert findings[CAT.outdoor_ad].status is VisionFindingStatus.observed
    assert findings[CAT.debris].status is VisionFindingStatus.possible_noncompliance
    for finding in findings.values():
        assert (finding.origin.value, finding.review_state.value) == ("model", "pending")
        assert (finding.model_version, finding.frame_id) == (fake.model_version, frame["id"])
        assert finding.detection_id is not None and finding.confidence is not None
    assert findings[CAT.fence].bbox == {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}

    body = detail(client, user, session["id"])
    out = body["runs"][0]
    assert out["summary"] == {
        "outdoor_ad": 1,
        "fence": 1,
        "site_gate": 0,
        "waste_container": 0,
        "wheel_wash": 0,
        "debris": 1,
    }
    assert out["status"] == "completed" and out["frames_done"] == 1 and body["processing"] is False
    assert {f["run_id"] for f in body["findings"]} == {run.id}


def test_detector_gets_a_shrunk_upright_copy(
    client: TestClient, db: Session, world: World, enable: Callable[[], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    upload(client, user, session["id"], make_jpeg(1600, 800, exif=True))  # Orientation 6: upright it is 800 x 1600
    enable()
    monkeypatch.setattr(get_settings(), "vision_detector_max_side", 400)
    fake = use(monkeypatch, FakeDetector())
    tasks.run_detection(db, make_run(db, session["id"]).id)
    assert fake.seen == [(200, 400)]


def test_unusable_frames_are_skipped(
    client: TestClient, db: Session, world: World, enable: Callable[[], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    frame = photo_frame(client, user, session["id"])
    db.get(VisionFrame, frame["id"]).usable = False  # type: ignore[union-attr]
    db.commit()
    enable()
    fake = use(monkeypatch, FakeDetector())
    run = make_run(db, session["id"])
    tasks.run_detection(db, run.id)
    db.refresh(run)
    assert (run.status, run.frames_total, fake.seen) == (VisionRunStatus.completed, 0, [])


def video_with_frames(db: Session, session_id: int, photo_frame_id: int, count: int, user_id: int) -> VisionAsset:
    """A video asset whose `count` frames all show the stored picture of an uploaded photo (content is irrelevant)."""
    photo = db.get(VisionFrame, photo_frame_id)
    assert photo is not None
    asset = VisionAsset(
        session_id=session_id,
        kind=VisionAssetKind.video,
        content_type="video/mp4",
        size_bytes=1,
        sha256="f" * 64,
        bucket=photo.bucket,
        s3_key=photo.s3_key,
        status=VisionAssetStatus.ready,
        uploaded_by=user_id,
        width=photo.width,
        height=photo.height,
    )
    db.add(asset)
    db.flush()
    db.add_all(
        VisionFrame(
            asset_id=asset.id,
            timestamp_ms=index * 3000,
            bucket=photo.bucket,
            s3_key=photo.s3_key,
            preview_key=photo.preview_key,
            width=photo.width,
            height=photo.height,
        )
        for index in range(count)
    )
    db.commit()
    return asset


def test_one_finding_per_group_with_the_most_confident_box(
    client: TestClient, db: Session, world: World, enable: Callable[[], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    photo = photo_frame(client, user, session["id"])
    asset = video_with_frames(db, session["id"], photo["id"], 4, user.id)
    script = [
        [det(CAT.waste_container, 0.10, c=0.5)],
        [det(CAT.waste_container, 0.12, c=0.9)],  # same container, best view
        [det(CAT.waste_container, 0.14, c=0.6), det(CAT.waste_container, 0.7, 0.7, c=0.4)],
        [],
    ]
    # The photo's own frame is processed first (asset order) and sees one fence.
    enable()
    use(monkeypatch, FakeDetector([[det(CAT.fence)], *script]))
    run = make_run(db, session["id"])
    tasks.run_detection(db, run.id)

    assert db.scalar(select(func.count()).select_from(VisionDetection).where(VisionDetection.run_id == run.id)) == 5
    findings = list(
        db.scalars(
            select(VisionFinding).where(VisionFinding.run_id == run.id, VisionFinding.category == CAT.waste_container)
        )
    )
    assert len(findings) == 2  # two physical containers, not four boxes
    best = max(findings, key=lambda f: f.confidence or 0)
    assert best.confidence == pytest.approx(0.9)
    frame = db.get(VisionFrame, best.frame_id)
    assert (frame.asset_id, frame.timestamp_ms) == (asset.id, 3000)  # type: ignore[union-attr]
    body = detail(client, user, session["id"])
    assert body["runs"][0]["summary"]["waste_container"] == 2 and body["runs"][0]["summary"]["fence"] == 1


def test_a_completed_run_is_not_processed_again_and_redelivery_does_not_duplicate(
    client: TestClient, db: Session, world: World, enable: Callable[[], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    photo_frame(client, user, session["id"])
    enable()
    fake = use(monkeypatch, FakeDetector([[det(CAT.fence)], [det(CAT.fence)]]))
    run = make_run(db, session["id"])
    tasks.run_detection(db, run.id)
    tasks.run_detection(db, run.id)
    assert len(fake.seen) == 1 and len(fake.script) == 1

    # The worker died after the results were written but before the broker was told.
    run.status = VisionRunStatus.running
    db.commit()
    tasks.run_detection(db, run.id)
    assert db.scalar(select(func.count()).select_from(VisionFinding).where(VisionFinding.run_id == run.id)) == 1
    assert db.scalar(select(func.count()).select_from(VisionDetection).where(VisionDetection.run_id == run.id)) == 1


def test_unknown_run_is_ignored(db: Session) -> None:
    tasks.run_detection(db, 987654)


def test_failures_are_recorded_on_the_run(
    client: TestClient, db: Session, world: World, enable: Callable[[], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    photo_frame(client, user, session["id"])

    def unavailable() -> detector.Detector:
        raise detector.DetectorUnavailable("no weights")

    monkeypatch.setattr(detector, "get_detector", unavailable)
    enable()
    run = make_run(db, session["id"])
    tasks.run_detection(db, run.id)
    db.refresh(run)
    assert (run.status, run.error_code) == (VisionRunStatus.failed, "detector_unavailable")

    class Exploding(FakeDetector):
        def detect(self, images: Sequence[Image.Image]) -> list[list[Detection]]:
            raise RuntimeError("secret internals")

    use(monkeypatch, Exploding())
    tasks.run_detection(db, run.id)  # a failed run may be delivered again
    db.refresh(run)
    assert (run.status, run.error_code) == (VisionRunStatus.failed, "detector_error")
    assert db.scalar(select(func.count()).select_from(VisionFinding).where(VisionFinding.run_id == run.id)) == 0
    assert detail(client, user, session["id"])["processing"] is False


def test_human_decisions_survive_a_new_run(
    client: TestClient, db: Session, world: World, enable: Callable[[], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    photo_frame(client, user, session["id"])
    enable()
    use(monkeypatch, FakeDetector([[det(CAT.debris)], [det(CAT.debris), det(CAT.fence, 0.6, 0.6)]]))
    first = make_run(db, session["id"])
    tasks.run_detection(db, first.id)
    old = db.scalars(select(VisionFinding).where(VisionFinding.run_id == first.id)).one()
    reviewed = client.post(
        f"{VISION}/findings/{old.id}/review",
        json={"action": "confirm", "status": "possible_noncompliance", "comment": "виден мусор"},
        headers=auth(user),
    )
    assert reviewed.status_code == 200

    body = reanalyze(client, user, session["id"]).json()
    second_id = body["runs"][-1]["id"]
    tasks.run_detection(db, second_id)
    db.refresh(old)
    assert (old.review_state.value, old.status, old.run_id) == (
        "confirmed",
        VisionFindingStatus.possible_noncompliance,
        first.id,
    )
    after = detail(client, user, session["id"])
    assert len(after["findings"]) == 3 and [r["status"] for r in after["runs"]] == ["completed", "completed"]
    assert [f["review_state"] for f in after["findings"] if f["run_id"] == second_id] == ["pending", "pending"]
    kept = next(f for f in after["findings"] if f["id"] == old.id)
    assert [r["comment"] for r in kept["reviews"]] == ["виден мусор"]


# ---------------------------------------------------------------- automatic runs


def test_a_photo_upload_starts_a_run_for_its_asset(
    client: TestClient, db: Session, world: World, enable: Callable[[], None], sent: list[Any]
) -> None:
    enable()
    user = world.users["mio_ust"]
    session = create_session(client, user)
    asset_id = upload(client, user, session["id"], make_jpeg()).json()["id"]
    run = db.scalars(select(VisionRun)).one()
    assert (run.asset_id, run.session_id, run.created_by, run.status) == (
        asset_id,
        session["id"],
        None,
        VisionRunStatus.queued,
    )
    assert sent == [("vision.detect", (run.id,))]
    assert detail(client, user, session["id"])["processing"] is True
    # The same file again is not a new photo.
    upload(client, user, session["id"], make_jpeg())
    assert db.scalar(select(func.count()).select_from(VisionRun)) == 1


def test_no_run_without_a_detector(client: TestClient, db: Session, world: World, sent: list[Any]) -> None:
    session = create_session(client, world.users["mio_ust"])
    upload(client, world.users["mio_ust"], session["id"], make_jpeg())
    assert db.scalar(select(func.count()).select_from(VisionRun)) == 0
    assert sent == []


def test_finished_frame_extraction_starts_a_run(
    client: TestClient,
    db: Session,
    world: World,
    enable: Callable[[], None],
    stub_media: list[Image.Image],  # noqa: F811
    sent: list[Any],
) -> None:
    enable()
    asset, job = make_video_job(client, db, world.users["mio_ust"])
    sent.clear()
    tasks.extract_frames_for_job(db, job.id)
    run = db.scalars(select(VisionRun)).one()
    assert (run.asset_id, run.session_id) == (asset.id, asset.session_id)
    assert sent == [("vision.detect", (run.id,))]


def test_task_names_and_queue() -> None:
    from app.worker.celery_app import celery_app

    assert "vision.detect" in celery_app.tasks
    assert celery_app.amqp.router.route({}, "vision.detect")["queue"].name == "vision"


# ---------------------------------------------------------------- the real model (skipped outside the vision image)


@pytest.fixture(scope="module")
def real_model() -> detector.GroundingDinoDetector:
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    settings = get_settings()
    try:
        return detector.GroundingDinoDetector(
            settings.vision_detector_model,
            "cpu",
            settings.vision_detector_box_threshold,
            settings.vision_detector_text_threshold,
            400,
        )
    except detector.DetectorUnavailable as exc:
        pytest.skip(str(exc))


def picture(width: int, height: int, shade: int) -> Image.Image:
    image = Image.new("RGB", (width, height), (shade, shade, shade))
    for x in range(0, width, 20):  # vertical stripes: something fence-like for the model to look at
        image.paste((30, 30, 30), (x, height // 3, x + 6, height))
    return image


def test_real_model_loads_and_answers_in_fractions(real_model: detector.GroundingDinoDetector) -> None:
    assert re.fullmatch(r"grounding-dino-tiny@[0-9a-f]{12}", real_model.model_version)
    images = [picture(320, 240, 200), picture(320, 240, 120)]
    results = real_model.detect(images)
    assert len(results) == 2
    for found in results:
        for item in found:
            box = item.box
            assert 0 <= box.x <= 1 and 0 <= box.y <= 1 and box.x + box.w <= 1 + 1e-6 and box.y + box.h <= 1 + 1e-6
            assert item.category in detector.CATEGORY_PROMPTS and 0 <= item.confidence <= 1


def test_real_model_gives_the_same_boxes_in_a_batch_and_alone(real_model: detector.GroundingDinoDetector) -> None:
    first, second = picture(320, 240, 200), picture(320, 240, 90)
    together = real_model.detect([first, second])
    alone = real_model.detect([first])
    assert [(d.category, round(d.confidence, 2)) for d in together[0]] == [
        (d.category, round(d.confidence, 2)) for d in alone[0]
    ]
