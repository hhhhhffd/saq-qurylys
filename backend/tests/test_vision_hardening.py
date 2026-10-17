"""Review follow-ups of the SAQ VISION API: statuses of decisions, upload handling and session reopening."""

import asyncio
import io
from collections.abc import MutableMapping
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditLog, VisionAsset, VisionFinding
from app.models.enums import VisionFindingStatus, VisionReviewState
from app.modules.vision import service
from app.modules.vision.limits import UploadSizeLimitMiddleware
from tests.conftest import World, auth
from tests.test_vision_api import MP4_BYTES, VISION, create_session, finding_body, make_jpeg, photo_frame, upload

pytestmark = pytest.mark.usefixtures("vision_bucket")


def new_finding(client: TestClient, user: Any, **fields: Any) -> dict[str, Any]:
    session = create_session(client, user)
    frame = photo_frame(client, user, session["id"])
    response = client.post(
        f"{VISION}/sessions/{session['id']}/findings", json=finding_body(frame["id"], **fields), headers=auth(user)
    )
    result: dict[str, Any] = response.json()
    return result


def review(client: TestClient, user: Any, finding_id: int, **body: Any) -> Any:
    return client.post(f"{VISION}/findings/{finding_id}/review", json=body, headers=auth(user))


# ---------------------------------------------------------------- review status


def test_review_can_set_the_status_and_records_it(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    finding = new_finding(client, user)
    response = review(client, user, finding["id"], action="confirm", status="possible_noncompliance")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["review_state"]) == ("possible_noncompliance", "confirmed")
    assert body["reviews"][0]["status"] == "possible_noncompliance"
    # A decision without a status leaves it as it was and records none.
    later = review(client, user, finding["id"], action="comment", comment="проверил").json()
    assert later["status"] == "possible_noncompliance"
    assert later["reviews"][1]["status"] is None


