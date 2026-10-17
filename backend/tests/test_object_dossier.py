"""Object case file PDF: sections, passport, risk, inventory of attachments, disclaimer, HTTP access."""

import re
from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.models import AuditLog, ConstructionObject, Developer, Inspection
from app.models.enums import AdStatus, CheckStatus, DocType, EvidenceKind, ScoreTrigger
from app.modules.objects import dossier
from app.modules.risk import service as risk
from app.modules.signals.pdf import _env, render_document
from app.storage import EvidenceLink
from tests.conftest import World, auth, make_object
from tests.support_risk import NOW, add_ad, add_document, png_bytes

DISCLAIMER = "Красная зона означает высокий риск и необходимость проверки, а не установленную виновность."


def page_texts(document: Any) -> list[str]:
    pages = []
    for page in document.pages:
        parts = [box.text for box in page._page_box.descendants() if getattr(box, "text", None)]
        pages.append(re.sub(r"\s+", " ", " ".join(parts)))
    return pages


def build_object(db: Session, world: World, bucket: str) -> tuple[ConstructionObject, dict[str, str]]:
    developer = Developer(bin="123456789012", name="ТОО Застройщик", director="Иванов И.И.", founders=["Петров"])
    db.add(developer)
    db.flush()
    obj = make_object(db, world.ust, "ЖК Алтын", developer_id=developer.id, address="ул. Абая, 1")
    permit = add_document(db, obj, DocType.dsu_permit, CheckStatus.not_found)
    permit.number = "ДСУ-1"
    scan = storage.put_evidence(
        db,
        png_bytes(color="#aa5522"),
        EvidenceKind.document_scan,
        "image/png",
        link=EvidenceLink(document_id=permit.id),
    )
    ad = add_ad(db, obj, NOW)
    shot = storage.put_evidence(
        db,
        png_bytes(640, 900, "#2255aa"),
        EvidenceKind.screenshot_png,
        "image/png",
        source_url=ad.url,
        link=EvidenceLink(ad_post_id=ad.id),
    )
    hidden = add_ad(db, obj, NOW - timedelta(hours=1), status=AdStatus.verification)
    hidden.text = "СКРЫТАЯ ПУБЛИКАЦИЯ"
    hidden.url = "https://example.kz/hidden"
    db.add(Inspection(object_id=obj.id, inspected_at=date(2026, 10, 1), readiness_pct=40, note="Осмотр площадки"))
    db.flush()
    risk.recalculate(db, obj.id, ScoreTrigger.event, NOW)
    return obj, {"scan": scan.sha256, "shot": shot.sha256}


def render(db: Session, world: World, obj: ConstructionObject) -> tuple[str, list[str]]:
    context = dossier.build_context(db, obj, world.users["mio_ust"])
    html = _env.get_template("object_dossier.html").render(**context)
    return html, page_texts(render_document(html))


def test_title_page_sections_and_passport(db: Session, world: World, bucket: str) -> None:
    obj, _ = build_object(db, world, bucket)
    _, texts = render(db, world, obj)
    text = " ".join(texts)

    assert "Материалы по объекту" in texts[0]
    assert obj.code in texts[0] and "ЖК Алтын" in texts[0] and "t_mio_ust" in texts[0]
    for heading in (
        "Содержание",
        "1. Паспорт объекта",
        "2. Оценка риска",
        "3. Документы и проверки разрешений",
        "4. Обследования",
        "5. Обращения граждан",
        "6. Публикации",
        "7. Сигнальные карточки",
        "8. Опись приложений",
        "Почему эта зона",
        "Что требует проверки",
        "Осмотр площадки",
    ):
        assert heading in text, heading
    assert "123456789012" in text and "Иванов И.И." in text and "Петров" in text


def test_inventory_lists_sha256_and_embeds_images(db: Session, world: World, bucket: str) -> None:
    obj, hashes = build_object(db, world, bucket)
    html, texts = render(db, world, obj)
    text = " ".join(texts)

    for digest in hashes.values():
        assert digest in html
    assert "Документ: Разрешение на привлечение денег дольщиков (ДСУ) ДСУ-1" in text
    assert "Публикация: Instagram" in text
    assert html.count("data:image/png;base64,") == 2


def test_every_page_has_disclaimer_and_page_numbers(db: Session, world: World, bucket: str) -> None:
    obj, _ = build_object(db, world, bucket)
    _, texts = render(db, world, obj)

    assert len(texts) >= 4
    for index, text in enumerate(texts, start=1):
        assert text.count(DISCLAIMER) == 2
        assert f"Стр. {index} из {len(texts)}" in text


def test_unconfirmed_publications_are_excluded(db: Session, world: World, bucket: str) -> None:
    obj, _ = build_object(db, world, bucket)
    html, _ = render(db, world, obj)
    assert "СКРЫТАЯ ПУБЛИКАЦИЯ" not in html
    assert "https://example.kz/hidden" not in html


def test_publications_are_capped(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "ЖК Много")
    for index in range(dossier.MAX_ADS + 2):
        add_ad(db, obj, NOW - timedelta(minutes=index))
    context = dossier.build_context(db, obj, world.users["mio_ust"])
    assert len(context["ads"]) == dossier.MAX_ADS
    assert context["ads_capped"] == f"Показаны {dossier.MAX_ADS} из {dossier.MAX_ADS + 2} публикаций (самые новые)"


def test_demo_object_keeps_the_watermark(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "ЖК Демо", is_demo=True)
    _, texts = render(db, world, obj)
    assert all("ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ" in text for text in texts)


# ---------------------------------------------------------------- HTTP


def test_dossier_endpoint(client: TestClient, db: Session, world: World, bucket: str) -> None:
    obj, _ = build_object(db, world, bucket)
    response = client.get(f"/api/v1/objects/{obj.id}/dossier.pdf", headers=auth(world.users["mio_ust"]))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == f'inline; filename="{obj.code}-dossier.pdf"'
    assert response.headers["cache-control"] == "no-store"
    assert response.content.startswith(b"%PDF-")
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "object.dossier", AuditLog.entity_id == obj.id)).one()
    assert entry.user_id == world.users["mio_ust"].id


def test_dossier_access(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "ЖК Доступ")
    url = f"/api/v1/objects/{obj.id}/dossier.pdf"

    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth(world.users["mio_semey"])).status_code == 404
    assert client.get(url, headers=auth(world.users["gask"])).status_code == 403
    assert client.get(url, headers=auth(world.users["law"])).status_code == 403
    assert client.get(url, headers=auth(world.users["admin"])).status_code == 200
