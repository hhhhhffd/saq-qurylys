"""Idempotent database seed: `python -m app.seed [--pilot] [--demo]`.

Reference data (territories, risk factors, phrases, settings) and the initial admin are always
created when missing and never overwritten. Optional files in app/seed_data/ are described in
app/seed_data/README.md. `--pilot` additionally imports the public snapshot of real objects of the pilot city,
`--demo` loads demo users and the fictional demo_objects.json.
"""

import argparse
import json
import logging
import re
import secrets
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from celery import chain
from pydantic import BaseModel, BeforeValidator, ConfigDict, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import get_sessionmaker
from app.events import objects_changed
from app.geo import make_point
from app.models import (
    AdPost,
    AppUser,
    Complaint,
    ConstructionObject,
    Developer,
    District,
    Document,
    Holiday,
    Inspection,
    LinkedEntity,
    Phrase,
    RiskFactor,
    RiskFactorChange,
    Territory,
)
from app.models.enums import (
    AdStatus,
    CheckSource,
    CheckStatus,
    ComplaintSource,
    ComplaintStatus,
    ConstructionStatus,
    DocType,
    HolidayKind,
    LinkedEntityKind,
    LinkMethod,
    Locale,
    PaymentScheme,
    PhraseCategory,
    Platform,
    Role,
    TerritoryLevel,
)
from app.modules.registry_sync.pilot import import_pilot
from app.modules.registry_sync.upsert import assign_district
from app.modules.settings.service import ensure_defaults
from app.phones import normalize_phone
from app.security import hash_password
from app.worker.celery_app import celery_app

logger = logging.getLogger("app.seed")

SEED_DATA_DIR = Path(__file__).parent / "seed_data"
REGION_CODE = "vko"
CITY_CODE = "ust-kamenogorsk"
# Since 2024-03-01 Kazakhstan uses a single UTC+5 time zone; IANA keeps the Asia/Almaty zone for it.
TIMEZONE = "Asia/Almaty"

RISK_FACTORS = [
    (
        "r1_no_legal_basis",
        "Установлено отсутствие правового основания: гарантия КЖК и разрешение МИО проверены, не найдены",
        35,
    ),
    (
        "r2_money_offer",
        "В рекламе за период есть предложение внести деньги: бронь, задаток, депозит, рассрочка, предв. договор",
        25,
    ),
    ("r3_active_ads", "За период есть реклама объекта", 10),
    ("r4_collective_complaint", "Есть проверенное незакрытое коллективное обращение", 15),
    ("r5_readiness_mismatch", "Заявленная в рекламе готовность выше фактической на пороговое значение", 10),
    ("r6_stalled_or_delayed", "Строительство остановлено или срок сдачи существенно сорван", 5),
]
# Codes of the first risk model. Removed when nothing refers to them, otherwise switched off.
OBSOLETE_RISK_FACTORS = (
    "no_permit",
    "money_offer",
    "active_ads",
    "complaints",
    "readiness_overstated",
    "on_schedule",
)

# (category, text, variants, weight)
PHRASES: list[tuple[PhraseCategory, str, list[str], int]] = [
    (
        PhraseCategory.booking,
        "бронирование",
        ["бронь", "забронировать", "бронировать", "бронирование квартиры", "онлайн бронь"],
        10,
    ),
    (
        PhraseCategory.down_payment,
        "первоначальный взнос",
        ["первый взнос", "стартовый взнос", "внести первоначальный взнос", "первоначалка"],
        10,
    ),
    (
        PhraseCategory.installment,
        "рассрочка",
        ["в рассрочку", "беспроцентная рассрочка", "рассрочка от застройщика", "рассрочка без процентов"],
        8,
    ),
    (
        PhraseCategory.sales_start,
        "старт продаж",
        ["открытие продаж", "начало продаж", "стартовали продажи", "открыли продажи"],
        5,
    ),
    (
        PhraseCategory.preliminary_contract,
        "предварительный договор",
        ["предварительный договор купли-продажи", "предварительное соглашение", "договор о намерениях"],
        10,
    ),
    (
        PhraseCategory.deposit,
        "задаток",
        [
            "внести задаток",
            "внести депозит",
            "оплатить депозит",
            "обеспечительный платёж",
            "обеспечительный взнос",
            "гарантийный взнос",
        ],
        10,
    ),
    (
        PhraseCategory.price_before_completion,
        "цена до сдачи дома",
        [
            "цены до сдачи",
            "цена до завершения",
            "цена до ввода в эксплуатацию",
            "успей купить до повышения цен",
            "цены вырастут после сдачи",
        ],
        6,
    ),
    (
        PhraseCategory.covert_contract,
        "инвестиционный договор",
        ["договор инвестирования", "инвестиционное соглашение", "инвестиционный контракт"],
        12,
    ),
    (
        PhraseCategory.covert_contract,
        "договор резервирования",
        ["резервирование квартиры", "договор резерва", "зарезервировать квартиру"],
        12,
    ),
]

