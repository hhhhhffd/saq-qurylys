"""PDF of a signal card: a Jinja2 template rendered by WeasyPrint (SPEC section 7.2)."""

import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader
from minio.error import S3Error
from sqlalchemy import select
from sqlalchemy.orm import Session
from weasyprint import HTML
from weasyprint.document import Document

from app import storage
from app.models import ConstructionObject, Evidence
from app.modules.risk.engine import FACTOR_LABELS
from app.modules.signals.labels import get_labels
from app.modules.signals.service import CardView

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
EMBEDDED_IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
MAX_EMBEDDED_BYTES = 20 * 1024 * 1024

# Autoescape is on: every value reaching the template (including stored texts) is HTML-escaped.
_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True)


def _local(value: str | None, tz: ZoneInfo, *, with_time: bool = True) -> str:
    if not value:
        return ""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(tz)
    return parsed.strftime("%d.%m.%Y %H:%M" if with_time and "T" in value else "%d.%m.%Y")


def _embedded_image(
    evidence: Evidence, labels: dict[str, Any], max_bytes: int = MAX_EMBEDDED_BYTES
) -> tuple[str | None, str | None, int]:
    """Embed one bounded image and return its actual byte count; other evidence is listed only."""
    if evidence.content_type not in EMBEDDED_IMAGE_TYPES or max_bytes <= 0:
        return None, labels["not_embedded"], 0
    limit = min(MAX_EMBEDDED_BYTES, max_bytes)
    if evidence.size_bytes > limit:
        return None, labels["not_embedded"], 0
    chunks: list[bytes] = []
    actual_size = 0
    oversized = False
    try:
        response = storage.open_evidence(evidence)
        try:
            while True:
                chunk = response.read(limit - actual_size + 1)
                if not chunk:
                    break
                chunks.append(chunk)
                actual_size += len(chunk)
                if actual_size > limit:
                    oversized = True
                    break
        finally:
            response.close()
            response.release_conn()
    except S3Error:
        logger.warning(
            "Evidence %s is missing in storage; the PDF lists it without the image", evidence.id, exc_info=True
        )
        return None, labels["unavailable"], 0
    if oversized:
        return None, labels["not_embedded"], 0
    data = b"".join(chunks)
    return f"data:{evidence.content_type};base64,{base64.b64encode(data).decode('ascii')}", None, len(data)


def _format_value(value: Any, labels: dict[str, Any]) -> str:
    if value is None or value == "":
        return str(labels["empty"])
    if isinstance(value, bool):
        return str(labels["yes" if value else "no"])
    if isinstance(value, list):
        return ", ".join(_format_value(item, labels) for item in value) or str(labels["empty"])
    if isinstance(value, dict):
        return "; ".join(
            f"{labels['codes'].get(key, key)}: {_format_value(item, labels)}" for key, item in value.items()
        )
    if isinstance(value, str):
        return str(labels["codes"].get(value, value))
    return str(value)


