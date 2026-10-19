"""Case file (dossier) of an object: one PDF with the passport, risk, documents, inspections, complaints,
publications, signal cards and an inventory of attachments. Rendered with the signal card PDF machinery."""

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.models import (
    AdPost,
    AppUser,
    Complaint,
    ConstructionObject,
    Developer,
    District,
    Document,
    Evidence,
    Inspection,
    SignalCard,
    Territory,
)
from app.models.enums import AdStatus
from app.modules.risk.engine import FACTOR_LABELS
from app.modules.risk.queries import AD_TIMESTAMP, latest_score_stmt
from app.modules.signals.labels import get_labels
from app.modules.signals.pdf import (
    EMBEDDED_IMAGE_TYPES,
    MAX_EMBEDDED_BYTES,
    _embedded_image,
    _env,
    _local,
    render_document,
)
from app.modules.signals.service import breakdown_parts

MAX_ADS = 50
MAX_AD_TEXT = 300
MAX_EMBEDDED_IMAGES = 30
# Total size of the embedded images: one request must not pull hundreds of megabytes out of storage.
MAX_EMBEDDED_TOTAL_BYTES = 60 * 1024 * 1024
MAX_WHY_FACTORS = 3


def _excerpt(text: str | None) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    return text if len(text) <= MAX_AD_TEXT else text[: MAX_AD_TEXT - 1].rstrip() + "…"