DEMO_USERS = [
    ("demo_admin", "Демо: администратор", Role.admin, None),
    ("demo_mio", "Демо: сотрудник МИО", Role.mio_officer, CITY_CODE),
    ("demo_gask", "Демо: сотрудник ГАСК", Role.gask, CITY_CODE),
    ("demo_police", "Демо: правоохранительные органы", Role.law_enforcement, REGION_CODE),
]


def seed_territories(session: Session) -> None:
    region = session.scalar(select(Territory).where(Territory.code == REGION_CODE))
    if region is None:
        region = Territory(
            level=TerritoryLevel.region,
            code=REGION_CODE,
            name="Восточно-Казахстанская область",
            timezone=TIMEZONE,
            center=make_point(49.5, 82.0),
        )
        session.add(region)
        session.flush()
    if session.scalar(select(Territory.id).where(Territory.code == CITY_CODE)) is None:
        session.add(
            Territory(
                parent_id=region.id,
                level=TerritoryLevel.city,
                code=CITY_CODE,
                name="Усть-Каменогорск",
                timezone=TIMEZONE,
                center=make_point(49.9483, 82.6279),
            )
        )
    session.flush()


def seed_risk_factors(session: Session) -> None:
    existing = {row.code: row for row in session.scalars(select(RiskFactor))}
    for order, (code, description, weight) in enumerate(RISK_FACTORS, start=1):
        if code not in existing:
            session.add(RiskFactor(code=code, description=description, weight=weight, sort_order=order))
    for code in OBSOLETE_RISK_FACTORS:
        factor = existing.get(code)
        if factor is None:
            continue
        if session.scalar(select(RiskFactorChange.id).where(RiskFactorChange.code == code).limit(1)) is None:
            session.delete(factor)
        else:
            factor.is_active = False  # its weight history stays readable


# Variants added to the dictionary after the first release (the wording of the case: "внесите депозит",
# "цена до завершения"). An existing dictionary gets them appended; nothing else in it is touched.
ADDED_VARIANTS = frozenset({"внести депозит", "оплатить депозит", "цена до завершения"})


def seed_phrases(session: Session) -> None:
    existing = {(row.category, row.text): row for row in session.scalars(select(Phrase))}
    for category, text, variants, weight in PHRASES:
        phrase = existing.get((category, text))
        if phrase is None:
            session.add(Phrase(category=category, text=text, variants=variants, weight=weight))
            continue
        missing = [variant for variant in variants if variant in ADDED_VARIANTS and variant not in phrase.variants]
        if missing:
            phrase.variants = [*phrase.variants, *missing]


def seed_admin(session: Session) -> None:
    settings = get_settings()
    username = settings.initial_admin_username.strip().lower()
    if session.scalar(select(AppUser.id).where(AppUser.username == username)):
        return
    if not settings.initial_admin_password:
        raise SystemExit("INITIAL_ADMIN_PASSWORD is not set: cannot create the initial admin")
    session.add(
        AppUser(
            username=username,
            full_name="Администратор",
            password_hash=hash_password(settings.initial_admin_password),
            role=Role.admin,
            locale=Locale.ru,
        )
    )
    logger.info("Created initial admin %s", username)


def seed_reference(session: Session) -> None:
    seed_territories(session)
    seed_risk_factors(session)
    seed_phrases(session)
    ensure_defaults(session)
    seed_admin(session)
    session.flush()


def load_districts(session: Session) -> int:
    path = SEED_DATA_DIR / "districts.geojson"
    if not path.exists():
        return 0
    collection = json.loads(path.read_text(encoding="utf-8"))
    count = 0
    for feature in collection["features"]:
        properties = feature["properties"]
        territory = session.scalar(
            select(Territory).where(Territory.code == properties.get("territory_code", CITY_CODE))
        )
        if territory is None:
            raise SystemExit(f"districts.geojson: unknown territory_code {properties.get('territory_code')!r}")
        boundary = func.ST_Multi(func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(feature["geometry"])), 4326))
        district = session.scalar(
            select(District).where(District.territory_id == territory.id, District.name == properties["name"])
        )
        if district is None:
            session.add(District(territory_id=territory.id, name=properties["name"], boundary=boundary))
        else:
            district.boundary = boundary
        count += 1
    session.flush()
    return count