def build_context(
    session: Session,
    view: CardView,
    locale: str = "ru",
    *,
    draft: bool = False,
    allowed_evidence_ids: set[int] | None = None,
    max_embedded_total_bytes: int | None = None,
) -> dict[str, Any]:
    labels = get_labels(locale)
    card, sections = view.card, view.card.sections
    tz = ZoneInfo(view.timezone)
    obj = session.get(ConstructionObject, card.object_id)

    evidence_ids = [
        evidence_id
        for key in ("permit_checks", "publications")
        for item in sections.get(key, [])
        for evidence_id in item["evidence_ids"]
    ]
    if allowed_evidence_ids is not None:
        evidence_ids = [evidence_id for evidence_id in evidence_ids if evidence_id in allowed_evidence_ids]
    remaining_embed_bytes = max_embedded_total_bytes
    evidence_rows = {
        row.id: row
        for row in session.scalars(select(Evidence).where(Evidence.id.in_(evidence_ids)).order_by(Evidence.id))
    }

    def evidence_items(ids: list[int]) -> list[dict[str, Any]]:
        nonlocal remaining_embed_bytes
        items = []
        for evidence_id in ids:
            row = evidence_rows.get(evidence_id)
            if row is None:
                continue
            if allowed_evidence_ids is not None and row.id not in allowed_evidence_ids:
                continue
            image_limit = MAX_EMBEDDED_BYTES
            if remaining_embed_bytes is not None:
                image_limit = min(image_limit, remaining_embed_bytes)
            image, note, embedded_bytes = _embedded_image(row, labels, image_limit)
            if remaining_embed_bytes is not None:
                remaining_embed_bytes -= embedded_bytes
            items.append(
                {
                    "id": row.id,
                    "kind": labels["evidence_kind"].get(row.kind.value, row.kind.value),
                    "captured_at": _local(row.captured_at.isoformat(), tz),
                    "sha256": row.sha256,
                    "source_url": row.source_url,
                    "image": image,
                    "note": note,
                }
            )
        return items

    meta = [
        (labels["meta"]["status"], labels["status"][card.status.value]),
        (labels["meta"]["origin"], labels["origin"][card.origin.value]),
        (labels["meta"]["created_at"], _local(card.created_at.isoformat(), tz)),
        (
            labels["meta"]["recipient"],
            labels["recipient"].get(card.recipient.value, "") if card.recipient else labels["empty"],
        ),
        (labels["meta"]["review_days"], card.review_days or labels["empty"]),
    ]
    if card.sent_at:
        meta.append((labels["meta"]["sent_at"], _local(card.sent_at.isoformat(), tz)))
    if card.due_date:
        meta.append((labels["meta"]["due_date"], _local(card.due_date.isoformat(), tz)))

    section = sections["object_developer"]
    object_developer = [
        (labels["object_developer"][key], _format_value(section.get(key), labels)) for key in labels["object_developer"]
    ]
    scheme = sections["scheme_payments"]
    scheme_payments = [
        (
            labels["scheme_payments"]["payment_schemes"],
            ", ".join(labels["payment_scheme"].get(code, code) for code in scheme["payment_schemes"])
            or labels["empty"],
        ),
        (labels["scheme_payments"]["contract_types"], ", ".join(scheme["contract_types"]) or labels["empty"]),
        (labels["scheme_payments"]["confirmed_payments_note"], scheme["confirmed_payments_note"] or labels["empty"]),
    ]
    route = sections["route"]
    zone = None
    if view.zone is not None and obj is not None:
        zone = {
            "code": view.zone.value,
            "label": labels["zone"][view.zone.value],
            "score": obj.score,
            "scored_at": _local(obj.last_scored_at.isoformat(), tz) if obj.last_scored_at else labels["empty"],
        }

    return {
        "t": labels,
        "draft": draft,
        "draft_label": ("ЧЕРНОВИК · НЕ НАПРАВЛЕНО" if locale != "kk" else "ЖОБА · ЖІБЕРІЛМЕГЕН"),
        "number": card.number,
        "meta": meta,
        "zone": zone,
        "object_developer": object_developer,
        "risk_factors": [
            {
                "name": f"{item.get('label') or FACTOR_LABELS.get(item['code'], '')} — "
                f"{labels['risk_factor'].get(item['code'], item['code'])}".lstrip(" —"),
                "weight": f"{item['weight']:+d}",
                "detail": [
                    (labels["detail_keys"].get(key, key.replace("_", " ")), _format_value(value, labels))
                    for key, value in (item["detail"] or {}).items()
                ],
                # What the factor rests on: the phrase found in a publication.
                "fragments": [
                    {"ad_id": ref["id"], "text": ref["fragment"]}
                    for ref in item.get("evidence", [])
                    if ref.get("fragment")
                ],
            }
            for item in sections["risk_factors"]
        ],
        "legal_basis": (
            labels["legal_basis"][sections["legal_basis_status"]] if sections.get("legal_basis_status") else None
        ),
        "needs_check": [
            {
                "name": labels["needs_check_flag"].get(flag["code"], flag["code"]),
                "detail": [
                    (labels["detail_keys"].get(key, key.replace("_", " ")), _format_value(value, labels))
                    for key, value in (flag.get("detail") or {}).items()
                ],
            }
            for flag in sections.get("needs_check", [])
        ],
        "permit_checks": [
            {
                "doc_type": labels["doc_type"].get(item["doc_type"], item["doc_type"]),
                "number": item["number"] or "",
                "check_status": labels["check_status"].get(item["check_status"], item["check_status"]),
                "source": labels["check_source"].get(item["source"], "") if item["source"] else "",
                "checked_at": _local(item["checked_at"], tz),
                "evidence": evidence_items(item["evidence_ids"]),
            }
            for item in sections["permit_checks"]
        ],
        "publications": [
            {
                "id": item["ad_post_id"],
                "platform": labels["platform"].get(item["platform"], item["platform"]),
                "url": item["url"] or "",
                "published_at": _local(item["published_at"], tz),
                "captured_at": _local(item["captured_at"], tz),
                "status": labels["ad_status"].get(item["status"], item["status"]),
                "hits": [
                    {
                        "kind": hit["kind"],
                        "kind_label": labels["hit_kind"].get(hit["kind"], hit["kind"]),
                        "category": labels["codes"].get(hit["category"], hit["category"]),
                        "fragment": hit["fragment"],
                    }
                    for hit in item.get("hits", [])
                ],
                "evidence": evidence_items(item["evidence_ids"]),
            }
            for item in sections["publications"]
        ],
        "scheme_payments": scheme_payments,
        "measures": [labels["measure"].get(code, code) for code in sections["proposed_measures"]],
        "route": [
            (
                labels["route"]["recipient"],
                labels["recipient"].get(route["recipient"], labels["empty"]) if route["recipient"] else labels["empty"],
            ),
            (labels["route"]["review_days"], route["review_days"]),
        ],
        "note": sections["note"],
        "response": (
            {"text": card.response_text, "at": _local(card.response_at.isoformat(), tz)}
            if card.response_text and card.response_at
            else None
        ),
    }


def render_html(context: dict[str, Any]) -> str:
    return _env.get_template("signal_card.html").render(**context)


def render_document(html: str) -> Document:
    return HTML(string=html, base_url=str(TEMPLATES_DIR)).render()


def render_pdf(
    session: Session,
    view: CardView,
    locale: str = "ru",
    *,
    draft: bool = False,
    allowed_evidence_ids: set[int] | None = None,
    max_embedded_total_bytes: int | None = None,
) -> bytes:
    context = build_context(
        session,
        view,
        locale,
        draft=draft,
        allowed_evidence_ids=allowed_evidence_ids,
        max_embedded_total_bytes=max_embedded_total_bytes,
    )
    return bytes(render_document(render_html(context)).write_pdf())
