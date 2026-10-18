import logging
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile
from redis.exceptions import RedisError
from sqlalchemy import and_, exists, func, or_, select

from app import audit
from app.collectors import COLLECTOR_PLATFORMS, account_enabled, enabled_sources, platform_enabled
from app.collectors import lock as collect_lock
from app.collectors.aggregator import check_search_url
from app.config import get_settings
from app.deps import ScopeDep, SessionDep, StaffUser
from app.errors import api_error, forbidden
from app.events import objects_changed
from app.models import AdPost, ConstructionObject, PhraseHit, SourceAccount, Territory
from app.models.enums import (
    AdOrigin,
    AdReviewState,
    AdStatus,
    CaptureStatus,
    DetectedBy,
    LinkMethod,
    LlmStatus,
    OcrStatus,
    Platform,
)
from app.modules.ads import service
from app.modules.ads.schemas import (
    AdDetail,
    AdPatch,
    AdRow,
    AdTriage,
    CaptureRequest,
    CollectorStatus,
    CollectQueued,
    HitConfirm,
    PhraseHitOut,
    SourceAccountCreate,
    SourceAccountOut,
    SourceAccountUpdate,
)
from app.modules.ads.urls import (
    UnsafeUrlError,
    detect_platform,
    ensure_public_url,
    external_id_for,
    handle_from_url,
    is_http_url,
    split_url,
)
from app.modules.developers.service import get_visible_developer
from app.modules.nlp.llm import UNCERTAIN_BELOW, Extraction
from app.modules.nlp.service import finding_for_hit, recompute_weights, supported_facts
from app.modules.nlp.text import strip_ocr_marker
from app.modules.objects.service import get_object_in_scope
from app.schemas import Page
from app.uploads import PHOTO_TYPES, read_upload
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ads"])

MAX_PHOTOS = 20
MAX_TOTAL_PHOTO_BYTES = 100 * 1024 * 1024
MAX_TEXT_CHARS = 50_000
MAX_SOURCE_ACCOUNTS = 500


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _public_url(url: str) -> str:
    if not is_http_url(url):
        raise api_error(422, "invalid_url", "Ссылка должна начинаться с http:// или https://")
    return url


def _new_ad_fields(session: SessionDep, scope: ScopeDep, user: StaffUser, object_id: int | None) -> dict[str, object]:
    """Link and territory of a publication entered by a person: the object they name, else their territory."""
    if object_id is None:
        return {"territory_id": user.territory_id}
    obj = get_object_in_scope(session, scope, object_id)
    return {
        "object_id": obj.id,
        "territory_id": obj.territory_id,
        "link_method": LinkMethod.manual,
        "link_confidence": 1.0,
    }


# ---------------------------------------------------------------- publications