def load_holidays(session: Session) -> int:
    path = SEED_DATA_DIR / "holidays.json"
    if not path.exists():
        return 0
    entries = json.loads(path.read_text(encoding="utf-8"))
    for entry in entries:
        day = date.fromisoformat(entry["day"])
        kind = HolidayKind(entry["kind"])
        holiday = session.get(Holiday, day)
        if holiday is None:
            session.add(Holiday(day=day, kind=kind, name=entry["name"]))
        else:
            holiday.kind = kind
            holiday.name = entry["name"]
    session.flush()
    return len(entries)


# --- demo data ------------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Dates in demo_objects.json may be relative to the moment of loading ("-2d", "+330d", "-36h"), so the demo
# stays current: ads remain inside the analysis window, inspections fresh, deadlines in the future.
_RELATIVE = re.compile(r"([+-])(\d+)([dh])")


def _relative_delta(value: Any) -> timedelta | None:
    match = _RELATIVE.fullmatch(value.strip()) if isinstance(value, str) else None
    if match is None:
        return None
    amount = int(match[2]) * (1 if match[1] == "+" else -1)
    return timedelta(days=amount) if match[3] == "d" else timedelta(hours=amount)


def _resolve_date(value: Any) -> Any:
    delta = _relative_delta(value)
    return value if delta is None else (datetime.now(ZoneInfo(TIMEZONE)) + delta).date()


def _resolve_datetime(value: Any) -> Any:
    delta = _relative_delta(value)
    return value if delta is None else datetime.now(UTC) + delta


RelativeDate = Annotated[date, BeforeValidator(_resolve_date)]
RelativeDateTime = Annotated[datetime, BeforeValidator(_resolve_datetime)]


class DemoDeveloper(_Strict):
    bin: str
    name: str
    director: str | None = None
    founders: list[str] = []
    authorized_company: str | None = None
    phones: list[str] = []


class DemoDocument(_Strict):
    doc_type: DocType
    number: str | None = None
    issued_at: RelativeDate | None = None
    issuer: str | None = None
    check_status: CheckStatus = CheckStatus.checking
    check_source: CheckSource | None = None
    checked_at: RelativeDateTime | None = None
    note: str | None = None


class DemoComplaint(_Strict):
    received_at: RelativeDate
    source: ComplaintSource = ComplaintSource.manual
    external_id: str | None = None
    is_collective: bool = False
    signatories_count: int = 1
    summary: str | None = None
    status: ComplaintStatus = ComplaintStatus.new
    confirmed_payments: bool = False
    is_verified: bool = False


class DemoInspection(_Strict):
    inspected_at: RelativeDate
    readiness_pct: int
    lat: float | None = None
    lon: float | None = None
    note: str | None = None


class DemoLinkedEntity(_Strict):
    kind: LinkedEntityKind
    value: str
    note: str | None = None


class DemoAd(_Strict):
    platform: Platform
    url: str | None = None
    external_id: str | None = None
    author: str | None = None
    published_at: RelativeDateTime
    text: str
    phones: list[str] = []
    is_outdoor: bool = False
    lat: float | None = None
    lon: float | None = None
    payment_schemes: list[PaymentScheme] = []
    claimed_readiness_pct: int | None = None
    price_before_completion: bool = False
    status: AdStatus = AdStatus.captured


class DemoObject(_Strict):
    name: str
    aliases: list[str] = []
    territory_code: str = CITY_CODE
    district: str | None = None
    developer_bin: str | None = None
    address: str | None = None
    cadastral_number: str | None = None
    land_purpose: str | None = None
    lat: float | None = None
    lon: float | None = None
    planned_completion: RelativeDate | None = None
    forecast_completion: RelativeDate | None = None
    construction_status: ConstructionStatus = ConstructionStatus.active
    stalled_since: RelativeDate | None = None
    prior_violations: str | None = None
    readiness_claimed_pct: int | None = None
    documents: list[DemoDocument] = []
    complaints: list[DemoComplaint] = []
    inspections: list[DemoInspection] = []
    linked_entities: list[DemoLinkedEntity] = []
    ads: list[DemoAd] = []


class DemoData(_Strict):
    developers: list[DemoDeveloper] = []
    objects: list[DemoObject] = []


