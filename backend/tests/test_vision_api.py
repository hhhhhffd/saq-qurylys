import io
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditLog, Inspection, VisionAsset, VisionFinding, VisionFrame, VisionJob, VisionReview
from app.models.enums import VisionAssetStatus, VisionJobStatus
from app.worker.celery_app import celery_app
from tests.conftest import World, auth, make_object

VISION = "/api/v1/vision"
BACKEND_DIR = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.usefixtures("vision_bucket")


def make_jpeg(
    width: int = 200, height: int = 100, *, exif: bool = True, color: tuple[int, int, int] = (200, 30, 30)
) -> bytes:
    """A real JPEG; with `exif` it is shot at 49°57'N 82°36'E at a known time and stored rotated (Orientation 6)."""
    image = Image.new("RGB", (width, height), color)
    metadata = Image.Exif()
    if exif:
        metadata[274] = 6
        metadata[0x8769] = {36867: "2026:10:01 12:30:00", 36880: "+06:00"}
        metadata[0x8825] = {1: "N", 2: (49.0, 57.0, 0.0), 3: "E", 4: (82.0, 36.0, 0.0)}
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=metadata)
    return buffer.getvalue()


MP4_BYTES = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x01" * 256
WEBM_BYTES = b"\x1a\x45\xdf\xa3\x93\x42\x82\x84webm" + b"\x01" * 256
MKV_BYTES = b"\x1a\x45\xdf\xa3\x93\x42\x82\x88matroska" + b"\x01" * 256


def create_session(client: TestClient, user: Any, **body: Any) -> dict[str, Any]:
    response = client.post(f"{VISION}/sessions", json={"source": "drone", **body}, headers=auth(user))
    assert response.status_code == 201, response.text
    session: dict[str, Any] = response.json()
    return session


def upload(client: TestClient, user: Any, session_id: int, data: bytes, name: str = "shot.jpg") -> Any:
    return client.post(
        f"{VISION}/sessions/{session_id}/assets",
        files={"file": (name, data, "application/octet-stream")},
        headers=auth(user),
    )


def photo_frame(client: TestClient, user: Any, session_id: int, data: bytes | None = None) -> dict[str, Any]:
    assert upload(client, user, session_id, data or make_jpeg()).status_code == 201
    frames = client.get(f"{VISION}/sessions/{session_id}/frames", headers=auth(user)).json()["items"]
    last: dict[str, Any] = frames[-1]
    return last


def finding_body(frame_id: int | None = None, **fields: Any) -> dict[str, Any]:
    return {"frame_id": frame_id, "category": "outdoor_ad", "status": "observed", **fields}


# ---------------------------------------------------------------- access


@pytest.mark.parametrize("role", ["gask", "law"])
def test_receiving_bodies_cannot_use_vision(client: TestClient, db: Session, world: World, role: str) -> None:
    session = create_session(client, world.users["mio_ust"])
    headers = auth(world.users[role])
    assert client.get(f"{VISION}/config", headers=headers).status_code == 403
    assert client.get(f"{VISION}/sessions", headers=headers).status_code == 403
    assert client.get(f"{VISION}/sessions/{session['id']}", headers=headers).status_code == 403
    assert client.post(f"{VISION}/sessions", json={"source": "drone"}, headers=headers).status_code == 403
    assert upload(client, world.users[role], session["id"], make_jpeg()).status_code == 403


def test_anonymous_requests_are_rejected(client: TestClient) -> None:
    assert client.get(f"{VISION}/config").status_code == 401
    assert client.get(f"{VISION}/sessions").status_code == 401
    assert client.post(f"{VISION}/sessions", json={"source": "drone"}).status_code == 401
    assert client.get(f"{VISION}/assets/1/content").status_code == 401


