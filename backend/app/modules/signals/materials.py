"""Prepare a scoped, auditable package from a signal card's stored snapshot."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import Any, Literal
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, storage
from app.errors import api_error
from app.models import AdPost, AppUser, ConstructionObject, Document, Evidence, RiskScore, SignalCard, Territory
from app.models.enums import CheckStatus, EvidenceKind, Recipient
from app.modules.evidence.service import can_access_evidence
from app.modules.signals import pdf, service
from app.modules.signals.material_documents import (
    render_cover_docx,
    render_inventory_pdf,
    render_publications_xlsx,
)
from app.modules.signals.schemas import (
    MaterialKind,
    SignalMaterialFile,
    SignalMaterialLimits,
    SignalMaterials,
    SignalMissingMaterial,
)
from app.scope import TerritoryScope
from app.xlsx_exports import content_disposition

logger = logging.getLogger(__name__)

MAX_PACKAGE_EVIDENCE_FILES = 50
MAX_PACKAGE_FILE_BYTES = 20 * 1024 * 1024
MAX_PACKAGE_TOTAL_BYTES = 60 * 1024 * 1024
MAX_DRAFT_PDF_EMBED_BYTES = 20 * 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024
_DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PDF_CONTENT_TYPE = "application/pdf"
_INVALID_FILENAME = re.compile(r"[^A-Za-z0-9_-]")


_TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "archive": "Сохранённая копия направленной карточки",
        "draft_pdf": "Сигнальная карточка · черновик",
        "cover": "Сопроводительный лист",
        "publications": "Публикации из снимка карточки",
        "inventory": "Опись материалов",
        "evidence": "Материал из снимка карточки",
        "storage_missing": "Файл недоступен в хранилище",
        "snapshot_missing": "Файл, указанный в снимке карточки, недоступен или не прошёл проверку связи",
        "archive_missing": "Сохранённая копия направленной карточки отсутствует или недоступна",
        "archive_integrity": "Сохранённую копию карточки не удалось проверить; файл не включён",
        "evidence_integrity": "Файл не прошёл проверку целостности; файл не включён",
        "selection_excluded": "Не включён по выбору сотрудника",
        "snapshot_capped": "В снимке перечислено 50 публикаций; перечень при создании карточки мог быть ограничен.",
        "invalid_selection": "Выбор файлов недействителен или содержит недоступный материал",
        "evidence_limit": "В пакет можно включить не более 50 файлов доказательств",
        "file_limit": "Файл превышает ограничение 20 МиБ",
        "total_limit": "Материалы пакета превышают общий предел 60 МиБ",
        "recipient": "Получатель не указан",
        "whole_territory": "Вся доступная территория",
        "legal_basis_confirmed": "В снимке карточки правовое основание отмечено как подтверждённое.",
        "permit_confirmed": "Проверка документа «{doc}» отмечена в снимке как подтверждённая.",
        "hit_confirmed": (
            "Формулировка «{fragment}» в публикации № {id} отмечена в карточке как подтверждённая человеком."
        ),
        "hit_needs_review": ("Совпадение в публикации № {id} не отмечено в снимке как проверенное человеком."),
        "hit_ai_review": "В публикации № {id} сохранена гипотеза ИИ, не подтверждённая человеком.",
        "needs_check": "В карточке отмечена дополнительная проверка: {name}.",
        "zone_green": "Зелёная",
        "zone_yellow": "Жёлтая",
        "zone_red": "Красная",
        "recipient_mio": "МИО",
        "recipient_gask": "ГАСК",
        "recipient_law": "Правоохранительные органы",
        "platform_instagram": "Instagram",
        "platform_tiktok": "TikTok",
        "platform_telegram": "Telegram",
        "platform_website": "Сайт",
        "platform_aggregator": "Агрегатор",
        "platform_outdoor": "Наружная реклама",
        "platform_other": "Другое",
        "doc_smr_notice": "Уведомление о начале СМР",
        "doc_psd": "Проектно-сметная документация",
        "doc_expertise": "Экспертиза",
        "doc_dsu_permit": "Разрешение на привлечение денег дольщиков",
        "doc_guarantee": "Гарантия",
        "doc_ddu_registration": "Регистрация ДДУ",
        "doc_land_title": "Правоустанавливающий документ на землю",
        "needs_legal_basis_unknown": "Правовое основание не установлено",
        "needs_complaint_unverified": "Коллективное обращение не проверено",
        "needs_readiness_unverified": "Заявленная готовность не подтверждена фотофиксацией",
        "needs_ai_hypotheses_pending": "Есть неподтверждённые находки ИИ",
        "needs_link_unverified": "Связь публикации с объектом не подтверждена",
        "kind_screenshot_png": "Снимок экрана",
        "kind_archive_mhtml": "Архив веб-страницы",
        "kind_photo": "Фотография",
        "kind_document_scan": "Скан документа",
        "kind_pdf": "PDF-документ",
        "kind_registry_response": "Ответ реестра",
    },
    "kk": {
        "archive": "Жіберілген карточканың сақталған көшірмесі",
        "draft_pdf": "Сигналдық карточка · жоба",
        "cover": "Ілеспе парақ",
        "publications": "Карточка көрінісіндегі жарияланымдар",
        "inventory": "Материалдар тізімдемесі",
        "evidence": "Карточка көрінісіндегі материал",
        "storage_missing": "Файл сақтау қоймасында қолжетімсіз",
        "snapshot_missing": "Карточка көрінісінде көрсетілген файл қолжетімсіз немесе байланысы тексерілмеді",
        "archive_missing": "Жіберілген карточканың сақталған көшірмесі жоқ немесе қолжетімсіз",
        "archive_integrity": "Карточканың сақталған көшірмесін тексеру мүмкін болмады; файл қосылмады",
        "evidence_integrity": "Файл тұтастық тексеруінен өтпеді; файл қосылмады",
        "selection_excluded": "Қызметкер таңдауы бойынша қосылмады",
        "snapshot_capped": "Көріністе 50 жарияланым бар; карточка жасалған кезде тізім шектелуі мүмкін.",
        "invalid_selection": "Файлдар таңдауы жарамсыз немесе қолжетімсіз материал бар",
        "evidence_limit": "Пакетке 50 дәлел файлынан артық қосуға болмайды",
        "file_limit": "Файл 20 МиБ шегінен асады",
        "total_limit": "Пакет материалдары 60 МиБ жалпы шегінен асады",
        "recipient": "Алушы көрсетілмеген",
        "whole_territory": "Барлық қолжетімді аумақ",
        "legal_basis_confirmed": "Карточканың сақталған көрінісінде құқықтық негіз расталған деп белгіленген.",
        "permit_confirmed": "«{doc}» құжатын тексеру сақталған көріністе расталған деп белгіленген.",
        "hit_confirmed": "№ {id} жарияланымындағы «{fragment}» тіркесі карточкада адам растаған деп белгіленген.",
        "hit_needs_review": "№ {id} жарияланымындағы сәйкестік адамның тексергені деп белгіленбеген.",
        "hit_ai_review": "№ {id} жарияланымында адам растамаған ЖИ болжамы сақталған.",
        "needs_check": "Карточкада қосымша тексеру белгіленген: {name}.",
        "zone_green": "Жасыл",
        "zone_yellow": "Сары",
        "zone_red": "Қызыл",
        "recipient_mio": "ЖАО",
        "recipient_gask": "МҚБК",
        "recipient_law": "Құқық қорғау органдары",
        "platform_instagram": "Instagram",
        "platform_tiktok": "TikTok",
        "platform_telegram": "Telegram",
        "platform_website": "Сайт",
        "platform_aggregator": "Агрегатор",
        "platform_outdoor": "Сыртқы жарнама",
        "platform_other": "Басқа",
        "doc_smr_notice": "Құрылыс-монтаж жұмыстарының басталғаны туралы хабарлама",
        "doc_psd": "Жобалау-сметалық құжаттама",
        "doc_expertise": "Сараптама қорытындысы",
        "doc_dsu_permit": "Үлескерлердің қаражатын тартуға рұқсат",
        "doc_guarantee": "Кепілдік",
        "doc_ddu_registration": "ҮҚК тіркеуі",
        "doc_land_title": "Жерге құқық белгілейтін құжат",
        "needs_legal_basis_unknown": "Құқықтық негіз анықталмаған",
        "needs_complaint_unverified": "Ұжымдық өтініш тексерілмеген",
        "needs_readiness_unverified": "Мәлімделген дайындық фотофиксациямен расталмаған",
        "needs_ai_hypotheses_pending": "Расталмаған ЖИ нәтижелері бар",
        "needs_link_unverified": "Жарияланымның объектімен байланысы расталмаған",
        "kind_screenshot_png": "Экран суреті",
        "kind_archive_mhtml": "Веб-бет мұрағаты",
        "kind_photo": "Фотосурет",
        "kind_document_scan": "Құжат сканы",
        "kind_pdf": "PDF құжаты",
        "kind_registry_response": "Тізілім жауабы",
    },
}

_SAFE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "application/pdf": ".pdf",
    "multipart/related": ".mhtml",
    "message/rfc822": ".mhtml",
    "application/x-mimearchive": ".mhtml",
}


@dataclass
class _SnapshotReference:
    evidence_id: int
    relation: Literal["publication", "document"]
    ad_post_id: int | None
    document_types: set[str]
    source_label: str
    source_url: str | None
    conflicted: bool = False


@dataclass(frozen=True)
class _CandidateEvidence:
    evidence: Evidence
    source_label: str
    source_url: str | None
    available: bool
    missing_reason: str | None


@dataclass(frozen=True)
class _PackageFile:
    kind: str
    filename: str
    content_type: str
    data: bytes
    source_label: str
    sha256: str
    captured_at: datetime | None = None
    evidence_id: int | None = None
    source_url: str | None = None


@dataclass
class _ReadEvidence:
    data: bytes | None
    reason: str | None = None


def _labels(locale: str) -> dict[str, str]:
    return _TEXT.get(locale, _TEXT["ru"])


def _snapshot_items(sections: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = sections.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _evidence_ids(item: dict[str, Any]) -> list[int]:
    value = item.get("evidence_ids")
    if not isinstance(value, list):
        return []
    return [evidence_id for evidence_id in value if isinstance(evidence_id, int) and evidence_id > 0]


def _valid_http_url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 2048 or any(ord(char) < 32 for char in value):
        return None
    from urllib.parse import urlsplit

    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return None
    except ValueError:
        return None
    return value


def _platform_label(value: object, labels: dict[str, str]) -> str:
    if not isinstance(value, str):
        return labels["platform_other"]
    key = f"platform_{value}"
    return labels.get(key, labels["platform_other"])


def _add_reference(
    refs: dict[int, _SnapshotReference],
    evidence_id: int,
    *,
    relation: Literal["publication", "document"],
    source_label: str,
    source_url: str | None = None,
    ad_post_id: int | None = None,
    document_type: str | None = None,
) -> None:
    existing = refs.get(evidence_id)
    if existing is None:
        existing = _SnapshotReference(
            evidence_id=evidence_id,
            relation=relation,
            ad_post_id=ad_post_id,
            document_types={document_type} if document_type else set(),
            source_label=source_label,
            source_url=source_url,
        )
        refs[evidence_id] = existing
        return
    if existing.relation != relation:
        existing.conflicted = True
        return
    if relation == "publication" and existing.ad_post_id != ad_post_id:
        existing.conflicted = True
        return
    if document_type:
        existing.document_types.add(document_type)


def _snapshot_references(card: SignalCard, locale: str) -> dict[int, _SnapshotReference]:
    labels = _labels(locale)
    sections = card.sections if isinstance(card.sections, dict) else {}
    refs: dict[int, _SnapshotReference] = {}
    for publication in _snapshot_items(sections, "publications"):
        ad_post_id = publication.get("ad_post_id")
        if not isinstance(ad_post_id, int) or ad_post_id < 1:
            continue
        source = f"{publication.get('ad_post_id')} · {_platform_label(publication.get('platform'), labels)}"
        source_url = _valid_http_url(publication.get("url"))
        for evidence_id in _evidence_ids(publication):
            _add_reference(
                refs,
                evidence_id,
                relation="publication",
                ad_post_id=ad_post_id,
                source_label=source,
                source_url=source_url,
            )
    for check in _snapshot_items(sections, "permit_checks"):
        doc_type = check.get("doc_type")
        if not isinstance(doc_type, str):
            continue
        doc_label = labels.get(f"doc_{doc_type}", doc_type)
        source = doc_label
        for evidence_id in _evidence_ids(check):
            _add_reference(
                refs,
                evidence_id,
                relation="document",
                document_type=doc_type,
                source_label=source,
            )
    return refs


def _storage_available(evidence: Evidence) -> bool:
    try:
        storage.get_client().stat_object(evidence.bucket, evidence.s3_key)
        return True
    except Exception:
        logger.warning("Package evidence %s is not available in object storage", evidence.id)
        return False


def _candidate_evidence(
    session: Session,
    user: AppUser,
    scope: TerritoryScope,
    card: SignalCard,
    locale: str,
) -> tuple[list[_CandidateEvidence], list[tuple[str, str]]]:
    refs = _snapshot_references(card, locale)
    usable_refs = {evidence_id: ref for evidence_id, ref in refs.items() if not ref.conflicted}
    publication_refs = {evidence_id: ref for evidence_id, ref in usable_refs.items() if ref.relation == "publication"}
    document_refs = {evidence_id: ref for evidence_id, ref in usable_refs.items() if ref.relation == "document"}
    rows: dict[int, tuple[Evidence, _SnapshotReference]] = {}
    if publication_refs:
        ad_post_ids = {ref.ad_post_id for ref in publication_refs.values() if ref.ad_post_id is not None}
        evidence_rows = session.scalars(
            select(Evidence)
            .join(AdPost, AdPost.id == Evidence.ad_post_id)
            .where(
                Evidence.id.in_(publication_refs),
                Evidence.ad_post_id.in_(ad_post_ids),
                AdPost.object_id == card.object_id,
            )
        )
        for evidence in evidence_rows:
            ref = publication_refs.get(evidence.id)
            if ref is not None and evidence.ad_post_id == ref.ad_post_id:
                rows[evidence.id] = (evidence, ref)
    if document_refs:
        document_rows = session.execute(
            select(Evidence, Document.doc_type)
            .join(Document, Document.id == Evidence.document_id)
            .where(
                Evidence.id.in_(document_refs),
                Document.object_id == card.object_id,
            )
        )
        for evidence, doc_type in document_rows:
            ref = document_refs.get(evidence.id)
            if ref is not None and doc_type.value in ref.document_types:
                rows[evidence.id] = (evidence, ref)

    candidates: list[_CandidateEvidence] = []
    missing: list[tuple[str, str]] = []
    for evidence_id, ref in sorted(refs.items()):
        if ref.conflicted:
            missing.append((ref.source_label, _labels(locale)["snapshot_missing"]))
            continue
        row_and_ref = rows.get(evidence_id)
        if row_and_ref is None:
            missing.append((ref.source_label, _labels(locale)["snapshot_missing"]))
            continue
        evidence, _ = row_and_ref
        if not can_access_evidence(session, user, scope, evidence):
            missing.append((ref.source_label, _labels(locale)["snapshot_missing"]))
            continue
        available = _storage_available(evidence)
        missing_reason = None if available else _labels(locale)["storage_missing"]
        candidates.append(
            _CandidateEvidence(
                evidence=evidence,
                source_label=ref.source_label,
                source_url=_valid_http_url(evidence.source_url) or ref.source_url,
                available=available,
                missing_reason=missing_reason,
            )
        )
    return candidates, missing


def _selection(
    evidence: list[_CandidateEvidence],
    include_evidence: bool | None,
    evidence_ids: list[int] | None,
    locale: str,
) -> set[int]:
    labels = _labels(locale)
    available_ids = {item.evidence.id for item in evidence if item.available}
    if include_evidence is not None and evidence_ids is not None:
        raise api_error(422, "invalid_evidence_selection", labels["invalid_selection"])
    if include_evidence is not None:
        return available_ids if include_evidence else set()
    if evidence_ids is None:
        return available_ids
    if len(evidence_ids) != len(set(evidence_ids)) or any(value < 1 for value in evidence_ids):
        raise api_error(422, "invalid_evidence_selection", labels["invalid_selection"])
    selected = set(evidence_ids)
    if not selected.issubset(available_ids):
        raise api_error(422, "invalid_evidence_selection", labels["invalid_selection"])
    return selected


def _archive_pdf(session: Session, user: AppUser, scope: TerritoryScope, card: SignalCard) -> Evidence | None:
    evidence = session.scalar(
        select(Evidence)
        .where(
            Evidence.signal_card_id == card.id,
            Evidence.kind == EvidenceKind.pdf,
        )
        .order_by(Evidence.id)
        .limit(1)
    )
    if evidence is None or not can_access_evidence(session, user, scope, evidence):
        return None
    return evidence


def _safe_card_token(number: str) -> str:
    token = _INVALID_FILENAME.sub("_", number).strip("_")
    return token[:64] or "signal"


def _evidence_filename(evidence: Evidence) -> str:
    extension = _SAFE_EXTENSIONS.get(evidence.content_type.split(";", maxsplit=1)[0].strip().lower(), ".bin")
    return f"evidence-{evidence.id}{extension}"


def _file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_limited(evidence: Evidence, remaining_total: int, locale: str) -> _ReadEvidence:
    labels = _labels(locale)
    if remaining_total <= 0:
        raise api_error(413, "package_total_size_limit", labels["total_limit"])
    limit = min(MAX_PACKAGE_FILE_BYTES, remaining_total)
    try:
        response = storage.open_evidence(evidence)
    except Exception:
        logger.warning("Package evidence %s could not be opened", evidence.id)
        return _ReadEvidence(None, labels["storage_missing"])
    chunks: list[bytes] = []
    actual_size = 0
    try:
        while True:
            chunk = response.read(min(_READ_CHUNK_BYTES, limit - actual_size + 1))
            if not chunk:
                break
            actual_size += len(chunk)
            if actual_size > MAX_PACKAGE_FILE_BYTES:
                raise api_error(413, "package_file_too_large", labels["file_limit"])
            if actual_size > remaining_total:
                raise api_error(413, "package_total_size_limit", labels["total_limit"])
            chunks.append(chunk)
    except HTTPException:
        raise
    except Exception:
        logger.warning("Package evidence %s could not be fully read", evidence.id)
        return _ReadEvidence(None, labels["storage_missing"])
    finally:
        response.close()
        response.release_conn()
    data = b"".join(chunks)
    if _file_hash(data) != evidence.sha256:
        logger.warning("Package evidence %s did not match its recorded digest", evidence.id)
        return _ReadEvidence(None, labels["evidence_integrity"])
    return _ReadEvidence(data)


def _archive_bytes(evidence: Evidence, remaining_total: int, locale: str) -> _ReadEvidence:
    labels = _labels(locale)
    result = _read_limited(evidence, remaining_total, locale)
    if result.data is None and result.reason == labels["storage_missing"]:
        return _ReadEvidence(None, labels["archive_missing"])
    if result.data is None:
        return _ReadEvidence(None, labels["archive_integrity"])
    return result


def _cover_facts(sections: dict[str, Any], labels: dict[str, str]) -> tuple[list[str], list[str]]:
    verified: list[str] = []
    to_check: list[str] = []
    if sections.get("legal_basis_status") == "confirmed":
        verified.append(labels["legal_basis_confirmed"])
    for check in _snapshot_items(sections, "permit_checks"):
        if check.get("check_status") == CheckStatus.confirmed.value:
            doc_type = check.get("doc_type")
            doc = labels.get(f"doc_{doc_type}", str(doc_type or ""))
            verified.append(labels["permit_confirmed"].format(doc=doc))
    for publication in _snapshot_items(sections, "publications"):
        post_id = publication.get("ad_post_id")
        hits = publication.get("hits")
        for hit in hits if isinstance(hits, list) else []:
            if not isinstance(hit, dict):
                continue
            confirmed = hit.get("confirmed")
            fragment = str(hit.get("fragment") or "").strip()
            if confirmed is True and fragment:
                verified.append(labels["hit_confirmed"].format(fragment=fragment, id=post_id))
            elif confirmed is None:
                if hit.get("detected_by") == "llm":
                    to_check.append(labels["hit_ai_review"].format(id=post_id))
                else:
                    to_check.append(labels["hit_needs_review"].format(id=post_id))
    flags = sections.get("needs_check")
    for flag in flags if isinstance(flags, list) else []:
        if isinstance(flag, dict):
            code = flag.get("code")
            name = labels.get(f"needs_{code}", "")
            if name:
                to_check.append(labels["needs_check"].format(name=name))
    return list(dict.fromkeys(verified)), list(dict.fromkeys(to_check))


def _cover_data(
    session: Session,
    view: service.CardView,
    user: AppUser,
    formed_at: datetime,
    labels: dict[str, str],
) -> dict[str, Any]:
    card = view.card
    sections = card.sections if isinstance(card.sections, dict) else {}
    snapshot_object = sections.get("object_developer")
    snapshot_object = snapshot_object if isinstance(snapshot_object, dict) else {}
    obj = session.get(ConstructionObject, card.object_id)
    territory = session.get(Territory, obj.territory_id) if obj is not None else None
    # The card stores its factual sections, but not its score. If a score is useful on the cover, use the
    # latest score calculated no later than the card snapshot instead of today's mutable object values.
    score = session.scalar(
        select(RiskScore)
        .where(RiskScore.object_id == card.object_id, RiskScore.calculated_at <= card.created_at)
        .order_by(RiskScore.calculated_at.desc(), RiskScore.id.desc())
        .limit(1)
    )
    recipient_key = (
        {
            Recipient.mio: "recipient_mio",
            Recipient.gask: "recipient_gask",
            Recipient.law_enforcement: "recipient_law",
        }.get(card.recipient)
        if card.recipient is not None
        else None
    )
    zone_key = f"zone_{score.zone.value}" if score is not None else ""
    verified, to_check = _cover_facts(sections, labels)
    return {
        "locale": user.locale.value,
        "card_number": card.number,
        "formed_at": formed_at,
        "card_created_at": card.created_at,
        "snapshot_at": card.created_at,
        "recipient_label": labels[recipient_key] if recipient_key else labels["recipient"],
        "object_code": snapshot_object.get("object_code"),
        "object_name": snapshot_object.get("object_name"),
        "developer_name": snapshot_object.get("developer_name"),
        "bin": snapshot_object.get("bin"),
        "address": snapshot_object.get("address"),
        "territory_label": territory.name if territory is not None else labels["whole_territory"],
        "zone_label": labels.get(zone_key) if zone_key else None,
        "score": score.score if score is not None else None,
        "is_draft": card.sent_at is None,
        "verified_facts": verified,
        "to_check_facts": to_check,
    }


def _publications_snapshot(card: SignalCard) -> list[dict[str, Any]]:
    sections = card.sections if isinstance(card.sections, dict) else {}
    return _snapshot_items(sections, "publications")


def _limits() -> SignalMaterialLimits:
    return SignalMaterialLimits(
        max_evidence_files=MAX_PACKAGE_EVIDENCE_FILES,
        max_file_bytes=MAX_PACKAGE_FILE_BYTES,
        max_total_bytes=MAX_PACKAGE_TOTAL_BYTES,
    )


def _fixed_names(number: str) -> dict[str, str]:
    token = _safe_card_token(number)
    return {
        "cover_docx": f"01_cover_{token}.docx",
        "signal_pdf": f"02_card_{token}.pdf",
        "publications_xlsx": f"03_publications_{token}.xlsx",
        "inventory_pdf": f"04_inventory_{token}.pdf",
    }


def _material_file(
    *,
    kind: MaterialKind,
    filename: str,
    source_label: str,
    available: bool,
    selected: bool,
    content_type: str | None = None,
    evidence_id: int | None = None,
    size_bytes: int | None = None,
    sha256: str | None = None,
    captured_at: datetime | None = None,
    source_url: str | None = None,
    missing_reason: str | None = None,
) -> SignalMaterialFile:
    return SignalMaterialFile(
        kind=kind,
        filename=filename,
        evidence_id=evidence_id,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        captured_at=captured_at,
        source_label=source_label,
        source_url=source_url,
        available=available,
        selected=selected,
        missing_reason=missing_reason,
    )


def build_preview(
    session: Session,
    view: service.CardView,
    user: AppUser,
    scope: TerritoryScope,
    include_evidence: bool | None = None,
    evidence_ids: list[int] | None = None,
) -> SignalMaterials:
    card = view.card
    locale = user.locale.value
    labels = _labels(locale)
    candidates, missing = _candidate_evidence(session, user, scope, card, locale)
    selected_ids = _selection(candidates, include_evidence, evidence_ids, locale)
    formed_at = datetime.now(UTC)
    is_draft = card.sent_at is None
    names = _fixed_names(card.number)
    archive = None if is_draft else _archive_pdf(session, user, scope, card)
    archive_available = bool(archive and _storage_available(archive))
    files = [
        _material_file(
            kind="cover_docx",
            filename=names["cover_docx"],
            source_label=labels["cover"],
            content_type=_DOCX_CONTENT_TYPE,
            available=True,
            selected=True,
        ),
        _material_file(
            kind="signal_pdf",
            filename=names["signal_pdf"],
            source_label=labels["draft_pdf"] if is_draft else labels["archive"],
            content_type=_PDF_CONTENT_TYPE,
            available=True if is_draft else archive_available,
            selected=True if is_draft else archive_available,
            evidence_id=archive.id if archive else None,
            size_bytes=archive.size_bytes if archive else None,
            sha256=archive.sha256 if archive else None,
            captured_at=archive.captured_at if archive else None,
            missing_reason=None if is_draft or archive_available else labels["archive_missing"],
        ),
        _material_file(
            kind="publications_xlsx",
            filename=names["publications_xlsx"],
            source_label=labels["publications"],
            content_type=_XLSX_CONTENT_TYPE,
            available=True,
            selected=True,
        ),
        _material_file(
            kind="inventory_pdf",
            filename=names["inventory_pdf"],
            source_label=labels["inventory"],
            content_type=_PDF_CONTENT_TYPE,
            available=True,
            selected=True,
        ),
    ]
    for candidate in candidates:
        evidence = candidate.evidence
        files.append(
            _material_file(
                kind="evidence",
                filename=_evidence_filename(evidence),
                source_label=candidate.source_label,
                content_type=evidence.content_type,
                evidence_id=evidence.id,
                size_bytes=evidence.size_bytes,
                sha256=evidence.sha256,
                captured_at=evidence.captured_at,
                source_url=candidate.source_url,
                available=candidate.available,
                selected=evidence.id in selected_ids,
                missing_reason=candidate.missing_reason,
            )
        )
        if candidate.missing_reason:
            missing.append((candidate.source_label, candidate.missing_reason))
    if not is_draft and not archive_available:
        missing.append((labels["archive"], labels["archive_missing"]))
    publications = _publications_snapshot(card)
    snapshot_capped = len(publications) >= service.MAX_PUBLICATIONS
    warnings = []
    if snapshot_capped:
        warnings.append(labels["snapshot_capped"])
    return SignalMaterials(
        signal_id=card.id,
        number=card.number,
        status=card.status,
        recipient=card.recipient,
        is_draft=is_draft,
        formed_at=formed_at,
        snapshot_at=card.created_at,
        snapshot_publications_capped=snapshot_capped,
        files=files,
        missing_materials=[
            SignalMissingMaterial(source_label=source_label, reason=reason)
            for source_label, reason in _unique_missing(missing)
        ],
        warnings=warnings,
        limits=_limits(),
    )


def _unique_missing(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return list(dict.fromkeys(items))


def _prepared_file(
    kind: str,
    filename: str,
    content_type: str,
    data: bytes,
    source_label: str,
    *,
    captured_at: datetime | None = None,
    evidence_id: int | None = None,
    source_url: str | None = None,
) -> _PackageFile:
    return _PackageFile(
        kind=kind,
        filename=filename,
        content_type=content_type,
        data=data,
        source_label=source_label,
        sha256=_file_hash(data),
        captured_at=captured_at,
        evidence_id=evidence_id,
        source_url=source_url,
    )


def _check_file_limits(files: list[_PackageFile], locale: str) -> int:
    labels = _labels(locale)
    total = 0
    for file in files:
        if len(file.data) > MAX_PACKAGE_FILE_BYTES:
            raise api_error(413, "package_file_too_large", labels["file_limit"])
        total += len(file.data)
        if total > MAX_PACKAGE_TOTAL_BYTES:
            raise api_error(413, "package_total_size_limit", labels["total_limit"])
    return total


def _inventory_row(
    *,
    filename: str,
    label: str,
    source_label: str,
    included: bool,
    content_type: str | None = None,
    size_bytes: int | None = None,
    sha256: str | None = None,
    captured_at: datetime | None = None,
    source_url: str | None = None,
    evidence_id: int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    return {
        "filename": filename,
        "label": label,
        "source_label": source_label,
        "evidence_id": evidence_id,
        "content_type": content_type,
        "size_bytes": size_bytes,
        "sha256": sha256,
        "captured_at": captured_at,
        "source_url": source_url,
        "included": included,
        "note": note,
    }


def _zip_info(filename: str) -> ZipInfo:
    info = ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    return info


def _zip_package(folder: str, files: list[_PackageFile], locale: str) -> bytes:
    labels = _labels(locale)
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for file in files:
            archive.writestr(_zip_info(f"{folder}/{file.filename}"), file.data)
    data = output.getvalue()
    if len(data) > MAX_PACKAGE_TOTAL_BYTES:
        raise api_error(413, "package_total_size_limit", labels["total_limit"])
    return data


def build_package(
    session: Session,
    view: service.CardView,
    user: AppUser,
    scope: TerritoryScope,
    request: Request,
    include_evidence: bool | None = None,
    evidence_ids: list[int] | None = None,
) -> tuple[bytes, str, str]:
    card = view.card
    locale = user.locale.value
    labels = _labels(locale)
    candidates, reference_missing = _candidate_evidence(session, user, scope, card, locale)
    selected_ids = _selection(candidates, include_evidence, evidence_ids, locale)
    if len(selected_ids) > MAX_PACKAGE_EVIDENCE_FILES:
        raise api_error(413, "package_evidence_limit", labels["evidence_limit"])

    formed_at = datetime.now(UTC)
    names = _fixed_names(card.number)
    is_draft = card.sent_at is None
    publications = _publications_snapshot(card)
    publications_bytes = render_publications_xlsx(
        locale,
        publications,
        card_number=card.number,
        is_draft=is_draft,
        generated_at=formed_at,
    )
    publications_file = _prepared_file(
        "publications_xlsx",
        names["publications_xlsx"],
        _XLSX_CONTENT_TYPE,
        publications_bytes,
        labels["publications"],
    )
    generated_files = [publications_file]
    missing = list(reference_missing)
    archive_evidence: Evidence | None = None
    card_pdf_file: _PackageFile | None = None
    if is_draft:
        allowed_ids = {candidate.evidence.id for candidate in candidates if candidate.available}
        draft_pdf = pdf.render_pdf(
            session,
            view,
            locale,
            draft=True,
            allowed_evidence_ids=allowed_ids,
            max_embedded_total_bytes=MAX_DRAFT_PDF_EMBED_BYTES,
        )
        card_pdf_file = _prepared_file(
            "signal_pdf", names["signal_pdf"], _PDF_CONTENT_TYPE, draft_pdf, labels["draft_pdf"]
        )
    else:
        archive_evidence = _archive_pdf(session, user, scope, card)
        if archive_evidence is None:
            missing.append((labels["archive"], labels["archive_missing"]))
        else:
            provisional_total = sum(len(file.data) for file in generated_files)
            result = _archive_bytes(
                archive_evidence,
                MAX_PACKAGE_TOTAL_BYTES - provisional_total,
                locale,
            )
            if result.data is None:
                missing.append((labels["archive"], result.reason or labels["archive_integrity"]))
            else:
                card_pdf_file = _prepared_file(
                    "signal_pdf",
                    names["signal_pdf"],
                    _PDF_CONTENT_TYPE,
                    result.data,
                    labels["archive"],
                    captured_at=archive_evidence.captured_at,
                    evidence_id=archive_evidence.id,
                )
    if card_pdf_file is None:
        missing.append((labels["draft_pdf"] if is_draft else labels["archive"], labels["archive_missing"]))

    fixed_files = generated_files + ([card_pdf_file] if card_pdf_file else [])
    total = _check_file_limits(fixed_files, locale)
    candidate_by_id = {item.evidence.id: item for item in candidates}
    included_evidence: list[_PackageFile] = []
    evidence_results: dict[int, tuple[_PackageFile | None, str | None]] = {}
    for evidence_id in sorted(selected_ids):
        candidate = candidate_by_id[evidence_id]
        result = _read_limited(candidate.evidence, MAX_PACKAGE_TOTAL_BYTES - total, locale)
        if result.data is None:
            evidence_results[evidence_id] = (None, result.reason)
            continue
        file = _prepared_file(
            "evidence",
            _evidence_filename(candidate.evidence),
            candidate.evidence.content_type,
            result.data,
            candidate.source_label,
            captured_at=candidate.evidence.captured_at,
            evidence_id=evidence_id,
            source_url=candidate.source_url,
        )
        total += len(file.data)
        included_evidence.append(file)
        evidence_results[evidence_id] = (file, None)

    cover_data = _cover_data(session, view, user, formed_at, labels)
    cover_data["appendices"] = (
        [file.filename for file in fixed_files if file.kind != "cover_docx"]
        + [file.filename for file in included_evidence]
        + [names["inventory_pdf"]]
    )
    cover_bytes = render_cover_docx(cover_data)
    cover_file = _prepared_file("cover_docx", names["cover_docx"], _DOCX_CONTENT_TYPE, cover_bytes, labels["cover"])
    generated_files = [cover_file, *generated_files]
    fixed_files = generated_files + ([card_pdf_file] if card_pdf_file else [])

    inventory_rows: list[dict[str, Any]] = []
    for file in fixed_files:
        inventory_rows.append(
            _inventory_row(
                filename=file.filename,
                label=file.source_label,
                source_label=labels["cover"] if file.kind == "cover_docx" else file.source_label,
                included=True,
                content_type=file.content_type,
                size_bytes=len(file.data),
                sha256=file.sha256,
                captured_at=file.captured_at,
                evidence_id=file.evidence_id,
            )
        )
    for candidate in candidates:
        evidence = candidate.evidence
        result_file, result_reason = evidence_results.get(evidence.id, (None, None))
        if evidence.id in selected_ids and result_file is not None:
            inventory_rows.append(
                _inventory_row(
                    filename=result_file.filename,
                    label=candidate.source_label,
                    source_label=candidate.source_label,
                    included=True,
                    content_type=result_file.content_type,
                    size_bytes=len(result_file.data),
                    sha256=result_file.sha256,
                    captured_at=evidence.captured_at,
                    source_url=candidate.source_url,
                    evidence_id=evidence.id,
                )
            )
        else:
            reason = (
                candidate.missing_reason
                or (result_reason if evidence.id in selected_ids else labels["selection_excluded"])
                or labels["storage_missing"]
            )
            inventory_rows.append(
                _inventory_row(
                    filename=_evidence_filename(evidence),
                    label=candidate.source_label,
                    source_label=candidate.source_label,
                    included=False,
                    content_type=evidence.content_type,
                    size_bytes=evidence.size_bytes,
                    sha256=evidence.sha256,
                    captured_at=evidence.captured_at,
                    source_url=candidate.source_url,
                    evidence_id=evidence.id,
                    note=reason,
                )
            )
            if evidence.id in selected_ids and result_reason:
                missing.append((candidate.source_label, result_reason))
    for source_label, reason in _unique_missing(missing):
        inventory_rows.append(
            _inventory_row(
                filename="unavailable-snapshot-reference.bin",
                label=source_label,
                source_label=source_label,
                included=False,
                note=reason,
            )
        )
    inventory_bytes = render_inventory_pdf(
        locale,
        inventory_rows,
        card_number=card.number,
        is_draft=is_draft,
        generated_at=formed_at,
    )
    inventory_file = _prepared_file(
        "inventory_pdf", names["inventory_pdf"], _PDF_CONTENT_TYPE, inventory_bytes, labels["inventory"]
    )
    final_files = generated_files + ([card_pdf_file] if card_pdf_file else []) + included_evidence + [inventory_file]
    _check_file_limits(final_files, locale)
    folder = f"SAQ_{_safe_card_token(card.number)}"
    package = _zip_package(folder, final_files, locale)
    filename = f"SAQ_{_safe_card_token(card.number)}_materials.zip"
    audit.record(
        session,
        user,
        "signal.materials_package.download",
        "signal_card",
        card.id,
        None,
        {
            "card_number": card.number,
            "selected_evidence_count": len(selected_ids),
            "included_evidence_count": len(included_evidence),
            "included_file_count": len(final_files),
            "package_size_bytes": len(package),
            "is_draft": is_draft,
        },
        request,
    )
    session.commit()
    return package, filename, f"SAQ_{_safe_card_token(card.number)}_materials.zip"


def package_response_headers(filename: str, fallback: str) -> dict[str, str]:
    return {
        "Content-Disposition": content_disposition(filename, fallback),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