def seed_demo_users(session: Session) -> list[tuple[str, str]]:
    """Create demo users; return (username, password) for the newly created ones."""
    configured = get_settings().demo_user_password
    created: list[tuple[str, str]] = []
    for username, full_name, role, territory_code in DEMO_USERS:
        if session.scalar(select(AppUser.id).where(AppUser.username == username)):
            continue
        territory_id = (
            session.scalar(select(Territory.id).where(Territory.code == territory_code)) if territory_code else None
        )
        password = configured or secrets.token_urlsafe(12)
        session.add(
            AppUser(
                username=username,
                full_name=full_name,
                password_hash=hash_password(password),
                role=role,
                territory_id=territory_id,
            )
        )
        created.append((username, password))
    session.flush()
    return created


def _add_demo_object(session: Session, item: DemoObject) -> int:
    territory = session.scalar(select(Territory).where(Territory.code == item.territory_code))
    if territory is None:
        raise SystemExit(f"demo_objects.json: unknown territory_code {item.territory_code!r}")
    district_id = None
    if item.district:
        district_id = session.scalar(
            select(District.id).where(District.territory_id == territory.id, District.name == item.district)
        )
        if district_id is None:
            logger.warning("Demo object %r: district %r not found, left empty", item.name, item.district)
    developer_id = None
    if item.developer_bin:
        developer_id = session.scalar(select(Developer.id).where(Developer.bin == item.developer_bin))
        if developer_id is None:
            raise SystemExit(f"demo_objects.json: unknown developer_bin {item.developer_bin!r}")

    latest_inspection = max(item.inspections, key=lambda i: i.inspected_at, default=None)
    latest_claim = max(
        (ad for ad in item.ads if ad.claimed_readiness_pct is not None), key=lambda a: a.published_at, default=None
    )
    obj = ConstructionObject(
        territory_id=territory.id,
        district_id=district_id,
        developer_id=developer_id,
        name=item.name,
        aliases=item.aliases,
        address=item.address,
        cadastral_number=item.cadastral_number,
        land_purpose=item.land_purpose,
        location=make_point(item.lat, item.lon),
        planned_completion=item.planned_completion,
        forecast_completion=item.forecast_completion,
        construction_status=item.construction_status,
        stalled_since=item.stalled_since,
        prior_violations=item.prior_violations,
        readiness_actual_pct=latest_inspection.readiness_pct if latest_inspection else None,
        readiness_claimed_pct=item.readiness_claimed_pct
        if item.readiness_claimed_pct is not None
        else (latest_claim.claimed_readiness_pct if latest_claim else None),
        is_demo=True,
    )
    session.add(obj)
    session.flush()
    assign_district(session, obj)  # an object without a named district gets the one that contains its point

    now = datetime.now(UTC)
    # The demo officer "did" the checks and verifications of the demo data, so they show who decided.
    officer_id = session.scalar(select(AppUser.id).where(AppUser.username == "demo_mio"))
    session.add_all(
        Document(
            object_id=obj.id,
            checked_by=officer_id if doc.check_status is not CheckStatus.checking else None,
            **doc.model_dump(),
        )
        for doc in item.documents
    )
    session.add_all(
        Complaint(
            object_id=obj.id,
            verified_by=officer_id if c.is_verified else None,
            verified_at=now if c.is_verified else None,
            **c.model_dump(),
        )
        for c in item.complaints
    )
    session.add_all(
        Inspection(
            object_id=obj.id,
            inspected_at=i.inspected_at,
            readiness_pct=i.readiness_pct,
            location=make_point(i.lat, i.lon),
            note=i.note,
        )
        for i in item.inspections
    )
    session.add_all(LinkedEntity(object_id=obj.id, **e.model_dump()) for e in item.linked_entities)
    for ad in item.ads:
        phones = [phone for raw in ad.phones if (phone := normalize_phone(raw))]
        session.add(
            AdPost(
                territory_id=territory.id,
                platform=ad.platform,
                url=ad.url,
                external_id=ad.external_id,
                author=ad.author,
                published_at=ad.published_at,
                captured_at=now,
                text=ad.text,
                phones=phones,
                object_id=obj.id,
                link_confidence=1.0,
                link_method=LinkMethod.manual,
                payment_schemes=[scheme.value for scheme in ad.payment_schemes],
                claimed_readiness_pct=ad.claimed_readiness_pct,
                price_before_completion=ad.price_before_completion,
                is_outdoor=ad.is_outdoor,
                location=make_point(ad.lat, ad.lon),
                status=ad.status,
                is_demo=True,
            )
        )
    session.flush()
    return obj.id