def test_other_territory_is_not_found_everywhere(client: TestClient, db: Session, world: World) -> None:
    owner, stranger = world.users["mio_ust"], world.users["mio_semey"]
    session = create_session(client, owner)
    frame = photo_frame(client, owner, session["id"])
    finding = client.post(
        f"{VISION}/sessions/{session['id']}/findings", json=finding_body(frame["id"]), headers=auth(owner)
    ).json()
    asset_id = (
        session["id"]
        and client.get(f"{VISION}/sessions/{session['id']}", headers=auth(owner)).json()["assets"][0]["id"]
    )
    headers = auth(stranger)

    assert client.get(f"{VISION}/sessions", headers=headers).json() == {"items": [], "total": 0}
    for method, path, body in [
        ("get", f"/sessions/{session['id']}", None),
        ("patch", f"/sessions/{session['id']}", {"note": "x"}),
        ("post", f"/sessions/{session['id']}/reviewed", None),
        ("get", f"/sessions/{session['id']}/frames", None),
        ("post", f"/sessions/{session['id']}/findings", finding_body()),
        ("get", f"/assets/{asset_id}/content", None),
        ("get", f"/frames/{frame['id']}/content", None),
        ("get", f"/frames/{frame['id']}/content?variant=original", None),
        ("get", f"/findings/{finding['id']}", None),
        ("post", f"/findings/{finding['id']}/review", {"action": "confirm"}),
    ]:
        response = client.request(method, VISION + path, json=body, headers=headers)
        assert response.status_code == 404, (method, path)
    assert upload(client, stranger, session["id"], make_jpeg()).status_code == 404

    # A region-level officer sees the sessions of the cities below.
    assert client.get(f"{VISION}/sessions/{session['id']}", headers=auth(world.users["mio_region"])).status_code == 200


def test_config(client: TestClient, world: World) -> None:
    body = client.get(f"{VISION}/config", headers=auth(world.users["mio_ust"])).json()
    assert body == {
        "enabled": True,
        "detector_mode": "disabled",
        "detector_model": None,
        "ocr_enabled": get_settings().ocr_enabled,
        "max_photo_mb": 25,
        "max_video_mb": 1024,
        "max_duration_seconds": 1800,
    }


def test_vision_routes_do_not_exist_while_the_module_is_off() -> None:
    code = (
        "from app.main import app\n"
        "paths = app.openapi()['paths']\n"
        "print(sum('/vision' in path for path in paths))\n"
        "print('/api/v1/health' in paths)"
    )
    env = {**os.environ, "VISION_ENABLED": "false"}
    out = subprocess.run(  # noqa: S603  (fixed arguments)
        [sys.executable, "-c", code], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, check=True
    )
    assert out.stdout.split() == ["0", "True"]


# ---------------------------------------------------------------- sessions


