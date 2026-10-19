"""PDF of the signal card: content, evidence images, disclaimer on every page, HTTP response."""

import re
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from minio.error import S3Error
from sqlalchemy.orm import Session

from app import storage
from app.models import Developer, Evidence
from app.models.enums import (
    CheckSource,
    CheckStatus,
    DetectedBy,
    DocType,
    EvidenceKind,
    PhraseCategory,
    Recipient,
    ScoreTrigger,
    SignalOrigin,
)
from app.modules.risk import service as risk
from app.modules.signals import labels, pdf, service
from app.scope import build_scope
from app.storage import EvidenceLink
from tests.conftest import World, auth, make_object
from tests.support_risk import NOW, add_ad, add_document, png_bytes

DISCLAIMER = "Красная зона означает высокий риск и необходимость проверки, а не установленную виновность."
BOOKING = ((PhraseCategory.booking, DetectedBy.dictionary, None),)


def page_texts(document: Any) -> list[str]:
    """Text of every page of a rendered document, margin boxes (header, footer, page numbers) included."""
    pages = []
    for page in document.pages:
        parts = [box.text for box in page._page_box.descendants() if getattr(box, "text", None)]
        pages.append(re.sub(r"\s+", " ", " ".join(parts)))
    return pages


def build_card(
    db: Session, world: World, ads: int = 2, *, demo: bool = False
) -> tuple[service.CardView, dict[str, list[int]]]:
    """A card of scenario B (absence of the legal basis established, a deposit in the advertising)."""
    developer = Developer(bin="123456789012", name="ТОО Застройщик", director="Иванов И.И.", founders=["Петров"])
    db.add(developer)
    db.flush()
    obj = make_object(db, world.ust, "ЖК Алтын", developer_id=developer.id, address="ул. Абая, 1", is_demo=demo)
    add_document(db, obj, DocType.guarantee, CheckStatus.not_found)
    permit = add_document(db, obj, DocType.dsu_permit, CheckStatus.not_found)
    permit.number, permit.check_source = "ДСУ-1", CheckSource.housing_portal
    scan = storage.put_evidence(
        db,
        png_bytes(color="#aa5522"),
        EvidenceKind.document_scan,
        "image/png",
        link=EvidenceLink(document_id=permit.id),
    )
    screenshots = []
    for index in range(ads):
        hits = BOOKING + (((PhraseCategory.installment, DetectedBy.llm, None),) if index == 0 else ())
        ad = add_ad(db, obj, NOW - timedelta(hours=index), hits=hits, payment_schemes=("booking",), is_demo=demo)
        shot = storage.put_evidence(
            db,
            png_bytes(640, 900, "#2255aa"),
            EvidenceKind.screenshot_png,
            "image/png",
            source_url=ad.url,
            link=EvidenceLink(ad_post_id=ad.id),
        )
        screenshots.append(shot.id)
    risk.recalculate(db, obj.id, ScoreTrigger.event, NOW)
    mio = world.users["mio_ust"]
    card = service.create_card(db, obj, SignalOrigin.manual, mio, now=NOW)
    card.sections = {**card.sections, "note": "<b>Осторожно</b> & проверить"}
    db.flush()
    view = service.get_card_view(db, mio, build_scope(db, mio), card.id)
    return view, {"scan": [scan.id], "screenshots": screenshots}


def test_every_page_carries_the_disclaimer_in_header_and_footer(db: Session, world: World, bucket: str) -> None:
    view, _ = build_card(db, world, ads=6)
    document = pdf.render_document(pdf.render_html(pdf.build_context(db, view)))

    texts = page_texts(document)

    assert len(texts) > 1, "six screenshots do not fit on one page"
    for index, text in enumerate(texts, start=1):
        assert text.count(DISCLAIMER) == 2, f"page {index}: header and footer"
        assert f"Стр. {index} из {len(texts)}" in text
        assert view.card.number in text  # the running header


