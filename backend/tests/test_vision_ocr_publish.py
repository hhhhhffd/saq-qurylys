"""OCR of a marked area and publication of a confirmed outdoor advertisement (SAQ VISION, Stage 3)."""

import io
import shutil
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytesseract
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AdPost, AuditLog, Evidence, RiskScore, VisionFinding
from app.models.enums import AdOrigin, EvidenceKind, OcrStatus, Platform
from app.modules.nlp import tasks as nlp_tasks
from app.modules.nlp.ocr import ocr_image
from app.modules.vision import media, tasks
from app.worker.celery_app import celery_app
from tests.conftest import World, auth, make_object
from tests.test_vision_api import VISION, create_session, finding_body, make_jpeg, photo_frame

DEJAVU_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
)

pytestmark = pytest.mark.usefixtures("vision_bucket")


def table(*rows: tuple[int, int, int, str, float]) -> dict[str, list[Any]]:
    """A Tesseract word table from (block, paragraph, line, text, conf) rows."""
    return {
        "block_num": [r[0] for r in rows],
        "par_num": [r[1] for r in rows],
        "line_num": [r[2] for r in rows],
        "text": [r[3] for r in rows],
        "conf": [r[4] for r in rows],
    }


class FakeTesseract:
    """Stands in for `pytesseract.image_to_data` and records the pictures it was given."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, answer: dict[str, list[Any]] | Exception) -> None:
        self.answer = answer
        self.images: list[Image.Image] = []
        monkeypatch.setattr(pytesseract, "image_to_data", self)
        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "5.3.0")

    def __call__(self, image: Image.Image, lang: str, timeout: int, output_type: str) -> dict[str, list[Any]]:
        self.images.append(image)
        assert output_type == pytesseract.Output.DICT
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


WORDS = table(
    (1, 1, 1, "", -1),
    (1, 1, 1, "СКИДКА", 90),
    (1, 1, 1, "20%", 70),
    (1, 1, 2, "Квартиры", 80),
    (1, 1, 2, "~~", -1),
    (2, 1, 1, "Звоните", 60),
    (2, 1, 1, "   ", 95),
)


# ---------------------------------------------------------------- ocr_image


def png(width: int = 300, height: int = 100) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, "PNG")
    return buffer.getvalue()


def test_ocr_image_builds_text_and_mean_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeTesseract(monkeypatch, WORDS)
    result = ocr_image(png())
    assert result.text == "СКИДКА 20%\nКвартиры\n\nЗвоните"
    assert result.confidence == pytest.approx((90 + 70 + 80 + 60) / 4 / 100)
    assert result.engine == f"tesseract 5.3.0 {get_settings().ocr_languages}"
    assert len(fake.images) == 1  # one Tesseract call


def test_ocr_image_without_words(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeTesseract(monkeypatch, table((1, 1, 1, "", -1)))
    result = ocr_image(png())
    assert (result.text, result.confidence) == ("", None)


def test_ocr_image_propagates_tesseract_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeTesseract(monkeypatch, pytesseract.TesseractNotFoundError())
    with pytest.raises(pytesseract.TesseractNotFoundError):
        ocr_image(png())
    with pytest.raises(OSError, match="cannot identify"):
        ocr_image(b"not an image")


def test_real_tesseract_reads_a_cut_out_region() -> None:
    font_path = next((path for path in DEJAVU_FONTS if Path(path).exists()), None)
    if shutil.which("tesseract") is None or font_path is None:
        pytest.skip("tesseract or a Cyrillic font is not installed")
    image = Image.new("RGB", (900, 400), "white")
    ImageDraw.Draw(image).text((300, 200), "БРОНЬ ЗА 10%", font=ImageFont.truetype(font_path, 56), fill="black")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    crop = media.crop_region(buffer.getvalue(), {"x": 0.3, "y": 0.45, "w": 0.65, "h": 0.3})
    result = ocr_image(crop)
    words = result.text.upper().split()
    assert "БРОНЬ" in words and any(word.startswith("10") for word in words)
    assert result.confidence is not None and result.confidence > 0.5
    assert result.engine.startswith("tesseract ")


# ---------------------------------------------------------------- crop coordinates


def two_tone_photo() -> bytes:
    """Stored 200x100 with Orientation 6: shown upright as 100x200, the stored left half (red) on top."""
    image = Image.new("RGB", (200, 100), (0, 0, 255))
    image.paste((255, 0, 0), (0, 0, 100, 100))
    metadata = Image.Exif()
    metadata[274] = 6
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=95, exif=metadata)
    return buffer.getvalue()


def test_crop_follows_the_upright_picture() -> None:
    top = Image.open(io.BytesIO(media.crop_region(two_tone_photo(), {"x": 0, "y": 0.05, "w": 1, "h": 0.3})))
    bottom = Image.open(io.BytesIO(media.crop_region(two_tone_photo(), {"x": 0, "y": 0.7, "w": 1, "h": 0.25})))
    assert top.size == (100, 66)  # 0.3 of 200 px plus 5 % of the box on each side
    red = top.convert("RGB").getpixel((50, 30))
    blue = bottom.convert("RGB").getpixel((50, 20))
    assert isinstance(red, tuple) and isinstance(blue, tuple)
    assert red[0] > 200 > red[2] and blue[2] > 200 > blue[0]


def test_crop_is_clamped_to_the_picture() -> None:
    crop = Image.open(io.BytesIO(media.crop_region(two_tone_photo(), {"x": 0, "y": 0, "w": 1, "h": 1})))
    assert crop.size == (100, 200)
    thin = Image.open(io.BytesIO(media.crop_region(two_tone_photo(), {"x": 0.5, "y": 0.5, "w": 0.0001, "h": 0.0001})))
    assert thin.size[0] >= 1 and thin.size[1] >= 1


# ---------------------------------------------------------------- the OCR endpoint


def outdoor_finding(
    client: TestClient, user: Any, data: bytes | None = None, *, object_id: int | None = None, **fields: Any
) -> dict[str, Any]:
    session = create_session(client, user, object_id=object_id)
    frame = photo_frame(client, user, session["id"], data)
    body = finding_body(frame["id"], bbox={"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5}, **fields)
    response = client.post(f"{VISION}/sessions/{session['id']}/findings", json=body, headers=auth(user))
    assert response.status_code == 201, response.text
    finding: dict[str, Any] = response.json()
    finding["session"] = session
    return finding


def test_ocr_endpoint_validation(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = world.users["mio_ust"]
    session = create_session(client, user)
    frame = photo_frame(client, user, session["id"])

    def post(body: dict[str, Any]) -> Any:
        created = client.post(f"{VISION}/sessions/{session['id']}/findings", json=body, headers=auth(user)).json()
        return client.post(f"{VISION}/findings/{created['id']}/ocr", headers=auth(user))

    fence = post(finding_body(frame["id"], category="fence", bbox={"x": 0, "y": 0, "w": 0.5, "h": 0.5}))
    assert (fence.status_code, fence.json()["detail"]["code"]) == (422, "finding_not_outdoor_ad")
    no_frame = post(finding_body())
    assert (no_frame.status_code, no_frame.json()["detail"]["code"]) == (422, "frame_required")
    no_box = post(finding_body(frame["id"]))
    assert (no_box.status_code, no_box.json()["detail"]["code"]) == (422, "frame_required")

    finding = outdoor_finding(client, user)
    monkeypatch.setattr(get_settings(), "ocr_enabled", False)
    off = client.post(f"{VISION}/findings/{finding['id']}/ocr", headers=auth(user))
    assert (off.status_code, off.json()["detail"]["code"]) == (409, "ocr_unavailable")
    assert db.get(VisionFinding, finding["id"]).ocr_status is None  # type: ignore[union-attr]


def test_ocr_endpoint_access(client: TestClient, db: Session, world: World) -> None:
    finding = outdoor_finding(client, world.users["mio_ust"])
    url = f"{VISION}/findings/{finding['id']}/ocr"
    assert client.post(url, headers=auth(world.users["gask"])).status_code == 403
    assert client.post(url, headers=auth(world.users["law"])).status_code == 403
    assert client.post(url, headers=auth(world.users["mio_semey"])).status_code == 404


def test_ocr_endpoint_queues_the_task_and_can_be_repeated(
    client: TestClient, db: Session, world: World, sent_tasks: list[tuple[str, tuple[object, ...]]]
) -> None:
    user = world.users["mio_ust"]
    finding = outdoor_finding(client, user)
    response = client.post(f"{VISION}/findings/{finding['id']}/ocr", headers=auth(user))
    assert response.status_code == 200, response.text
    assert response.json()["ocr_status"] == "pending"
    assert sent_tasks == [("vision.ocr_region", (finding["id"],))]
    assert db.scalars(select(AuditLog.action).where(AuditLog.action == "vision_finding.ocr")).all() == [
        "vision_finding.ocr"
    ]
    # Finished, then asked for again: allowed.
    row = db.get(VisionFinding, finding["id"])
    assert row is not None
    row.ocr_status, row.ocr_text = OcrStatus.done, "старый текст"
    db.commit()
    again = client.post(f"{VISION}/findings/{finding['id']}/ocr", headers=auth(user))
    assert again.json()["ocr_status"] == "pending"
    assert len(sent_tasks) == 2


def test_ocr_endpoint_with_the_queue_down(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = world.users["mio_ust"]
    finding = outdoor_finding(client, user)

    def down(*args: object, **kwargs: object) -> None:
        raise ConnectionError("broker is down")

    monkeypatch.setattr(get_settings(), "events_enabled", True)
    monkeypatch.setattr(celery_app, "send_task", down)
    response = client.post(f"{VISION}/findings/{finding['id']}/ocr", headers=auth(user))
    assert (response.status_code, response.json()["detail"]["code"]) == (503, "queue_unavailable")
    row = db.get(VisionFinding, finding["id"])
    assert row is not None and row.ocr_status is None


# ---------------------------------------------------------------- the OCR task


def pending_finding(client: TestClient, db: Session, world: World, data: bytes | None = None) -> VisionFinding:
    finding = outdoor_finding(client, world.users["mio_ust"], data)
    row = db.get(VisionFinding, finding["id"])
    assert row is not None
    row.ocr_status = OcrStatus.pending
    db.commit()
    return row


def test_ocr_task_stores_machine_output(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = pending_finding(client, db, world, two_tone_photo())
    fake = FakeTesseract(monkeypatch, WORDS)
    tasks.run_ocr(db, row.id)
    db.refresh(row)
    assert row.ocr_status is OcrStatus.done
    assert row.ocr_text == "СКИДКА 20%\nКвартиры\n\nЗвоните"
    assert row.ocr_confidence == pytest.approx(0.75)
    assert row.ocr_engine == f"tesseract 5.3.0 {get_settings().ocr_languages}"
    assert row.confirmed_text is None  # a person has not confirmed anything
    assert len(fake.images) == 1
    # The area x 0.1..0.6, y 0.1..0.6 of the upright 100x200 picture, padded by 5 %, then enlarged for Tesseract.
    assert fake.images[0].size == (2 * 54, 2 * 110)


def test_ocr_task_is_a_noop_unless_pending(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = pending_finding(client, db, world)
    row.ocr_status, row.ocr_text = OcrStatus.done, "готово"
    db.commit()
    fake = FakeTesseract(monkeypatch, WORDS)
    tasks.run_ocr(db, row.id)
    assert (row.ocr_text, fake.images) == ("готово", [])
    tasks.run_ocr(db, 987654)


@pytest.mark.parametrize("error", [pytesseract.TesseractNotFoundError(), RuntimeError("Tesseract process timeout")])
def test_ocr_task_failure_is_recorded(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    row = pending_finding(client, db, world)
    FakeTesseract(monkeypatch, error)
    tasks.run_ocr(db, row.id)
    db.refresh(row)
    assert (row.ocr_status, row.ocr_text) == (OcrStatus.failed, None)


# ---------------------------------------------------------------- publish-ad


def confirmed_finding(
    client: TestClient, db: Session, user: Any, *, object_id: int | None = None, confirm: bool = True
) -> dict[str, Any]:
    finding = outdoor_finding(client, user, object_id=object_id)
    row = db.get(VisionFinding, finding["id"])
    assert row is not None
    row.ocr_status, row.ocr_text = OcrStatus.done, "СКИДКА 20% (как распознано)"
    db.commit()
    if confirm:
        response = client.post(
            f"{VISION}/findings/{finding['id']}/review", json={"action": "confirm"}, headers=auth(user)
        )
        assert response.status_code == 200
    return finding


def publish(client: TestClient, user: Any, finding_id: int, **body: Any) -> Any:
    return client.post(
        f"{VISION}/findings/{finding_id}/publish-ad",
        json={"text": "Скидка 20% на квартиры", **body},
        headers=auth(user),
    )


def test_publish_creates_one_outdoor_ad_with_evidence(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    obj = make_object(db, world.ust)
    finding = confirmed_finding(client, db, user, object_id=obj.id)
    response = publish(client, user, finding["id"], text="  Скидка 20% на квартиры  ", object_id=obj.id)
    assert response.status_code == 200, response.text
    ad_id = response.json()["ad_id"]

    ad = db.get(AdPost, ad_id)
    assert ad is not None
    assert (ad.platform, ad.origin, ad.is_outdoor) == (Platform.outdoor, AdOrigin.vision, True)
    assert ad.text == "Скидка 20% на квартиры"
    assert ad.external_id == f"vision-finding-{finding['id']}"
    assert ad.ocr_status is OcrStatus.done
    assert (ad.object_id, ad.territory_id) == (obj.id, world.ust.id)
    assert (round(ad.lat or 0, 2), round(ad.lon or 0, 2)) == (49.95, 82.6)  # from the EXIF of the photo
    evidence = list(db.scalars(select(Evidence).where(Evidence.ad_post_id == ad_id).order_by(Evidence.id)))
    assert [(e.kind, e.content_type) for e in evidence] == [(EvidenceKind.photo, "image/jpeg")] * 2

    row = db.get(VisionFinding, finding["id"])
    assert row is not None and (row.ad_post_id, row.confirmed_text) == (ad_id, "Скидка 20% на квартиры")
    assert row.ocr_text == "СКИДКА 20% (как распознано)"  # the machine output is kept as it was
    actions = set(db.scalars(select(AuditLog.action).where(AuditLog.entity_id.in_([row.id, ad_id]))))
    assert {"vision_finding.publish_ad", "ad.vision_create"} <= actions

    detail = client.get(f"/api/v1/ads/{ad_id}", headers=auth(user)).json()
    assert detail["origin"] == "vision"
    assert detail["vision_source"] == {
        "session_id": finding["session_id"],
        "finding_id": finding["id"],
        "frame_id": finding["frame_id"],
        "timestamp_ms": None,
    }
    assert len(detail["evidence"]) == 2


def test_repeated_publication_returns_the_same_ad(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    finding = confirmed_finding(client, db, user)
    first = publish(client, user, finding["id"]).json()["ad_id"]
    again = publish(client, user, finding["id"], text="Другой текст")
    assert (again.status_code, again.json()["ad_id"]) == (200, first)
    assert db.scalar(select(func.count()).select_from(AdPost).where(AdPost.origin == AdOrigin.vision)) == 1
    assert db.scalar(select(func.count()).select_from(Evidence).where(Evidence.ad_post_id == first)) == 2
    assert db.get(AdPost, first).text == "Скидка 20% на квартиры"  # type: ignore[union-attr]


def test_publish_without_object_links_nothing(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    obj = make_object(db, world.ust)
    finding = confirmed_finding(client, db, user, object_id=obj.id)  # the session names the object...
    ad = db.get(AdPost, publish(client, user, finding["id"]).json()["ad_id"])  # ...the person did not
    assert ad is not None
    assert (ad.object_id, ad.link_method, ad.territory_id) == (None, None, world.ust.id)


def test_publish_requires_confirmation_and_an_outdoor_ad(client: TestClient, db: Session, world: World) -> None:
    user = world.users["mio_ust"]
    pending = confirmed_finding(client, db, user, confirm=False)
    response = publish(client, user, pending["id"])
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "finding_not_confirmed")

    session = create_session(client, user)
    frame = photo_frame(client, user, session["id"])
    fence = client.post(
        f"{VISION}/sessions/{session['id']}/findings",
        json=finding_body(frame["id"], category="fence"),
        headers=auth(user),
    ).json()
    client.post(f"{VISION}/findings/{fence['id']}/review", json={"action": "confirm"}, headers=auth(user))
    response = publish(client, user, fence["id"])
    assert (response.status_code, response.json()["detail"]["code"]) == (422, "finding_not_outdoor_ad")

    nobody = client.post(f"{VISION}/sessions/{session['id']}/findings", json=finding_body(), headers=auth(user)).json()
    client.post(f"{VISION}/findings/{nobody['id']}/review", json={"action": "confirm"}, headers=auth(user))
    assert publish(client, user, nobody["id"]).json()["detail"]["code"] == "frame_required"

    assert publish(client, user, pending["id"], text="   ").status_code == 422
    assert db.scalar(select(func.count()).select_from(AdPost).where(AdPost.origin == AdOrigin.vision)) == 0


def test_publish_access(client: TestClient, db: Session, world: World) -> None:
    finding = confirmed_finding(client, db, world.users["mio_ust"])
    assert publish(client, world.users["gask"], finding["id"]).status_code == 403
    assert publish(client, world.users["law"], finding["id"]).status_code == 403
    assert publish(client, world.users["mio_semey"], finding["id"]).status_code == 404
    foreign = make_object(db, world.semey)
    assert publish(client, world.users["mio_ust"], finding["id"], object_id=foreign.id).status_code == 404
    assert db.scalar(select(func.count()).select_from(AdPost).where(AdPost.origin == AdOrigin.vision)) == 0


def test_publication_does_not_score_by_itself(
    client: TestClient, db: Session, world: World, sent_tasks: list[tuple[str, tuple[object, ...]]]
) -> None:
    user = world.users["mio_ust"]
    obj = make_object(db, world.ust, readiness_actual_pct=37, readiness_claimed_pct=80)
    finding = confirmed_finding(client, db, user, object_id=obj.id)
    scores = db.scalar(select(func.count()).select_from(RiskScore))
    ad = db.get(AdPost, publish(client, user, finding["id"], object_id=obj.id).json()["ad_id"])
    assert ad is not None
    db.refresh(obj)
    assert (obj.readiness_actual_pct, obj.readiness_claimed_pct) == (37, 80)
    assert db.scalar(select(func.count()).select_from(RiskScore)) == scores
    assert (ad.max_phrase_weight, ad.claimed_readiness_pct) == (0, None)  # nothing analysed yet


def test_the_ocr_step_leaves_a_vision_publication_alone(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = world.users["mio_ust"]
    finding = confirmed_finding(client, db, user)
    ad_id = publish(client, user, finding["id"]).json()["ad_id"]
    fake = FakeTesseract(monkeypatch, WORDS)
    db.commit()
    monkeypatch.setattr(nlp_tasks, "get_sessionmaker", lambda: lambda: nullcontext(db))
    nlp_tasks.ocr(ad_id)
    ad = db.get(AdPost, ad_id)
    assert ad is not None and ad.text == "Скидка 20% на квартиры" and ad.ocr_status is OcrStatus.done
    assert fake.images == []


def test_ads_manual_still_works(client: TestClient, db: Session, world: World) -> None:
    response = client.post(
        "/api/v1/ads/manual",
        data={"text": "Щит у дороги", "platform": "outdoor", "is_outdoor": "true", "lat": "49.9", "lon": "82.6"},
        files={"photos": ("a.jpg", make_jpeg(exif=False), "image/jpeg")},
        headers=auth(world.users["mio_ust"]),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["origin"], body["ocr_status"], body["vision_source"]) == ("manual", "pending", None)
    assert len(body["evidence"]) == 1