def test_session_territory_comes_from_the_object_or_the_user(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    with_object = create_session(client, world.users["mio_region"], object_id=obj.id, note="  облёт  ")
    assert with_object["territory_id"] == world.ust.id
    assert with_object["object"] == {"id": obj.id, "code": obj.code, "name": obj.name}
    assert with_object["note"] == "облёт"
    assert with_object["status"] == "open"
    assert with_object["created_by_name"] == "t_mio_region"
    assert (with_object["assets_count"], with_object["frames_count"], with_object["findings_count"]) == (0, 0, 0)
    assert (with_object["processing"], with_object["failed"]) == (False, False)

    own = create_session(client, world.users["mio_semey"])
    assert own["territory_id"] == world.semey.id
    assert own["object"] is None

    named = create_session(client, world.users["admin"], territory_id=world.ust.id)
    assert named["territory_id"] == world.ust.id

    audit_actions = set(db.scalars(select(AuditLog.action).where(AuditLog.entity_type == "vision_session")))
    assert audit_actions == {"vision_session.create"}


def test_session_territory_is_required_and_checked(client: TestClient, db: Session, world: World) -> None:
    admin = world.users["admin"]
    response = client.post(f"{VISION}/sessions", json={"source": "drone"}, headers=auth(admin))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "territory_required"

    obj = make_object(db, world.ust)
    mismatch = client.post(
        f"{VISION}/sessions",
        json={"source": "drone", "object_id": obj.id, "territory_id": world.semey.id},
        headers=auth(admin),
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["detail"]["code"] == "territory_mismatch"

    other_city = client.post(
        f"{VISION}/sessions",
        json={"source": "drone", "territory_id": world.semey.id},
        headers=auth(world.users["mio_ust"]),
    )
    assert other_city.status_code == 404
    foreign_object = client.post(
        f"{VISION}/sessions", json={"source": "drone", "object_id": obj.id}, headers=auth(world.users["mio_semey"])
    )
    assert foreign_object.status_code == 404
    assert client.post(f"{VISION}/sessions", json={"source": "satellite"}, headers=auth(admin)).status_code == 422


def test_list_filters_and_counts(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    obj = make_object(db, world.ust)
    first = create_session(client, user, object_id=obj.id, source="drone")
    second = create_session(client, user, source="camera")
    photo_frame(client, user, first["id"])
    assert upload(client, user, first["id"], MP4_BYTES, "flight.mp4").status_code == 201

    page = client.get(f"{VISION}/sessions", headers=auth(user)).json()
    assert [item["id"] for item in page["items"]] == [second["id"], first["id"]]
    assert page["total"] == 2
    row = page["items"][1]
    assert (row["assets_count"], row["frames_count"], row["processing"], row["failed"]) == (2, 1, True, False)

    def ids(query: str) -> list[int]:
        return [item["id"] for item in client.get(f"{VISION}/sessions?{query}", headers=auth(user)).json()["items"]]

    assert ids(f"object_id={obj.id}") == [first["id"]]
    assert ids("source=camera") == [second["id"]]
    assert ids("status=reviewed") == []
    assert ids("limit=1&offset=1") == [first["id"]]
    assert client.get(f"{VISION}/sessions?limit=1", headers=auth(user)).json()["total"] == 2


def test_patch_links_and_unlinks_the_object_by_hand(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_region"]
    session = create_session(client, user, territory_id=world.region.id)
    obj = make_object(db, world.ust)

    linked = client.patch(
        f"{VISION}/sessions/{session['id']}",
        json={"object_id": obj.id, "note": "после дождя", "source": "phone"},
        headers=auth(user),
    ).json()
    assert linked["object"]["id"] == obj.id
    assert linked["territory_id"] == world.ust.id
    assert (linked["note"], linked["source"]) == ("после дождя", "phone")

    untouched = client.patch(f"{VISION}/sessions/{session['id']}", json={"note": "ещё"}, headers=auth(user)).json()
    assert untouched["object"]["id"] == obj.id

    detached = client.patch(f"{VISION}/sessions/{session['id']}", json={"object_id": None}, headers=auth(user)).json()
    assert detached["object"] is None
    assert (
        client.patch(f"{VISION}/sessions/{session['id']}", json={"source": None}, headers=auth(user)).status_code == 422
    )
    assert (
        client.patch(f"{VISION}/sessions/{session['id']}", json={"object_id": 999999}, headers=auth(user)).status_code
        == 404
    )
    actions = list(db.scalars(select(AuditLog.action).where(AuditLog.action == "vision_session.update")))
    assert len(actions) == 3


def test_session_becomes_reviewed_only_by_an_explicit_request(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    frame = photo_frame(client, user, session["id"])
    finding = client.post(
        f"{VISION}/sessions/{session['id']}/findings", json=finding_body(frame["id"]), headers=auth(user)
    ).json()
    assert (
        client.post(
            f"{VISION}/findings/{finding['id']}/review", json={"action": "confirm"}, headers=auth(user)
        ).status_code
        == 200
    )
    assert client.get(f"{VISION}/sessions/{session['id']}", headers=auth(user)).json()["status"] == "open"

    done = client.post(f"{VISION}/sessions/{session['id']}/reviewed", headers=auth(user)).json()
    assert done["status"] == "reviewed"
    assert done["reviewed_by_name"] == "t_mio_ust"
    assert done["reviewed_at"] is not None
    # Repeating the request changes nothing and writes no second audit entry.
    assert (
        client.post(f"{VISION}/sessions/{session['id']}/reviewed", headers=auth(user)).json()["reviewed_at"]
        == done["reviewed_at"]
    )
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "vision_session.review")) == 1


# ---------------------------------------------------------------- upload


def test_photo_upload_makes_a_frame_with_preview_and_exif(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    data = make_jpeg(400, 200)
    response = upload(client, user, session["id"], data, "C:\\fakepath\\DJI_0001.JPG")
    assert response.status_code == 201, response.text
    asset = response.json()
    assert asset["kind"] == "photo"
    assert asset["status"] == "ready"
    assert asset["progress"] == 100
    assert asset["frames_count"] == 1
    assert asset["original_name"] == "DJI_0001.JPG"
    assert asset["content_type"] == "image/jpeg"
    assert asset["size_bytes"] == len(data)
    import hashlib

    assert asset["sha256"] == hashlib.sha256(data).hexdigest()
    # Orientation 6 turns a 400x200 picture upright: 200x400.
    assert (asset["width"], asset["height"]) == (200, 400)
    assert asset["taken_at"].startswith("2026-10-01T06:30:00")
    assert asset["lat"] == pytest.approx(49.95)
    assert asset["lon"] == pytest.approx(82.6)

    frames = client.get(f"{VISION}/sessions/{session['id']}/frames", headers=auth(user)).json()
    assert frames["total"] == 1
    frame = frames["items"][0]
    assert (frame["asset_id"], frame["timestamp_ms"], frame["width"], frame["height"]) == (asset["id"], None, 200, 400)

    original = client.get(f"{VISION}/frames/{frame['id']}/content?variant=original", headers=auth(user))
    assert original.status_code == 200
    assert original.content == data
    assert original.headers["content-type"] == "image/jpeg"
    preview = client.get(f"{VISION}/frames/{frame['id']}/content", headers=auth(user))
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(preview.content)) as image:
        assert max(image.size) <= 640
    assert client.get(f"{VISION}/assets/{asset['id']}/content", headers=auth(user)).content == data
    assert client.get(f"{VISION}/frames/{frame['id']}/content?variant=thumb", headers=auth(user)).status_code == 422

    detail = client.get(f"{VISION}/sessions/{session['id']}", headers=auth(user)).json()
    assert detail["assets"][0]["id"] == asset["id"]
    assert (detail["assets_count"], detail["frames_count"], detail["processing"]) == (1, 1, False)
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "vision_asset.upload")).one()
    assert entry.entity_id == asset["id"]


def test_large_photo_is_scaled_down_for_the_preview_only(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    frame = photo_frame(client, user, session["id"], make_jpeg(2000, 1000, exif=False))
    assert (frame["width"], frame["height"]) == (2000, 1000)
    preview = client.get(f"{VISION}/frames/{frame['id']}/content", headers=auth(user)).content
    with Image.open(io.BytesIO(preview)) as image:
        assert image.size == (640, 320)


def test_png_without_exif_is_accepted(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    buffer = io.BytesIO()
    Image.new("RGBA", (30, 20), (1, 2, 3, 128)).save(buffer, "PNG")
    response = upload(client, user, session["id"], buffer.getvalue(), "plan.png")
    assert response.status_code == 201
    asset = response.json()
    assert (asset["content_type"], asset["width"], asset["height"]) == ("image/png", 30, 20)
    assert (asset["taken_at"], asset["lat"], asset["lon"]) == (None, None, None)


def test_the_same_file_in_the_same_session_returns_the_existing_asset(
    client: TestClient, db: Session, world: World
) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    other = create_session(client, user)
    data = make_jpeg()
    first = upload(client, user, session["id"], data)
    again = upload(client, user, session["id"], data, "renamed.jpg")
    elsewhere = upload(client, user, other["id"], data)
    assert (first.status_code, again.status_code, elsewhere.status_code) == (201, 200, 201)
    assert again.json()["id"] == first.json()["id"]
    assert elsewhere.json()["id"] != first.json()["id"]
    assert db.scalar(select(func.count()).select_from(VisionAsset).where(VisionAsset.session_id == session["id"])) == 1
    assert db.scalar(select(func.count()).select_from(VisionFrame)) == 2
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "vision_asset.upload")) == 2


def test_upload_is_validated_by_content_not_by_name_or_declared_type(
    client: TestClient, db: Session, world: World
) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)

    not_media = upload(client, user, session["id"], b"%PDF-1.4\n" + b"0" * 64, "scan.jpg")
    assert not_media.status_code == 415
    assert not_media.json()["detail"]["code"] == "unsupported_media_type"
    assert upload(client, user, session["id"], b"plain text, not a picture", "a.mp4").status_code == 415
    empty = upload(client, user, session["id"], b"", "empty.jpg")
    assert (empty.status_code, empty.json()["detail"]["code"]) == (422, "empty_file")

    # JPEG signature, but nothing decodes: refused, and nothing is stored.
    broken = upload(client, user, session["id"], b"\xff\xd8\xff\xe0" + b"junk" * 50, "broken.jpg")
    assert (broken.status_code, broken.json()["detail"]["code"]) == (422, "image_undecodable")
    assert db.scalar(select(func.count()).select_from(VisionAsset)) == 0
    assert db.scalar(select(func.count()).select_from(VisionFrame)) == 0