def test_not_applicable_cannot_be_set_through_another_action(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    finding = new_finding(client, user)
    response = review(client, user, finding["id"], action="confirm", status="not_applicable")
    assert (response.status_code, response.json()["detail"]["code"]) == (422, "status_not_allowed")


def test_confirming_a_not_applicable_finding_needs_a_new_status(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    finding = new_finding(client, user)
    review(client, user, finding["id"], action="not_applicable", comment="не требуется")
    refused = review(client, user, finding["id"], action="confirm")
    assert (refused.status_code, refused.json()["detail"]["code"]) == (409, "finding_not_applicable")
    ok = review(client, user, finding["id"], action="confirm", status="insufficient_evidence")
    assert (ok.json()["status"], ok.json()["review_state"]) == ("insufficient_evidence", "confirmed")


def test_publish_refuses_a_not_applicable_finding(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    finding = new_finding(client, user)
    row = db.get(VisionFinding, finding["id"])
    assert row is not None
    row.review_state, row.status = VisionReviewState.confirmed, VisionFindingStatus.not_applicable
    db.commit()
    response = client.post(f"{VISION}/findings/{finding['id']}/publish-ad", json={"text": "x"}, headers=auth(user))
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "finding_not_applicable")


# ---------------------------------------------------------------- upload handling


def test_oversized_content_length_is_refused_before_the_body_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "vision_max_video_mb", 10)
    monkeypatch.setattr(get_settings(), "vision_max_photo_mb", 10)
    sent: list[MutableMapping[str, Any]] = []
    reached: list[bool] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        reached.append(True)

    async def receive() -> dict[str, Any]:
        raise AssertionError("the body must not be read")

    async def send(message: MutableMapping[str, Any]) -> None:
        sent.append(message)

    def scope(length: int, path: str = "/api/v1/vision/sessions/5/assets") -> dict[str, Any]:
        return {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [(b"content-length", str(length).encode())],
        }

    middleware = UploadSizeLimitMiddleware(app)
    asyncio.run(middleware(scope(12 * 1024 * 1024), receive, send))
    assert reached == [] and sent[0]["status"] == 413
    assert b"file_too_large" in sent[1]["body"]

    asyncio.run(middleware(scope(10 * 1024 * 1024 + 1000), receive, send))  # within the slack for form framing
    asyncio.run(middleware(scope(10**12, "/api/v1/vision/sessions/5"), receive, send))  # another endpoint
    assert reached == [True, True]


def test_oversized_upload_is_refused_by_the_application(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "vision_max_video_mb", 1)
    monkeypatch.setattr(get_settings(), "vision_max_photo_mb", 1)
    user = world.users["mio_ust"]
    session = create_session(client, user)
    response = upload(client, user, session["id"], MP4_BYTES + b"\x00" * (3 * 1024 * 1024))
    assert (response.status_code, response.json()["detail"]["code"]) == (413, "file_too_large")


@pytest.mark.parametrize("brand", [b"heic", b"heix", b"mif1", b"avif", b"M4A "])
def test_non_video_ftyp_brands_are_refused(client: TestClient, world: World, brand: bytes) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    data = b"\x00\x00\x00\x18ftyp" + brand + b"\x00" * 300
    response = upload(client, user, session["id"], data)
    assert (response.status_code, response.json()["detail"]["code"]) == (415, "unsupported_media_type")


@pytest.mark.parametrize("brand", [b"isom", b"mp42", b"avc1", b"M4V ", b"qt  ", b"3gp4", b"dash"])
def test_video_ftyp_brands_are_accepted(client: TestClient, world: World, brand: bytes) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    response = upload(client, user, session["id"], b"\x00\x00\x00\x18ftyp" + brand + b"\x00" * 300)
    assert response.status_code == 201


def test_a_concurrent_duplicate_returns_the_existing_asset(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    data = make_jpeg()
    first = upload(client, user, session["id"], data)
    assert first.status_code == 201

    real = service._existing_asset
    calls: list[int] = []

    def blind_once(db: Session, session_id: int, sha256: str) -> VisionAsset | None:
        calls.append(1)
        return None if len(calls) == 1 else real(db, session_id, sha256)

    # The other request had not committed yet when this one looked: the unique index decides.
    monkeypatch.setattr(service, "_existing_asset", blind_once)
    second = upload(client, user, session["id"], data)
    assert (second.status_code, second.json()["id"]) == (200, first.json()["id"])
    assert len(db.scalars(select(VisionAsset)).all()) == 1


def test_large_jpeg_reports_upright_dimensions(client: TestClient, world: World) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    asset = upload(client, user, session["id"], make_jpeg(4000, 3000)).json()
    assert (asset["width"], asset["height"]) == (3000, 4000)  # Orientation 6 swaps the sides
    frames = client.get(f"{VISION}/sessions/{session['id']}/frames", headers=auth(user)).json()["items"]
    preview = client.get(f"{VISION}/frames/{frames[0]['id']}/content", headers=auth(user)).content
    assert Image.open(io.BytesIO(preview)).size == (480, 640)


def test_exif_time_without_offset_is_local_time(client: TestClient, world: World) -> None:
    image = Image.new("RGB", (40, 40))
    metadata = Image.Exif()
    metadata[0x8769] = {36867: "2026:10:01 12:30:00"}
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=metadata)
    user = world.users["mio_ust"]
    session = create_session(client, user)
    asset = upload(client, user, session["id"], buffer.getvalue()).json()
    assert asset["taken_at"].startswith("2026-10-01T07:30:00")  # Asia/Almaty is UTC+5


# ---------------------------------------------------------------- a reviewed session


def test_new_material_reopens_a_reviewed_session(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)

    def state() -> dict[str, Any]:
        detail: dict[str, Any] = client.get(f"{VISION}/sessions/{session['id']}", headers=auth(user)).json()
        return detail

    frame = photo_frame(client, user, session["id"])
    client.post(f"{VISION}/sessions/{session['id']}/reviewed", headers=auth(user))
    assert state()["status"] == "reviewed"

    # A repeated upload adds nothing and leaves the review in place.
    assert upload(client, user, session["id"], make_jpeg()).status_code == 200
    assert state()["status"] == "reviewed"

    assert upload(client, user, session["id"], make_jpeg(color=(1, 2, 3))).status_code == 201
    reopened = state()
    assert (reopened["status"], reopened["reviewed_at"], reopened["reviewed_by_name"]) == ("open", None, None)

    client.post(f"{VISION}/sessions/{session['id']}/reviewed", headers=auth(user))
    created = client.post(
        f"{VISION}/sessions/{session['id']}/findings", json=finding_body(frame["id"]), headers=auth(user)
    )
    assert created.status_code == 201
    assert state()["status"] == "open"
    actions = db.scalars(select(AuditLog.action).where(AuditLog.action == "vision_session.reopen")).all()
    assert len(actions) == 2
