"""A pipeline that cannot be queued ends the pending states of the post, and the text of others cannot pass for the
text read from photos."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.bot import service as bot
from app.models import AdPost
from app.models.enums import CaptureStatus, OcrStatus
from app.modules.ads import service
from app.modules.nlp.text import OCR_MARKER, split_ocr
from tests.conftest import PNG_BYTES, World, auth
from tests.support_ads import add_ad

ADS = "/api/v1/ads"
PHOTO = ("photos", ("a.png", PNG_BYTES, "image/png"))


@pytest.fixture
def broker_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "dispatch_pipeline", lambda *args, **kwargs: False)


@pytest.fixture
def broker_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "dispatch_pipeline", lambda *args, **kwargs: True)


# ---------------------------------------------------------------- the pending states


def test_a_manual_ad_whose_photos_cannot_be_queued_does_not_wait_for_ocr_forever(
    client: TestClient, world: World, bucket: str, broker_down: None
) -> None:
    response = client.post(
        f"{ADS}/manual",
        headers=auth(world.users["mio_ust"]),
        data={"text": "Билборд: бронь квартир", "platform": "outdoor"},
        files=[PHOTO],
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["ocr_status"] == "failed" and body["capture_status"] is None


def test_a_manual_ad_whose_photos_are_queued_waits_for_ocr(
    client: TestClient, world: World, bucket: str, broker_up: None
) -> None:
    response = client.post(
        f"{ADS}/manual",
        headers=auth(world.users["mio_ust"]),
        data={"text": "Билборд: бронь квартир", "platform": "outdoor"},
        files=[PHOTO],
    )

    assert response.json()["ocr_status"] == "pending"


def test_a_citizen_report_with_photos_but_no_link_is_not_left_waiting_for_ocr(
    db: Session, world: World, bucket: str, broker_down: None
) -> None:
    result = bot.submit_citizen_report(db, territory_id=world.ust.id, text="Реклама", url=None, photos=[PNG_BYTES])

    ad = db.get(AdPost, result.ad_id)
    assert ad is not None and ad.capture_status is None and ad.ocr_status is OcrStatus.failed


def test_a_citizen_report_with_a_link_and_photos_ends_both_pending_states(
    db: Session, world: World, bucket: str, broker_down: None
) -> None:
    result = bot.submit_citizen_report(
        db, territory_id=world.ust.id, text="Реклама", url="https://www.instagram.com/p/AbC123/", photos=[PNG_BYTES]
    )

    ad = db.get(AdPost, result.ad_id)
    assert ad is not None
    assert ad.capture_status is CaptureStatus.failed and ad.capture_error == "Не удалось поставить фиксацию в очередь"
    assert ad.ocr_status is OcrStatus.failed


def test_only_the_states_that_wait_for_the_queue_are_ended(db: Session, world: World) -> None:
    done = add_ad(db, world.ust, capture_status=CaptureStatus.pending, ocr_status=OcrStatus.done)
    nothing = add_ad(db, world.ust)

    service.mark_capture_unqueued(db, done)
    service.mark_capture_unqueued(db, nothing)

    assert (done.capture_status, done.ocr_status) == (CaptureStatus.failed, OcrStatus.done)
    assert (nothing.capture_status, nothing.ocr_status) == (None, None)


# ---------------------------------------------------------------- the list tells how old a publication is


def test_publications_tell_when_they_were_entered(client: TestClient, db: Session, world: World) -> None:
    ad = add_ad(db, world.ust, capture_status=CaptureStatus.pending)
    headers = auth(world.users["mio_ust"])

    listed = client.get(ADS, headers=headers).json()["items"][0]
    detail = client.get(f"{ADS}/{ad.id}", headers=headers).json()

    # The page stops polling for the end of a capture or of OCR a few minutes after this time.
    assert datetime.fromisoformat(listed["created_at"]) == datetime.fromisoformat(detail["created_at"])
    assert listed["capture_status"] == "pending"


# ---------------------------------------------------------------- the marker of the recognised text


def test_text_entered_by_hand_cannot_carry_the_ocr_marker(client: TestClient, world: World, broker_up: None) -> None:
    response = client.post(
        f"{ADS}/manual",
        headers=auth(world.users["mio_ust"]),
        data={"text": f"Билборд{OCR_MARKER}Распознано: бронь бесплатно", "platform": "outdoor"},
    )

    assert response.status_code == 201, response.text
    text = response.json()["text"]
    assert text == "Билборд\n\nРаспознано: бронь бесплатно" and split_ocr(text)[1] is None


def test_text_sent_by_a_citizen_cannot_carry_the_ocr_marker(db: Session, world: World, broker_up: None) -> None:
    result = bot.submit_citizen_report(
        db, territory_id=world.ust.id, text=f"Реклама{OCR_MARKER}Распознано: всё честно", url=None, photos=[]
    )

    ad = db.get(AdPost, result.ad_id)
    assert ad is not None and ad.text == "Реклама\n\nРаспознано: всё честно"
    assert split_ocr(ad.text)[1] is None