def test_the_disclaimer_text_is_the_agreed_one() -> None:
    assert labels.RED_ZONE_DISCLAIMER == DISCLAIMER
    assert labels.get_labels("ru")["disclaimer"] == DISCLAIMER
    assert labels.get_labels("kk")["disclaimer"] == DISCLAIMER  # until Kazakh is filled in, Russian is used


def test_the_card_content_reaches_the_pdf(db: Session, world: World, bucket: str) -> None:
    view, evidence = build_card(db, world)
    context = pdf.build_context(db, view)
    html = pdf.render_html(context)
    text = " ".join(page_texts(pdf.render_document(html)))

    for expected in (
        "Сигнальная карточка " + view.card.number,
        "ЖК Алтын",
        "ТОО Застройщик",
        "123456789012",
        "Иванов И.И.",
        "ул. Абая, 1",
        "Красная",  # zone label
        "R1 — Установлено отсутствие правового основания",
        "R2 — Предложение внести деньги в рекламе",
        "R3 — Активная реклама объекта",
        "Отсутствие установлено: гарантия КЖК и разрешение МИО проверены и не найдены",
        "Нужна проверка",
        "Есть неподтверждённые находки ИИ",
        "Формулировка в публикации",
        "«бронь»",
        "Факт",
        "Гипотеза ИИ (не подтверждена человеком)",
        "Разрешение на привлечение денег дольщиков (ДСУ)",
        "Не найден",
        "Жилищный портал",
        "Instagram",
        "Бронирование",
        "Требует подтверждения",
    ):
        assert expected in text, expected
    assert html.count("data:image/png;base64,") == 3  # the scan and two screenshots
    for evidence_id in evidence["scan"] + evidence["screenshots"]:
        assert f"Файл № {evidence_id}" in text
    assert "&lt;b&gt;Осторожно&lt;/b&gt; &amp; проверить" in html  # stored text is escaped, not interpreted
    assert "<b>Осторожно</b>" not in html


def test_evidence_lists_capture_time_and_sha256(db: Session, world: World, bucket: str) -> None:
    view, evidence = build_card(db, world, ads=1)
    row = db.get(Evidence, evidence["screenshots"][0])
    assert row is not None
    html = pdf.render_html(pdf.build_context(db, view))
    assert row.sha256 in html
    assert row.captured_at.astimezone(ZoneInfo(view.timezone)).strftime("%d.%m.%Y %H:%M") in html