@router.get("/ads", response_model=Page[AdRow])
def list_ads(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    platform: Annotated[Platform | None, Query()] = None,
    object_id: Annotated[int | None, Query()] = None,
    status: Annotated[AdStatus | None, Query()] = None,
    is_demo: Annotated[bool | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    queue: bool = False,
    review_state: Annotated[AdReviewState | None, Query()] = None,
    duplicate_of: Annotated[int | None, Query(gt=0)] = None,
) -> Page[AdRow]:
    stmt = select(AdPost, ConstructionObject.name).outerjoin(
        ConstructionObject, ConstructionObject.id == AdPost.object_id
    )
    stmt = scope.restrict(stmt, AdPost.territory_id)
    if queue and review_state is None:
        unresolved = or_(
            AdPost.status == AdStatus.verification,
            AdPost.capture_status.in_((CaptureStatus.pending, CaptureStatus.failed)),
            AdPost.ocr_status.in_((OcrStatus.pending, OcrStatus.failed)),
            AdPost.llm_status.in_((LlmStatus.pending, LlmStatus.failed)),
            exists(select(PhraseHit.id).where(PhraseHit.ad_post_id == AdPost.id, PhraseHit.confirmed.is_(None))),
        )
        stmt = stmt.where(
            or_(
                AdPost.review_state == AdReviewState.unreviewed,
                and_(AdPost.review_state == AdReviewState.reviewed, unresolved),
            )
        )
    elif review_state is not None:
        stmt = stmt.where(AdPost.review_state == review_state)
    if platform is not None:
        stmt = stmt.where(AdPost.platform == platform)
    if object_id is not None:
        stmt = stmt.where(AdPost.object_id == object_id)
    if status is not None:
        stmt = stmt.where(AdPost.status == status)
    if duplicate_of is not None:
        anchor = service.get_ad_in_scope(session, scope, duplicate_of)
        if anchor.source_account_id is None or not anchor.text:
            raise api_error(
                422,
                "duplicate_group_unavailable",
                "У этой публикации нет сохранённого источника и текста для точной группировки",
            )
        stmt = stmt.where(AdPost.source_account_id == anchor.source_account_id, AdPost.text == anchor.text)
    if is_demo is not None:
        stmt = stmt.where(AdPost.is_demo == is_demo)
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(
            AdPost.text.ilike(pattern)
            | AdPost.author.ilike(pattern)
            | AdPost.url.ilike(pattern)
            | ConstructionObject.name.ilike(pattern)
            | func.array_to_string(AdPost.phones, " ").ilike(pattern)
        )
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    # Posts without a known publication date are ordered by the time they were captured or entered.
    recency = func.coalesce(AdPost.published_at, AdPost.captured_at, AdPost.created_at)
    rows = [
        (ad, object_name)
        for ad, object_name in session.execute(
            stmt.order_by(AdPost.max_phrase_weight.desc(), recency.desc(), AdPost.id.desc()).limit(limit).offset(offset)
        )
    ]
    return Page(items=service.build_rows(session, rows, scope), total=total)


@router.post("/ads/capture", response_model=AdDetail, status_code=201)
def capture_ad(
    body: CaptureRequest, response: Response, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> AdDetail:
    """Register a publication by its URL; a worker archives the page and analyzes the text."""
    url = _public_url(body.url)
    try:
        ensure_public_url(url)
    except UnsafeUrlError as exc:
        raise api_error(422, "url_not_allowed", str(exc)) from exc
    platform = body.platform or detect_platform(url)
    external_id = external_id_for(platform, url)

    existing = session.scalar(select(AdPost).where(AdPost.platform == platform, AdPost.external_id == external_id))
    if existing is not None:
        if not scope.contains(existing.territory_id):
            raise api_error(409, "ad_exists", "Эта публикация уже зафиксирована")
        response.status_code = 200
        if existing.capture_status not in {None, CaptureStatus.failed}:
            return service.build_detail(session, existing, scope)
        before = audit.snapshot(existing)
        existing.capture_status = CaptureStatus.pending
        existing.capture_error = None
        audit.record(session, user, "ad.recapture", "ad_post", existing.id, before, audit.snapshot(existing), request)
        session.commit()
        if not service.dispatch_pipeline(existing.id, capture=True, requested_by=user.id):
            service.mark_capture_unqueued(session, existing)
        return service.build_detail(session, existing, scope)

    fields = _new_ad_fields(session, scope, user, body.object_id)
    source = service.resolve_source_account(session, platform, url)
    ad = AdPost(
        platform=platform,
        url=url,
        external_id=external_id,
        author=handle_from_url(platform, url),
        source_account_id=source.id if source else None,
        capture_status=CaptureStatus.pending,
        origin=AdOrigin.capture,
        **fields,
    )
    session.add(ad)
    session.flush()
    session.refresh(ad)
    audit.record(session, user, "ad.capture", "ad_post", ad.id, None, audit.snapshot(ad), request)
    session.commit()
    if not service.dispatch_pipeline(ad.id, capture=True, requested_by=user.id):
        service.mark_capture_unqueued(session, ad)
    return service.build_detail(session, ad, scope)


@router.post("/ads/manual", response_model=AdDetail, status_code=201)
def create_manual_ad(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    request: Request,
    text: Annotated[str, Form(min_length=1, max_length=MAX_TEXT_CHARS)],
    platform: Annotated[Platform, Form()],
    url: Annotated[str | None, Form(max_length=2000)] = None,
    object_id: Annotated[int | None, Form()] = None,
    published_at: Annotated[datetime | None, Form()] = None,
    is_outdoor: Annotated[bool, Form()] = False,
    lat: Annotated[float | None, Form(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Form(ge=-180, le=180)] = None,
    photos: Annotated[list[UploadFile] | None, File()] = None,
    photos_brackets: Annotated[list[UploadFile] | None, File(alias="photos[]")] = None,
) -> AdDetail:
    """Enter a publication by hand (text and photos); outdoor advertising carries a map point."""
    text = strip_ocr_marker(text.strip())
    if not text:
        raise api_error(422, "validation_error", "Текст публикации не может быть пустым")
    if (lat is None) != (lon is None):
        raise api_error(422, "validation_error", "Координаты lat и lon указываются вместе")
    url = url.strip() if url and url.strip() else None
    if url is not None:
        _public_url(url)
    uploads = [upload for upload in (*(photos or []), *(photos_brackets or [])) if upload.filename]
    if len(uploads) > MAX_PHOTOS:
        raise api_error(422, "too_many_photos", f"Не более {MAX_PHOTOS} фотографий")
    # Validate every file before anything is written to storage.
    payloads: list[tuple[bytes, str]] = []
    total_bytes = 0
    for upload in uploads:
        data, content_type = read_upload(upload, PHOTO_TYPES)
        total_bytes += len(data)
        if total_bytes > MAX_TOTAL_PHOTO_BYTES:
            raise api_error(413, "request_too_large", "Суммарный размер фотографий больше 100 МБ")
        payloads.append((data, content_type))

    external_id = external_id_for(platform, url) if url else None
    if external_id is not None and session.scalar(
        select(AdPost.id).where(AdPost.platform == platform, AdPost.external_id == external_id)
    ):
        raise api_error(409, "ad_exists", "Эта публикация уже внесена")
    fields = _new_ad_fields(session, scope, user, object_id)
    ad = service.create_manual_ad(
        session,
        user,
        request,
        platform=platform,
        url=url,
        external_id=external_id,
        text=text,
        published_at=published_at,
        is_outdoor=is_outdoor,
        lat=lat,
        lon=lon,
        photos=payloads,
        ocr_status=OcrStatus.pending if payloads else None,
        fields=fields,
    )
    session.commit()
    if not service.dispatch_pipeline(ad.id, capture=False, requested_by=user.id):
        service.mark_capture_unqueued(session, ad)
    return service.build_detail(session, ad, scope)


@router.get("/ads/{ad_id}", response_model=AdDetail)
def get_ad(ad_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep) -> AdDetail:
    return service.build_detail(session, service.get_ad_in_scope(session, scope, ad_id), scope)


@router.patch("/ads/{ad_id}/triage", response_model=AdDetail)
def triage_ad(
    ad_id: int, body: AdTriage, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> AdDetail:
    """Record a staff triage decision without changing publication facts, status, or risk inputs."""
    ad = service.get_ad_in_scope(session, scope, ad_id, for_update=True)
    has_unreviewed_hits = bool(
        session.scalar(select(exists().where(PhraseHit.ad_post_id == ad.id, PhraseHit.confirmed.is_(None))))
    )
    has_confirmed_hits = bool(
        session.scalar(select(exists().where(PhraseHit.ad_post_id == ad.id, PhraseHit.confirmed.is_(True))))
    )
    pipeline_unresolved = (
        ad.capture_status in {CaptureStatus.pending, CaptureStatus.failed}
        or ad.ocr_status in {OcrStatus.pending, OcrStatus.failed}
        or ad.llm_status in {LlmStatus.pending, LlmStatus.failed}
    )
    verification_link = ad.status is AdStatus.verification
    confirmed_link = ad.object_id is not None and not verification_link

    if body.state is AdReviewState.reviewed:
        unresolved: list[str] = []
        if has_unreviewed_hits:
            unresolved.append("подтвердите или отклоните все найденные формулировки")
        if verification_link:
            unresolved.append("подтвердите или снимите неопределённую связь с ЖК в карточке публикации")
        if pipeline_unresolved:
            unresolved.append("дождитесь завершения или устраните ошибку обработки публикации")
        if unresolved:
            raise api_error(
                409,
                "reviewed_unresolved",
                "Чтобы отметить публикацию разобранной, сначала " + "; ".join(unresolved),
            )
    elif body.state is AdReviewState.irrelevant and (has_confirmed_hits or confirmed_link):
        actions: list[str] = []
        if has_confirmed_hits:
            actions.append("отклоните подтверждённые формулировки через действия у формулировок")
        if confirmed_link:
            actions.append("снимите подтверждённую связь с ЖК в карточке публикации")
        raise api_error(409, "irrelevant_has_facts", "Сначала " + "; ".join(actions))

    before = audit.snapshot(ad)
    ad.review_state = body.state
    if "note" in body.model_fields_set:
        ad.review_note = body.note
    ad.reviewed_by = user.id
    ad.reviewed_at = datetime.now(UTC)
    session.flush()
    audit.record(session, user, "ad.triage", "ad_post", ad.id, before, audit.snapshot(ad), request)
    session.commit()
    return service.build_detail(session, ad, scope)


def _confirmed_status(ad: AdPost) -> AdStatus:
    """Status of a post whose link a person has decided: a post found removed stays marked as removed."""
    return AdStatus.removed_saved if ad.removed_detected_at is not None else AdStatus.captured


@router.patch("/ads/{ad_id}", response_model=AdDetail)
def update_ad(
    ad_id: int, body: AdPatch, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> AdDetail:
    ad = service.get_ad_in_scope(session, scope, ad_id)
    changes = body.model_dump(exclude_unset=True)
    before = audit.snapshot(ad)
    previous_object_id = ad.object_id

    if "object_id" in changes:
        new_object_id = changes.pop("object_id")
        if new_object_id is None:
            ad.object_id = None
            ad.link_method = None
            ad.link_confidence = None
        else:
            obj = get_object_in_scope(session, scope, new_object_id)
            ad.object_id = obj.id
            ad.territory_id = obj.territory_id
            ad.link_method = LinkMethod.manual
            ad.link_confidence = 1.0
            if "status" not in changes and ad.status is AdStatus.verification:
                ad.status = _confirmed_status(ad)  # a person has decided the link
    if "status" in changes:
        new_status = changes.pop("status")
        if new_status is AdStatus.captured and ad.status is AdStatus.verification:
            new_status = _confirmed_status(ad)  # «confirm the link» of a post that has been removed since
        if new_status is AdStatus.removed_saved and ad.removed_detected_at is None:
            ad.removed_detected_at = datetime.now(UTC)
        elif new_status is not AdStatus.removed_saved:
            ad.removed_detected_at = None
        ad.status = new_status
    for field, value in changes.items():
        setattr(ad, field, value)

    session.flush()
    affected = [object_id for object_id in dict.fromkeys([previous_object_id, ad.object_id]) if object_id is not None]
    for object_id in affected:
        service.refresh_claimed_readiness(session, object_id)
    session.refresh(ad)
    audit.record(session, user, "ad.update", "ad_post", ad.id, before, audit.snapshot(ad), request)
    session.commit()
    objects_changed(affected)
    return service.build_detail(session, ad, scope)


@router.post("/ads/{ad_id}/hits/{hit_id}/confirm", response_model=PhraseHitOut)
def confirm_hit(
    ad_id: int, hit_id: int, body: HitConfirm, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> PhraseHitOut:
    ad = service.get_ad_in_scope(session, scope, ad_id)
    hit = session.get(PhraseHit, hit_id)
    if hit is None or hit.ad_post_id != ad.id:
        raise api_error(404, "hit_not_found", "Формулировка в публикации не найдена")
    before = audit.snapshot(hit)
    hit.confirmed = body.confirmed
    hit.confirmed_by = user.id
    session.flush()
    recompute_weights(session, ad)
    audit.record(session, user, "ad.confirm_hit", "phrase_hit", hit.id, before, audit.snapshot(hit), request)
    extraction = Extraction.model_validate(ad.llm_extraction) if ad.llm_extraction is not None else None
    result = PhraseHitOut.from_hit(hit, ad.text or "", finding_for_hit(hit, extraction))
    session.commit()
    if ad.object_id is not None:
        objects_changed([ad.object_id])
    return result


@router.post("/ads/{ad_id}/accept-llm", response_model=AdDetail)
def accept_llm(ad_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request) -> AdDetail:
    """Move what the model extracted into the confirmed fields of the publication."""
    ad = service.get_ad_in_scope(session, scope, ad_id)
    if ad.llm_status is not LlmStatus.done or ad.llm_extraction is None:
        raise api_error(409, "llm_not_ready", "Нет результата ИИ для подтверждения")
    extraction = Extraction.model_validate(ad.llm_extraction)
    facts = supported_facts(extraction, ad.text or "")
    before = audit.snapshot(ad)
    ad.payment_schemes = list(dict.fromkeys([*ad.payment_schemes, *(scheme.value for scheme in facts.payment_schemes)]))
    if facts.claimed_readiness_pct is not None:
        ad.claimed_readiness_pct = facts.claimed_readiness_pct
    if facts.price_before_completion:
        ad.price_before_completion = True
    for hit in session.scalars(
        select(PhraseHit).where(
            PhraseHit.ad_post_id == ad.id, PhraseHit.detected_by == DetectedBy.llm, PhraseHit.confirmed.is_(None)
        )
    ):
        # A finding the model itself doubts stays a hypothesis until a person confirms that very hit.
        finding = finding_for_hit(hit, extraction)
        if finding is None or finding.confidence >= UNCERTAIN_BELOW:
            hit.confirmed = True
            hit.confirmed_by = user.id
    session.flush()
    recompute_weights(session, ad)
    if ad.object_id is not None:
        service.refresh_claimed_readiness(session, ad.object_id)
    audit.record(session, user, "ad.accept_llm", "ad_post", ad.id, before, audit.snapshot(ad), request)
    session.commit()
    if ad.object_id is not None:
        objects_changed([ad.object_id])
    return service.build_detail(session, ad, scope)


# ---------------------------------------------------------------- source accounts


def _normalize_handle(handle: str) -> str:
    return handle.strip().removeprefix("@").lower()


def _get_account(session: SessionDep, scope: ScopeDep, account_id: int) -> SourceAccount:
    account = session.get(SourceAccount, account_id)
    if account is None or not scope.contains(account.territory_id):
        raise api_error(404, "source_account_not_found", "Аккаунт не найден")
    return account


def _check_account_references(
    session: SessionDep, scope: ScopeDep, object_id: int | None, developer_id: int | None, territory_id: int | None
) -> None:
    if object_id is not None:
        get_object_in_scope(session, scope, object_id)
    if developer_id is not None:
        get_visible_developer(session, scope, developer_id)
    if territory_id is not None:
        if session.get(Territory, territory_id) is None:
            raise api_error(422, "territory_not_found", "Территория не найдена")
        if not scope.contains(territory_id):
            raise forbidden("Территория вне вашей зоны ответственности")


def _ensure_account_unique(session: SessionDep, platform: Platform, handle: str, own_id: int | None = None) -> None:
    stmt = select(SourceAccount.id).where(
        SourceAccount.platform == platform, func.lower(SourceAccount.handle) == handle
    )
    if own_id is not None:
        stmt = stmt.where(SourceAccount.id != own_id)
    if session.scalar(stmt) is not None:
        raise api_error(409, "source_account_exists", "Такой аккаунт уже добавлен")


def _checked_search_url(url: str | None) -> str:
    """The search address of an aggregator account: an http(s) address on olx.kz or krisha.kz."""
    if url is None:
        raise api_error(422, "invalid_source_url", "Для агрегатора укажите ссылку на поиск на olx.kz или krisha.kz")
    try:
        check_search_url(url)
    except ValueError as exc:
        raise api_error(422, "invalid_source_url", str(exc)) from exc
    return url


def _reject_aggregator_object(object_id: int | None) -> None:
    """A saved search returns the listings of any seller, so it cannot vouch for an object (OPEN_QUESTIONS 29)."""
    if object_id is not None:
        raise api_error(
            422,
            "aggregator_object_not_allowed",
            "Поиск на агрегаторе нельзя привязать к объекту: он находит объявления любых продавцов",
        )


def _search_label(url: str) -> str:
    """Name of a search the user did not name: its address without the scheme, so that two searches differ."""
    parts = urlsplit(url)
    label = split_url(url)[0] + parts.path.rstrip("/") + (f"?{parts.query}" if parts.query else "")
    return label[:255].lower()


@router.get("/source-accounts/collectors", response_model=list[CollectorStatus])
def list_collectors(user: StaffUser) -> list[CollectorStatus]:
    """Which collectors are on. They are switched on in `.env`, not here."""
    settings = get_settings()
    sources = enabled_sources(settings)
    return [
        CollectorStatus(
            platform=platform,
            enabled=platform_enabled(platform, settings),
            sources={name: sources[name] for name in ("olx", "krisha")} if platform is Platform.aggregator else {},
        )
        for platform in COLLECTOR_PLATFORMS
    ]


@router.get("/source-accounts", response_model=Page[SourceAccountOut])
def list_source_accounts(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    limit: Annotated[int, Query(ge=1, le=MAX_SOURCE_ACCOUNTS)] = MAX_SOURCE_ACCOUNTS,
    offset: Annotated[int, Query(ge=0)] = 0,
    platform: Annotated[Platform | None, Query()] = None,
    object_id: Annotated[int | None, Query()] = None,
    is_watched: Annotated[bool | None, Query()] = None,
) -> Page[SourceAccountOut]:
    stmt = scope.restrict(select(SourceAccount), SourceAccount.territory_id)
    if platform is not None:
        stmt = stmt.where(SourceAccount.platform == platform)
    if object_id is not None:
        stmt = stmt.where(SourceAccount.object_id == object_id)
    if is_watched is not None:
        stmt = stmt.where(SourceAccount.is_watched == is_watched)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(stmt.order_by(SourceAccount.platform, SourceAccount.handle).limit(limit).offset(offset))
    return Page(items=[SourceAccountOut.model_validate(row) for row in rows], total=total)


@router.post("/source-accounts", response_model=SourceAccountOut, status_code=201)
def create_source_account(
    body: SourceAccountCreate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> SourceAccount:
    handle = _normalize_handle(body.handle) if body.handle else None
    if body.platform is Platform.aggregator:
        url = _checked_search_url(body.url)
        _reject_aggregator_object(body.object_id)
        handle = handle or _search_label(url)
    elif handle is None and body.url is not None:
        handle = handle_from_url(body.platform, body.url)
    if not handle:
        raise api_error(422, "validation_error", "Не удалось определить имя аккаунта: укажите handle")
    _check_account_references(session, scope, body.object_id, body.developer_id, body.territory_id)
    _ensure_account_unique(session, body.platform, handle)
    territory_id = body.territory_id
    if territory_id is None:
        object_territory = (
            session.scalar(select(ConstructionObject.territory_id).where(ConstructionObject.id == body.object_id))
            if body.object_id is not None
            else None
        )
        territory_id = object_territory if object_territory is not None else user.territory_id
    account = SourceAccount(
        **body.model_dump(exclude={"handle", "territory_id"}), handle=handle, territory_id=territory_id
    )
    session.add(account)
    session.flush()
    session.refresh(account)
    audit.record(
        session, user, "source_account.create", "source_account", account.id, None, audit.snapshot(account), request
    )
    session.commit()
    return account


@router.patch("/source-accounts/{account_id}", response_model=SourceAccountOut)
def update_source_account(
    account_id: int, body: SourceAccountUpdate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> SourceAccount:
    account = _get_account(session, scope, account_id)
    changes = body.model_dump(exclude_unset=True)
    _check_account_references(
        session, scope, changes.get("object_id"), changes.get("developer_id"), changes.get("territory_id")
    )
    if account.platform is Platform.aggregator:
        if "url" in changes:
            _checked_search_url(changes["url"])
        _reject_aggregator_object(changes.get("object_id"))
    if "handle" in changes:
        changes["handle"] = _normalize_handle(changes["handle"])
        _ensure_account_unique(session, account.platform, changes["handle"], account.id)
    before = audit.snapshot(account)
    for field, value in changes.items():
        setattr(account, field, value)
    session.flush()
    session.refresh(account)
    audit.record(
        session, user, "source_account.update", "source_account", account.id, before, audit.snapshot(account), request
    )
    session.commit()
    return account


@router.post("/source-accounts/{account_id}/collect", response_model=CollectQueued, status_code=202)
def collect_source_account(
    account_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> CollectQueued:
    """Collect the account's new posts now; the worker runs the same collection as the scheduled one."""
    account = _get_account(session, scope, account_id)
    if account.platform is Platform.telegram and get_settings().userbot_configured:
        raise api_error(409, "collected_by_userbot", "Telegram собирает userbot: новые сообщения приходят сами")
    if not account_enabled(account, get_settings()):
        raise api_error(409, "collector_disabled", "Сборщик этого источника выключен: он включается в .env сервера")
    try:
        collecting = collect_lock.is_held(account.id)
    except RedisError as exc:
        logger.exception("Failed to read the collection lock of source account %s", account.id)
        raise api_error(503, "queue_unavailable", "Очередь задач недоступна") from exc
    if collecting:
        raise api_error(409, "collect_in_progress", "Сбор этого источника уже идёт")
    if get_settings().events_enabled:
        try:
            celery_app.send_task("collect.source", args=[account.id], queue="collect", retry=False, ignore_result=True)
        except Exception as exc:
            logger.exception("Failed to enqueue collect.source for source account %s", account.id)
            raise api_error(503, "queue_unavailable", "Очередь задач недоступна") from exc
    audit.record(session, user, "source_account.collect", "source_account", account.id, None, None, request)
    session.commit()
    return CollectQueued()