def build_context(session: Session, obj: ConstructionObject, user: AppUser, locale: str = "ru") -> dict[str, Any]:
    labels = get_labels(locale)
    d = labels["dossier"]
    empty = labels["empty"]
    territory = session.get(Territory, obj.territory_id)
    tz = ZoneInfo(territory.timezone if territory else "Asia/Almaty")
    developer = session.get(Developer, obj.developer_id) if obj.developer_id else None
    district = session.get(District, obj.district_id) if obj.district_id else None

    def day(value: Any) -> str:
        return _local(value.isoformat(), tz) if value else ""

    p = d["passport"]
    passport = [
        (p["code"], obj.code),
        (p["name"], obj.name),
        (p["aliases"], ", ".join(obj.aliases)),
        (p["address"], obj.address),
        (p["district"], district.name if district else None),
        (p["cadastral_number"], obj.cadastral_number),
        (p["land_purpose"], obj.land_purpose),
        (
            p["construction_status"],
            d["construction_status"].get(obj.construction_status.value, obj.construction_status.value),
        ),
        (p["planned_completion"], day(obj.planned_completion)),
        (p["forecast_completion"], day(obj.forecast_completion)),
        (p["stalled_since"], day(obj.stalled_since)),
        (p["readiness_actual"], obj.readiness_actual_pct),
        (p["readiness_claimed"], obj.readiness_claimed_pct),
        (p["key_status"], d["key_status"].get(obj.key_status.value, obj.key_status.value) if obj.key_status else None),
        (p["prior_violations"], obj.prior_violations),
        (p["developer"], developer.name if developer else None),
        (p["bin"], developer.bin if developer else None),
        (p["director"], developer.director if developer else None),
        (p["founders"], ", ".join(developer.founders or []) if developer else None),
        (p["phones"], ", ".join(developer.phones or []) if developer else None),
    ]
    passport = [(label, value if value not in (None, "") else empty) for label, value in passport]

    latest = session.scalar(latest_score_stmt(obj.id))
    factors, needs_check, basis_status = breakdown_parts(latest.breakdown if latest else None)

    def factor_name(item: dict[str, Any]) -> str:
        code = item["code"]
        return f"{item.get('label') or FACTOR_LABELS.get(code, '')} — {labels['risk_factor'].get(code, code)}".lstrip(
            " —"
        )

    triggered = sorted((item for item in factors if item["triggered"]), key=lambda item: -abs(item["weight"]))
    risk = {
        "zone": obj.zone.value if obj.zone else None,
        "zone_label": labels["zone"].get(obj.zone.value, obj.zone.value) if obj.zone else empty,
        "score": obj.score,
        "has_score": latest is not None,
        "why": [factor_name(item) for item in triggered[:MAX_WHY_FACTORS]],
        "factors": [
            {"name": factor_name(item), "triggered": item["triggered"], "weight": f"{item['weight']:+d}"}
            for item in factors
        ],
        "needs_check": [labels["needs_check_flag"].get(flag["code"], flag["code"]) for flag in needs_check],
        "legal_basis": labels["legal_basis"].get(basis_status, basis_status) if basis_status else None,
    }

    documents = session.scalars(select(Document).where(Document.object_id == obj.id).order_by(Document.id)).all()
    inspections = session.scalars(
        select(Inspection)
        .where(Inspection.object_id == obj.id)
        .order_by(Inspection.inspected_at.desc(), Inspection.id.desc())
    ).all()
    inspector_ids = {ins.inspector_id for ins in inspections if ins.inspector_id}
    inspector_names = {
        user_row.id: user_row.full_name
        for user_row in session.scalars(select(AppUser).where(AppUser.id.in_(inspector_ids)))
    }
    complaints = session.scalars(
        select(Complaint)
        .where(Complaint.object_id == obj.id)
        .order_by(Complaint.received_at.desc(), Complaint.id.desc())
    ).all()
    # A link nobody confirmed is not evidence about this object (as in the signal card sections).
    ad_filter = (AdPost.object_id == obj.id, AdPost.status != AdStatus.verification)
    ads_total = session.scalar(select(func.count()).select_from(AdPost).where(*ad_filter)) or 0
    ads = session.scalars(
        select(AdPost).where(*ad_filter).order_by(AD_TIMESTAMP.desc(), AdPost.id.desc()).limit(MAX_ADS)
    ).all()
    cards = session.scalars(select(SignalCard).where(SignalCard.object_id == obj.id).order_by(SignalCard.id)).all()

    # Attachments in the order of the sections; the owner title tells what each file belongs to.
    inv = d["inventory"]
    owners: list[tuple[InstrumentedAttribute[int | None], int, str]] = [
        *(
            (
                Evidence.document_id,
                doc.id,
                f"{inv['owner_document']}: "
                f"{labels['doc_type'].get(doc.doc_type.value, doc.doc_type.value)} {doc.number or ''}".rstrip(),
            )
            for doc in documents
        ),
        *(
            (
                Evidence.ad_post_id,
                ad.id,
                f"{inv['owner_publication']}: {labels['platform'].get(ad.platform.value, ad.platform.value)} #{ad.id}",
            )
            for ad in ads
        ),
        *(
            (Evidence.inspection_id, ins.id, f"{inv['owner_inspection']}: {day(ins.inspected_at)}")
            for ins in inspections
        ),
        *((Evidence.signal_card_id, card.id, f"{inv['owner_signal']}: {card.number}") for card in cards),
    ]
    owner_columns = (Evidence.document_id, Evidence.ad_post_id, Evidence.inspection_id, Evidence.signal_card_id)
    by_owner: dict[tuple[str, int], list[Evidence]] = {}
    if owners:
        evidence_rows = session.scalars(
            select(Evidence)
            .where(
                or_(
                    *(
                        column.in_([owner_id for owner_column, owner_id, _ in owners if owner_column is column])
                        for column in owner_columns
                    )
                )
            )
            .order_by(Evidence.captured_at, Evidence.id)
        )
        for row in evidence_rows:
            for column in owner_columns:
                owner_id = getattr(row, column.key)
                if owner_id is not None:
                    by_owner.setdefault((column.key, owner_id), []).append(row)
    attachments: list[dict[str, Any]] = []
    embedded = 0
    embedded_bytes = 0
    for column, owner_id, owner_title in owners:
        for row in by_owner.get((column.key, owner_id), []):
            image, note = None, None
            if embedded < MAX_EMBEDDED_IMAGES:
                is_image = row.content_type in EMBEDDED_IMAGE_TYPES and row.size_bytes <= MAX_EMBEDDED_BYTES
                # The budget is checked on the recorded size, before anything is downloaded.
                if is_image and embedded_bytes + row.size_bytes > MAX_EMBEDDED_TOTAL_BYTES:
                    note = inv["over_budget"]
                else:
                    image, note, actual_bytes = _embedded_image(row, labels, MAX_EMBEDDED_TOTAL_BYTES - embedded_bytes)
                    if image is not None:
                        embedded += 1
                        embedded_bytes += actual_bytes
            attachments.append(
                {
                    "number": len(attachments) + 1,
                    "kind": labels["evidence_kind"].get(row.kind.value, row.kind.value),
                    "owner": owner_title,
                    "captured_at": _local(row.captured_at.isoformat(), tz),
                    "sha256": row.sha256,
                    "source_url": row.source_url or "",
                    "image": image,
                    "note": note,
                }
            )

    sections = [
        {"id": f"sec-{key}", "title": f"{number}. {title}"}
        for number, (key, title) in enumerate(d["sections"].items(), 1)
    ]

    return {
        "t": labels,
        "d": d,
        "obj_code": obj.code,
        "obj_name": obj.name,
        "address": obj.address or empty,
        "territory": territory.name if territory else empty,
        "formed_at": _local(datetime.now(UTC).isoformat(), tz),
        "formed_by": user.full_name,
        "sections": sections,
        "titles": {section["id"]: section["title"] for section in sections},
        "passport": passport,
        "risk": risk,
        "documents": [
            {
                "doc_type": labels["doc_type"].get(doc.doc_type.value, doc.doc_type.value),
                "number": doc.number or "",
                "issued_at": day(doc.issued_at),
                "issuer": doc.issuer or "",
                "check_status": labels["check_status"].get(doc.check_status.value, doc.check_status.value),
                "checked_at": day(doc.checked_at),
                "source": labels["check_source"].get(doc.check_source.value, "") if doc.check_source else "",
                "note": doc.note or "",
            }
            for doc in documents
        ],
        "inspections": [
            {
                "inspected_at": day(ins.inspected_at),
                "readiness": ins.readiness_pct,
                "inspector": inspector_names.get(ins.inspector_id, "") if ins.inspector_id else "",
                "note": ins.note or "",
            }
            for ins in inspections
        ],
        "complaints": [
            {
                "received_at": day(item.received_at),
                "source": d["complaint_source"].get(item.source.value, item.source.value),
                "kind": f"{d['complaints']['collective']}: {item.signatories_count}"
                if item.is_collective
                else d["complaints"]["individual"],
                "summary": item.summary or "",
                "status": d["complaint_status"].get(item.status.value, item.status.value),
            }
            for item in complaints
        ],
        "ads": [
            {
                "date": day(ad.published_at or ad.captured_at or ad.created_at),
                "platform": labels["platform"].get(ad.platform.value, ad.platform.value),
                "author": ad.author or "",
                "url": ad.url or "",
                "status": labels["ad_status"].get(ad.status.value, ad.status.value),
                "text": _excerpt(ad.text),
            }
            for ad in ads
        ],
        "ads_capped": d["publications"]["capped"].format(shown=len(ads), total=ads_total)
        if ads_total > len(ads)
        else None,
        "cards": [
            {
                "number": card.number,
                "status": labels["status"].get(card.status.value, card.status.value),
                "recipient": labels["recipient"].get(card.recipient.value, "") if card.recipient else "",
                "sent_at": day(card.sent_at),
                "due_date": day(card.due_date),
                "response_at": day(card.response_at),
            }
            for card in cards
        ],
        "attachments": attachments,
        "images": [item for item in attachments if item["image"]],
        "images_capped": inv["images_capped"].format(shown=MAX_EMBEDDED_IMAGES)
        if embedded >= MAX_EMBEDDED_IMAGES and any(item["image"] is None and not item["note"] for item in attachments)
        else None,
    }


def render_pdf(session: Session, obj: ConstructionObject, user: AppUser, locale: str = "ru") -> bytes:
    html = _env.get_template("object_dossier.html").render(**build_context(session, obj, user, locale))
    return bytes(render_document(html).write_pdf())