def test_missing_stored_file_does_not_break_the_pdf(
    db: Session, world: World, bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    view, _ = build_card(db, world, ads=1)

    def gone(evidence: object) -> None:
        raise S3Error(None, "NoSuchKey", "missing", "r", "id", "host")  # type: ignore[arg-type]

    monkeypatch.setattr(storage, "open_evidence", gone)
    context = pdf.build_context(db, view)
    assert pdf.render_pdf(db, view).startswith(b"%PDF-")
    assert "data:image" not in pdf.render_html(context)
    assert "файл недоступен в хранилище" in pdf.render_html(context)


def test_files_that_are_not_images_are_listed_not_embedded(db: Session, world: World, bucket: str) -> None:
    view, _ = build_card(db, world, ads=0)
    checks = view.card.sections["permit_checks"]
    document = next(item for item in checks if item["evidence_ids"])  # the permit with a scan
    extra = storage.put_evidence(
        db,
        b"%PDF-1.4 scan",
        EvidenceKind.pdf,
        "application/pdf",
        link=EvidenceLink(document_id=db.get(Evidence, document["evidence_ids"][0]).document_id),  # type: ignore[union-attr]
    )
    view.card.sections = {
        **view.card.sections,
        "permit_checks": [
            {**item, "evidence_ids": [*item["evidence_ids"], extra.id]} if item is document else item for item in checks
        ],
    }
    html = pdf.render_html(pdf.build_context(db, view))
    assert html.count("data:image/png") == 1
    assert "PDF-документ" in html
    assert "вложение не является изображением" in html


def test_response_of_the_receiving_body_is_printed(db: Session, world: World, bucket: str) -> None:
    view, _ = build_card(db, world, ads=0)
    mio, gask = world.users["mio_ust"], world.users["gask"]
    service.confirm_and_send(db, view, mio, Recipient.gask, None, NOW)
    service.respond(db, view, gask, "Проверка проведена, нарушений нет", None, NOW)
    text = " ".join(page_texts(pdf.render_document(pdf.render_html(pdf.build_context(db, view)))))
    assert "Результат рассмотрения" in text
    assert "Проверка проведена, нарушений нет" in text
    assert "ГАСК" in text


# ---------------------------------------------------------------- HTTP


def test_pdf_endpoint(client: TestClient, db: Session, world: World, bucket: str) -> None:
    view, _ = build_card(db, world, ads=1)
    response = client.get(f"/api/v1/signals/{view.card.id}/pdf", headers=auth(world.users["mio_ust"]))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == f'inline; filename="{view.card.number}.pdf"'
    assert response.headers["cache-control"] == "no-store"
    assert response.content.startswith(b"%PDF-")
    assert response.content.rstrip().endswith(b"%%EOF")
    assert len(response.content) > 10_000


def test_pdf_access_follows_the_card_rules(client: TestClient, db: Session, world: World, bucket: str) -> None:
    view, _ = build_card(db, world, ads=1)
    url = f"/api/v1/signals/{view.card.id}/pdf"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth(world.users["gask"])).status_code == 404  # not sent yet
    assert client.get(url, headers=auth(world.users["mio_semey"])).status_code == 404
    assert client.get(url, headers=auth(world.users["admin"])).status_code == 200

    client.post(
        f"/api/v1/signals/{view.card.id}/confirm-and-send",
        headers=auth(world.users["mio_ust"]),
        json={"recipient": "gask"},
    )
    assert client.get(url, headers=auth(world.users["gask"])).status_code == 200
    assert client.get(url, headers=auth(world.users["law"])).status_code == 404


# ---------------------------------------------------------------- demo marker


def test_demo_object_card_carries_no_demo_marker(db: Session, world: World, bucket: str) -> None:
    view, _ = build_card(db, world, ads=6, demo=True)
    html = pdf.render_html(pdf.build_context(db, view))

    texts = page_texts(pdf.render_document(html))

    assert len(texts) > 1
    for index, text in enumerate(texts, start=1):
        assert "ДЕМО" not in text, f"page {index}"
        assert text.count(DISCLAIMER) == 2
    assert "демонстрац" not in " ".join(texts)
    assert "demo-" not in html


def test_card_without_flags_says_that_no_check_is_needed(db: Session, world: World, bucket: str) -> None:
    obj = make_object(db, world.ust, "ЖК Чистый")
    add_document(db, obj, DocType.guarantee, CheckStatus.confirmed)
    risk.recalculate(db, obj.id, ScoreTrigger.event, NOW)
    mio = world.users["mio_ust"]
    card = service.create_card(db, obj, SignalOrigin.manual, mio, now=NOW)
    view = service.get_card_view(db, mio, build_scope(db, mio), card.id)
    text = " ".join(page_texts(pdf.render_document(pdf.render_html(pdf.build_context(db, view)))))
    assert "Дополнительных проверок не требуется" in text
    assert "Подтверждено (гарантия КЖК или разрешение МИО)" in text
    assert "Сработавших факторов нет" in text


def test_a_card_made_before_the_case_model_still_renders(db: Session, world: World, bucket: str) -> None:
    view, _ = build_card(db, world, ads=1)
    legacy = {
        key: value
        for key, value in view.card.sections.items()
        if key not in ("needs_check", "legal_basis_status", "is_demo")
    }
    legacy["risk_factors"] = [{"code": "no_permit", "weight": 40, "detail": {"count": 0}}]
    legacy["publications"] = [
        {k: v for k, v in item.items() if k not in ("hits", "is_demo")} for item in legacy["publications"]
    ]
    view.card.sections = legacy
    text = " ".join(page_texts(pdf.render_document(pdf.render_html(pdf.build_context(db, view)))))
    assert "no_permit" in text  # an unknown code is printed as it is
    assert view.card.number in text
