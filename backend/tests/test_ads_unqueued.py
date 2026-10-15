"""A pipeline that cannot be queued ends the pending states of the post, and the text of others cannot pass for the
text read from photos."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.bot import service as bot
from app.models import AdPost
from app.modules.ads import service
from app.modules.nlp.text import OCR_MARKER, split_ocr
from tests.conftest import World, auth

ADS = "/api/v1/ads"


@pytest.fixture
def broker_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "dispatch_pipeline", lambda *args, **kwargs: True)


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
