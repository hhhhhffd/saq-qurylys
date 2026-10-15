"""Idempotent database seed: `python -m app.seed [--demo]`.

Reference data (territories, risk factors, phrases, settings) and the initial admin are always
created when missing and never overwritten. Optional files in app/seed_data/ are described in
app/seed_data/README.md. `--demo` additionally loads demo users and demo_objects.json.
"""

import argparse
import json
import logging
import secrets
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_sessionmaker
from app.events import object_changed
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
from app.modules.settings.service import ensure_defaults
from app.phones import normalize_phone
from app.security import hash_password

logger = logging.getLogger("app.seed")

SEED_DATA_DIR = Path(__file__).parent / "seed_data"
REGION_CODE = "vko"
CITY_CODE = "ust-kamenogorsk"
# Since 2024-03-01 Kazakhstan uses a single UTC+5 time zone; IANA keeps the Asia/Almaty zone for it.
TIMEZONE = "Asia/Almaty"

RISK_FACTORS = [
    ("no_permit", "Нет подтверждённого разрешения (ДСУ) или гарантии", 40),
    (
        "money_offer",
        "В рекламе за период есть предложение внести деньги (бронь, задаток, рассрочка, предварительный договор)",
        20,
    ),
    ("active_ads", "За период есть реклама объекта", 15),
    ("complaints", "Есть коллективное обращение или число открытых обращений достигло порога", 15),
    ("readiness_overstated", "Заявленная в рекламе готовность выше фактической", 10),
    ("on_schedule", "Строительство идёт по графику (снижающий фактор)", -15),
]

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
        ["внести задаток", "обеспечительный платёж", "обеспечительный взнос", "гарантийный взнос"],
        10,
    ),
    (
        PhraseCategory.price_before_completion,
        "цена до сдачи дома",
        ["цены до сдачи", "цена до ввода в эксплуатацию", "успей купить до повышения цен", "цены вырастут после сдачи"],
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
    existing = set(session.scalars(select(RiskFactor.code)))
    for order, (code, description, weight) in enumerate(RISK_FACTORS, start=1):
        if code not in existing:
            session.add(RiskFactor(code=code, description=description, weight=weight, sort_order=order))


def seed_phrases(session: Session) -> None:
    existing = {(row.category, row.text) for row in session.scalars(select(Phrase))}
    for category, text, variants, weight in PHRASES:
        if (category, text) not in existing:
            session.add(Phrase(category=category, text=text, variants=variants, weight=weight))


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
    issued_at: date | None = None
    issuer: str | None = None
    check_status: CheckStatus = CheckStatus.checking
    check_source: CheckSource | None = None
    note: str | None = None


class DemoComplaint(_Strict):
    received_at: date
    source: ComplaintSource = ComplaintSource.manual
    external_id: str | None = None
    is_collective: bool = False
    signatories_count: int = 1
    summary: str | None = None
    status: ComplaintStatus = ComplaintStatus.new
    confirmed_payments: bool = False


class DemoInspection(_Strict):
    inspected_at: date
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
    published_at: datetime
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
    planned_completion: date | None = None
    forecast_completion: date | None = None
    construction_status: ConstructionStatus = ConstructionStatus.active
    stalled_since: date | None = None
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

    now = datetime.now(UTC)
    session.add_all(Document(object_id=obj.id, **doc.model_dump()) for doc in item.documents)
    session.add_all(Complaint(object_id=obj.id, **c.model_dump()) for c in item.complaints)
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


def run(demo: bool) -> None:
    factory = get_sessionmaker()
    with factory() as session:
        seed_reference(session)
        districts = load_districts(session)
        holidays = load_holidays(session)
        session.commit()
        logger.info("Reference data ready (districts: %s, holiday entries: %s)", districts, holidays)

    if not demo:
        return
    with factory() as session:
        credentials = seed_demo_users(session)
        object_ids = seed_demo_objects(session)
        session.commit()
    for username, password in credentials:
        print(f"demo user {username}: {password}")  # shown once; only the hash is stored
    if credentials:
        print("Passwords above are shown once. Set DEMO_USER_PASSWORD to choose your own.")
    for object_id in object_ids:
        object_changed(object_id)
    logger.info("Demo data ready (new objects: %s)", len(object_ids))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.seed", description=__doc__)
    parser.add_argument("--demo", action="store_true", help="also load demo users and demo_objects.json")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    run(demo=args.demo)


if __name__ == "__main__":
    main()