def seed_demo_objects(session: Session) -> list[int]:
    path = SEED_DATA_DIR / "demo_objects.json"
    if not path.exists():
        logger.warning("%s not found: no demo objects loaded", path)
        return []
    try:
        data = DemoData.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise SystemExit(f"demo_objects.json is invalid:\n{exc}") from exc

    for developer in data.developers:
        if session.scalar(select(Developer.id).where(Developer.bin == developer.bin)) is None:
            payload: dict[str, Any] = developer.model_dump()
            payload["phones"] = [phone for raw in developer.phones if (phone := normalize_phone(raw))]
            session.add(Developer(**payload))
    session.flush()

    created: list[int] = []
    for item in data.objects:
        if session.scalar(
            select(ConstructionObject.id).where(
                ConstructionObject.is_demo.is_(True), ConstructionObject.name == item.name
            )
        ):
            continue
        created.append(_add_demo_object(session, item))
    return created


def run_pilot(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        try:
            result = import_pilot(session)
        except (OSError, ValueError, KeyError) as exc:
            raise SystemExit(f"pilot import failed: {exc}") from exc
        session.commit()
    objects_changed(result.changes.object_ids)
    logger.info(
        "Pilot data ready: %s krisha.kz objects, %s registry-only objects; created %s objects, %s documents; "
        "updated %s objects, %s documents; skipped as completed in the registry: %s; objects without a district: %s",
        result.krisha_objects,
        result.registry_only_objects,
        result.changes.objects_created,
        result.changes.documents_created,
        result.changes.objects_updated,
        result.changes.documents_updated,
        ", ".join(result.skipped_completed) or "none",
        result.without_district,
    )


def dispatch_demo_processing(ads: list[tuple[int, int]], objects_without_ads: list[int]) -> None:
    """Queue what turns the loaded demo data into scored objects (the pipeline of SPEC 5).

    Every ad goes through `nlp.analyze` -> `nlp.link` (-> `nlp.llm_extract` when `LLM_ENABLED`) and then its object
    is rescored (`risk.recalc_object`), so phrase hits exist before the score is calculated. A finding of the LLM
    is only a hypothesis until a person confirms it, so it does not change the score. Tasks are addressed by name:
    they live in other modules. Objects without ads are rescored right away. Does nothing when events are disabled.
    """
    settings = get_settings()
    if not settings.events_enabled:
        return
    for ad_post_id, object_id in ads:
        steps = [("nlp.analyze", "nlp", ad_post_id), ("nlp.link", "nlp", ad_post_id)]
        if settings.llm_enabled:
            steps.append(("nlp.llm_extract", "nlp", ad_post_id))
        steps.append(("risk.recalc_object", "score", object_id))
        try:
            chain(
                *(celery_app.signature(name, args=[arg], queue=queue, immutable=True) for name, queue, arg in steps)
            ).apply_async(retry=False)
        except Exception:
            logger.exception(
                "Failed to enqueue the processing of demo ad %s; the daily sweep will score it", ad_post_id
            )
            return
    objects_changed(objects_without_ads)


def run(demo: bool, pilot: bool = False) -> None:
    factory = get_sessionmaker()
    with factory() as session:
        seed_reference(session)
        districts = load_districts(session)
        holidays = load_holidays(session)
        session.commit()
        logger.info("Reference data ready (districts: %s, holiday entries: %s)", districts, holidays)

    if pilot:
        run_pilot(factory)
    if not demo:
        return
    from app.seed_versions import seed_demo_versions  # imported here: that module builds on this one

    with factory() as session:
        credentials = seed_demo_users(session)
        object_ids = seed_demo_objects(session)
        object_ids += seed_demo_versions(session)
        ads = [
            (row.id, row.object_id)
            for row in session.execute(select(AdPost.id, AdPost.object_id).where(AdPost.object_id.in_(object_ids)))
        ]
        session.commit()
    for username, password in credentials:
        print(f"demo user {username}: {password}")  # shown once; only the hash is stored
    if credentials:
        print("Passwords above are shown once. Set DEMO_USER_PASSWORD to choose your own.")
    with_ads = {object_id for _, object_id in ads}
    dispatch_demo_processing(ads, [object_id for object_id in object_ids if object_id not in with_ads])
    logger.info("Demo data ready (new objects: %s, new ads: %s)", len(object_ids), len(ads))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.seed", description=__doc__)
    parser.add_argument("--pilot", action="store_true", help="also import the public snapshot of real pilot objects")
    parser.add_argument("--demo", action="store_true", help="also load demo users and demo_objects.json")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    run(demo=args.demo, pilot=args.pilot)


if __name__ == "__main__":
    main()