def test_size_limits_are_enforced_per_kind(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    monkeypatch.setattr(get_settings(), "vision_max_photo_mb", 1)
    big_photo = make_jpeg(300, 300, exif=False)
    big_photo += b"\x00" * (1024 * 1024)  # trailing bytes keep the JPEG valid and push it over the limit
    too_big = upload(client, user, session["id"], big_photo)
    assert (too_big.status_code, too_big.json()["detail"]["code"]) == (413, "file_too_large")

    # A video larger than the photo limit is fine while it fits the video limit...
    video = MP4_BYTES + b"\x00" * (1024 * 1024)
    assert upload(client, user, session["id"], video, "long.mp4").status_code == 201
    monkeypatch.setattr(get_settings(), "vision_max_video_mb", 1)
    # ...and not beyond it.
    assert upload(client, user, session["id"], video + b"\x02", "longer.mp4").status_code == 413
    assert db.scalar(select(func.count()).select_from(VisionAsset)) == 1


@pytest.mark.parametrize("data", [MP4_BYTES, WEBM_BYTES, MKV_BYTES, b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 64])
def test_video_is_stored_queued_and_the_extraction_task_is_sent(
    client: TestClient, db: Session, world: World, sent_tasks: list[tuple[str, tuple[object, ...]]], data: bytes
) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    response = upload(client, user, session["id"], data, "flight.bin")
    assert response.status_code == 201, response.text
    asset = response.json()
    assert asset["kind"] == "video"
    assert asset["status"] == "queued"
    assert asset["progress"] == 0
    assert asset["frames_count"] == 0
    assert (asset["width"], asset["duration_ms"]) == (None, None)

    job = db.scalars(select(VisionJob).where(VisionJob.asset_id == asset["id"])).one()
    assert (job.kind.value, job.status, job.attempts) == ("extract_frames", VisionJobStatus.queued, 0)
    assert job.idempotency_key == f"extract:{asset['id']}:1"
    assert sent_tasks == [("vision.extract_frames", (job.id,))]
    assert client.get(f"{VISION}/assets/{asset['id']}/content", headers=auth(user)).content == data

    detail = client.get(f"{VISION}/sessions/{session['id']}", headers=auth(user)).json()
    assert (detail["processing"], detail["failed"]) == (True, False)

    # The same video again: no second job, no second task.
    assert upload(client, user, session["id"], data).status_code == 200
    assert len(sent_tasks) == 1


def test_video_task_goes_to_the_vision_queue() -> None:
    options = celery_app.amqp.router.route({}, "vision.extract_frames")
    assert options["queue"].name == "vision"


def test_unreachable_broker_fails_the_video_and_records_the_error(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise ConnectionError("broker is down")

    monkeypatch.setattr(get_settings(), "events_enabled", True)
    monkeypatch.setattr(celery_app, "send_task", broken)
    user = world.users["mio_ust"]
    session = create_session(client, user)
    response = upload(client, user, session["id"], MP4_BYTES)
    assert response.status_code == 201
    assert (response.json()["status"], response.json()["error_code"]) == ("failed", "queue_unavailable")
    job = db.scalars(select(VisionJob)).one()
    assert job.status is VisionJobStatus.failed
    assert job.error_code == "queue_unavailable"
    asset = db.scalars(select(VisionAsset)).one()
    assert asset.status is VisionAssetStatus.failed


# ---------------------------------------------------------------- findings


def test_manual_finding_with_frame_and_bbox(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    frame = photo_frame(client, user, session["id"])
    response = client.post(
        f"{VISION}/sessions/{session['id']}/findings",
        json=finding_body(frame["id"], bbox={"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.8}, note=" баннер на заборе "),
        headers=auth(user),
    )
    assert response.status_code == 201, response.text
    finding = response.json()
    assert finding["origin"] == "manual"
    assert finding["review_state"] == "pending"
    assert finding["status"] == "observed"
    assert finding["bbox"] == {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.8}
    assert finding["note"] == "баннер на заборе"
    assert finding["created_by_name"] == "t_mio_ust"
    assert (finding["confidence"], finding["model_version"], finding["ocr_status"], finding["ad_post_id"]) == (
        None,
    ) * 4
    assert finding["reviews"] == []
    assert client.get(f"{VISION}/findings/{finding['id']}", headers=auth(user)).json() == finding
    assert client.get(f"{VISION}/sessions/{session['id']}", headers=auth(user)).json()["findings"] == [finding]

    # A finding may also concern the whole session (no frame).
    assert (
        client.post(
            f"{VISION}/sessions/{session['id']}/findings",
            json=finding_body(category="fence", status="insufficient_evidence"),
            headers=auth(user),
        ).status_code
        == 201
    )
    entries = list(db.scalars(select(AuditLog.action).where(AuditLog.entity_type == "vision_finding")))
    assert entries == ["vision_finding.create"] * 2


@pytest.mark.parametrize(
    "bbox",
    [
        {"x": 0.5, "y": 0, "w": 0.6, "h": 0.5},
        {"x": 0, "y": 0.9, "w": 0.5, "h": 0.2},
        {"x": 0, "y": 0, "w": 0, "h": 0.5},
        {"x": 0, "y": 0, "w": 0.5, "h": -0.1},
        {"x": -0.1, "y": 0, "w": 0.5, "h": 0.5},
        {"x": 0, "y": 0, "w": 1.5, "h": 0.5},
        {"x": 0, "y": 0, "w": 0.5},
    ],
)
def test_bbox_must_lie_inside_the_frame(client: TestClient, db: Session, world: World, bbox: dict[str, float]) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    frame = photo_frame(client, user, session["id"])
    response = client.post(
        f"{VISION}/sessions/{session['id']}/findings", json=finding_body(frame["id"], bbox=bbox), headers=auth(user)
    )
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(VisionFinding)) == 0


def test_finding_validation(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    other = create_session(client, user)
    frame = photo_frame(client, user, session["id"])
    foreign_frame = photo_frame(client, user, other["id"], make_jpeg(exif=False, color=(0, 0, 255)))
    url = f"{VISION}/sessions/{session['id']}/findings"
    whole = {"x": 0, "y": 0, "w": 1, "h": 1}

    assert client.post(url, json=finding_body(frame["id"], bbox=whole), headers=auth(user)).status_code == 201
    # The status is the person's judgement and is not defaulted.
    assert client.post(url, json={"frame_id": frame["id"], "category": "fence"}, headers=auth(user)).status_code == 422
    assert client.post(url, json={"frame_id": frame["id"], "status": "observed"}, headers=auth(user)).status_code == 422
    assert (
        client.post(url, json=finding_body(frame["id"], status="violation_confirmed"), headers=auth(user)).status_code
        == 422
    )
    assert client.post(url, json=finding_body(bbox=whole), headers=auth(user)).status_code == 422  # bbox without frame
    wrong = client.post(url, json=finding_body(foreign_frame["id"]), headers=auth(user))
    assert (wrong.status_code, wrong.json()["detail"]["code"]) == (422, "frame_not_in_session")
    assert client.post(url, json=finding_body(999999), headers=auth(user)).status_code == 422
    assert db.scalar(select(func.count()).select_from(VisionFinding)) == 1


# ---------------------------------------------------------------- review


def test_review_keeps_an_append_only_history(client: TestClient, db: Session, world: World) -> None:
    author, colleague = world.users["mio_ust"], world.users["mio_region"]
    session = create_session(client, author)
    finding = client.post(
        f"{VISION}/sessions/{session['id']}/findings",
        json=finding_body(category="wheel_wash", status="possible_noncompliance"),
        headers=auth(author),
    ).json()
    url = f"{VISION}/findings/{finding['id']}/review"

    first = client.post(
        url, json={"action": "needs_more_evidence", "comment": "нужен снимок въезда"}, headers=auth(author)
    )
    assert first.status_code == 200
    assert first.json()["review_state"] == "needs_more_evidence"
    commented = client.post(
        url, json={"action": "comment", "comment": "запросил съёмку"}, headers=auth(colleague)
    ).json()
    assert commented["review_state"] == "needs_more_evidence"  # a comment is not a decision
    confirmed = client.post(url, json={"action": "confirm"}, headers=auth(colleague)).json()
    assert confirmed["review_state"] == "confirmed"
    assert confirmed["status"] == "possible_noncompliance"
    rejected = client.post(url, json={"action": "reject", "comment": "ошибся"}, headers=auth(author)).json()
    assert rejected["review_state"] == "rejected"

    history = client.get(f"{VISION}/findings/{finding['id']}", headers=auth(author)).json()["reviews"]
    assert [(item["action"], item["comment"], item["reviewer_name"]) for item in history] == [
        ("needs_more_evidence", "нужен снимок въезда", "t_mio_ust"),
        ("comment", "запросил съёмку", "t_mio_region"),
        ("confirm", None, "t_mio_region"),
        ("reject", "ошибся", "t_mio_ust"),
    ]
    assert db.scalar(select(func.count()).select_from(VisionReview)) == 4
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "vision_finding.review")) == 4


def test_not_applicable_needs_a_reason_and_changes_the_status(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    finding = client.post(
        f"{VISION}/sessions/{session['id']}/findings", json=finding_body(category="fence"), headers=auth(user)
    ).json()
    url = f"{VISION}/findings/{finding['id']}/review"

    missing = client.post(url, json={"action": "not_applicable"}, headers=auth(user))
    assert (missing.status_code, missing.json()["detail"]["code"]) == (422, "comment_required")
    assert client.post(url, json={"action": "not_applicable", "comment": "   "}, headers=auth(user)).status_code == 422
    assert client.post(url, json={"action": "comment"}, headers=auth(user)).status_code == 422
    assert client.post(url, json={"action": "approve"}, headers=auth(user)).status_code == 422
    assert db.scalar(select(func.count()).select_from(VisionReview)) == 0

    done = client.post(
        url, json={"action": "not_applicable", "comment": "стройка без забора по проекту"}, headers=auth(user)
    ).json()
    assert done["status"] == "not_applicable"
    assert done["review_state"] == "rejected"
    assert len(done["reviews"]) == 1


# ---------------------------------------------------------------- isolation from the rest of SAQ


def test_vision_never_touches_readiness_or_the_risk_engine(
    client: TestClient,
    db: Session,
    world: World,
    sent_tasks: list[tuple[str, tuple[object, ...]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    changed: list[object] = []
    monkeypatch.setattr("app.events.objects_changed", changed.append)
    user = world.users["mio_ust"]
    obj = make_object(db, world.ust, readiness_actual_pct=37, readiness_claimed_pct=80)
    session = create_session(client, user, object_id=obj.id)
    frame = photo_frame(client, user, session["id"])
    assert upload(client, user, session["id"], MP4_BYTES).status_code == 201
    finding = client.post(
        f"{VISION}/sessions/{session['id']}/findings", json=finding_body(frame["id"]), headers=auth(user)
    ).json()
    client.post(f"{VISION}/findings/{finding['id']}/review", json={"action": "confirm"}, headers=auth(user))
    client.post(f"{VISION}/sessions/{session['id']}/reviewed", headers=auth(user))
    client.patch(f"{VISION}/sessions/{session['id']}", json={"object_id": None}, headers=auth(user))

    db.refresh(obj)
    assert (obj.readiness_actual_pct, obj.readiness_claimed_pct) == (37, 80)
    assert changed == []
    assert [name for name, _ in sent_tasks] == ["vision.extract_frames"]
    assert db.scalar(select(func.count()).select_from(Inspection)) == 0
