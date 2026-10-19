from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast

from fastapi import APIRouter, File, Query, Request, Response, UploadFile
from sqlalchemy import Select, func, select

from app import audit
from app.config import get_settings
from app.csv_import import ImportResult
from app.deps import PageDep, ScopeDep, SessionDep, StaffUser
from app.errors import api_error
from app.events import object_changed, objects_changed
from app.geo import make_point
from app.models import AdPost, ConstructionObject, Developer, District, Document, Territory
from app.models.enums import DocType, Zone
from app.modules.complaints.schemas import ComplaintOut
from app.modules.developers.schemas import DeveloperOut
from app.modules.documents.schemas import DocumentOut
from app.modules.inspections.schemas import InspectionOut
from app.modules.linked_entities.schemas import LinkedEntityOut
from app.modules.objects import dossier, importer
from app.modules.objects.schemas import (
    LatestScore,
    ObjectCreate,
    ObjectDetail,
    ObjectPassport,
    ObjectRow,
    ObjectUpdate,
)
from app.modules.objects.service import (
    apply_status_rules,
    check_references,
    get_object_in_scope,
    key_status_detail,
    object_rows_stmt,
)
from app.modules.risk.engine import DocumentFact, document_statuses, legal_basis_status
from app.modules.risk.queries import latest_score_stmt
from app.modules.settings.service import load_settings
from app.schemas import Page
from app.uploads import read_csv_upload
from app.xlsx_exports import (
    MAX_EXPORT_ROWS,
    ExportColumn,
    LinkCell,
    app_origin,
    build_workbook,
    content_disposition,
    utc_datetime,
)

router = APIRouter(prefix="/objects", tags=["objects"])

_EXPORT_LABELS: dict[str, dict[str, Any]] = {
    "ru": {
        "sheet": "Объекты",
        "metadata_sheet": "Об экспорте",
        "title": "Выгрузка реестра объектов",
        "open": "Открыть",
        "columns": (
            "ID",
            "Карточка",
            "Код",
            "Наименование",
            "Адрес",
            "Территория",
            "Район",
            "Застройщик",
            "БИН",
            "Статус строительства",
            "Правовое основание",
            "Гарантия КЖК — проверка",
            "Разрешение ДСУ — проверка",
            "Последняя проверка (UTC)",
            "Балл риска",
            "Зона риска",
            "Последний расчёт (UTC)",
            "Следующая проверка (UTC)",
            "Обновлено (UTC)",
        ),
        "meta": ("Параметр", "Значение", "Сформировано (UTC)"),
        "whole_scope": "Вся территория",
        "subtree": "{name} и подчинённые территории",
        "territory_filter": "Территория",
        "territory_unavailable": "Территория вне доступной области",
        "district_filter": "Район ID",
        "zone_filter": "Зона риска",
        "query_filter": "Поиск",
        "row_count": "Строк выгружено",
        "empty_note": "Нет данных по выбранным фильтрам",
        "unknown": "Не установлено",
        "legal_basis": {
            "confirmed": "Подтверждено",
            "absent_established": "Отсутствие установлено проверкой",
            "unknown": "Не установлено",
        },
        "check": {
            "confirmed": "Подтверждено",
            "checking": "На проверке",
            "not_found": "Не найдено",
            "none": "Нет записи",
        },
        "zone": {"red": "Красная", "yellow": "Жёлтая", "green": "Зелёная"},
        "construction": {
            "not_started": "Не начато",
            "active": "Ведётся",
            "stalled": "Остановлено",
            "completed": "Завершено",
        },
        "yes": "Да",
        "no": "Нет",
        "risk_note": "Балл риска помогает расставить приоритет проверки; это не доказательство нарушения.",
        "data_note": "Пустое значение означает, что сведения не сохранены; это не подтверждает отсутствие документа.",
        "time_note": "Временные отметки приведены в UTC.",
    },
    "kk": {
        "sheet": "Объектілер",
        "metadata_sheet": "Экспорт туралы",
        "title": "Объектілер тізімінің экспорты",
        "open": "Ашу",
        "columns": (
            "ID",
            "Карточка",
            "Коды",
            "Атауы",
            "Мекенжайы",
            "Өңір",
            "Аудан",
            "Құрылыс салушы",
            "БСН",
            "Құрылыс мәртебесі",
            "Құқықтық негіз",
            "ҚЖК кепілдігі — тексеру",
            "ҮҚШ рұқсаты — тексеру",
            "Соңғы тексеру (UTC)",
            "Тәуекел балы",
            "Тәуекел аймағы",
            "Соңғы есеп (UTC)",
            "Келесі тексеру (UTC)",
            "Жаңартылған (UTC)",
        ),
        "meta": ("Параметр", "Мәні", "Қалыптастырылған (UTC)"),
        "whole_scope": "Барлық аумақ",
        "subtree": "{name} және оған бағынысты аумақтар",
        "territory_filter": "Өңір",
        "territory_unavailable": "Қолжетімді аумақтан тыс өңір",
        "district_filter": "Аудан ID",
        "zone_filter": "Тәуекел аймағы",
        "query_filter": "Іздеу",
        "row_count": "Экспортталған жол саны",
        "empty_note": "Таңдалған сүзгілер бойынша дерек жоқ",
        "unknown": "Белгісіз",
        "legal_basis": {
            "confirmed": "Расталған",
            "absent_established": "Тексеру арқылы жоқ екені анықталған",
            "unknown": "Белгісіз",
        },
        "check": {"confirmed": "Расталған", "checking": "Тексерілуде", "not_found": "Табылмады", "none": "Жазба жоқ"},
        "zone": {"red": "Қызыл", "yellow": "Сары", "green": "Жасыл"},
        "construction": {
            "not_started": "Басталмаған",
            "active": "Жүріп жатыр",
            "stalled": "Тоқтап тұр",
            "completed": "Аяқталған",
        },
        "yes": "Иә",
        "no": "Жоқ",
        "risk_note": "Тәуекел балы тексеру басымдығын көрсетеді; ол құқық бұзушылықтың дәлелі емес.",
        "data_note": "Бос мән мәлімет сақталмағанын білдіреді; құжаттың жоқ екенін дәлелдемейді.",
        "time_note": "Уақыт белгілері UTC бойынша берілген.",
    },
}


def _export_scope(session: SessionDep, user: StaffUser, labels: dict[str, Any]) -> str:
    if user.territory_id is None:
        return str(labels["whole_scope"])
    territory = session.get(Territory, user.territory_id)
    if territory is None:
        return str(labels["territory_unavailable"])
    return str(labels["subtree"]).format(name=territory.name)


def _export_origin(request: Request) -> str | None:
    settings = get_settings()
    return app_origin(
        request.headers.get("origin"),
        settings.cors_origin_list,
        referer=request.headers.get("referer"),
        request_base_url=str(request.base_url),
    )


def to_row(obj: ConstructionObject, developer_name: str | None, district_name: str | None) -> ObjectRow:
    return ObjectRow(
        id=obj.id,
        code=obj.code,
        name=obj.name,
        developer_name=developer_name,
        score=obj.score,
        zone=obj.zone,
        key_status=obj.key_status,
        key_status_detail=key_status_detail(obj),
        district_name=district_name,
        lat=obj.lat,
        lon=obj.lon,
        is_demo=obj.is_demo,
    )


def build_detail(session: SessionDep, obj: ConstructionObject) -> ObjectDetail:
    developer = session.get(Developer, obj.developer_id) if obj.developer_id else None
    district = session.get(District, obj.district_id) if obj.district_id else None
    window_start = datetime.now(UTC) - timedelta(days=load_settings(session).ad_window_days)
    ads_count = session.scalar(
        select(func.count())
        .select_from(AdPost)
        .where(
            AdPost.object_id == obj.id,
            func.coalesce(AdPost.published_at, AdPost.captured_at, AdPost.created_at) >= window_start,
        )
    )
    latest = session.scalar(latest_score_stmt(obj.id))
    gap = (
        obj.readiness_claimed_pct - obj.readiness_actual_pct
        if obj.readiness_claimed_pct is not None and obj.readiness_actual_pct is not None
        else None
    )
    return ObjectDetail(
        **ObjectPassport.model_validate(obj).model_dump(),
        district_name=district.name if district else None,
        key_status_detail=key_status_detail(obj),
        developer=DeveloperOut.model_validate(developer) if developer else None,
        documents=[DocumentOut.model_validate(item) for item in obj.documents],
        inspections=[InspectionOut.model_validate(item) for item in obj.inspections],
        complaints=[ComplaintOut.model_validate(item) for item in obj.complaints],
        linked_entities=[LinkedEntityOut.model_validate(item) for item in obj.linked_entities],
        ads_7d_count=ads_count or 0,
        readiness_gap_pp=gap,
        latest_score=LatestScore.model_validate(latest) if latest else None,
    )


@router.get("", response_model=Page[ObjectRow])
def list_objects(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    page: PageDep,
    zone: Annotated[Zone | None, Query()] = None,
    district_id: Annotated[int | None, Query()] = None,
    territory_id: Annotated[int | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> Page[ObjectRow]:
    stmt = object_rows_stmt(scope, zone=zone, district_id=district_id, territory_id=territory_id, q=q)
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = session.execute(
        stmt.order_by(ConstructionObject.score.desc().nulls_last(), ConstructionObject.id)
        .limit(page.limit)
        .offset(page.offset)
    )
    return Page(
        items=[to_row(obj, developer_name, district_name) for obj, developer_name, district_name in rows], total=total
    )


@router.get("/export.xlsx")
def export_objects(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    request: Request,
    zone: Annotated[Zone | None, Query()] = None,
    district_id: Annotated[int | None, Query()] = None,
    territory_id: Annotated[int | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> Response:
    """Export the same scoped, filtered object registry as the list, without page limits."""
    labels = _EXPORT_LABELS.get(user.locale.value, _EXPORT_LABELS["ru"])
    generated_at = datetime.now(UTC)
    stmt = cast(
        Select[ConstructionObject, str | None, str | None, str, str | None],
        object_rows_stmt(scope, zone=zone, district_id=district_id, territory_id=territory_id, q=q).add_columns(
            Territory.name, Developer.bin
        ),
    ).join(Territory, Territory.id == ConstructionObject.territory_id)
    rows = session.execute(
        stmt.order_by(ConstructionObject.score.desc().nulls_last(), ConstructionObject.id).limit(MAX_EXPORT_ROWS + 1)
    ).all()
    if len(rows) > MAX_EXPORT_ROWS:
        raise api_error(413, "too_many_export_rows", "Выгрузка содержит больше 10 000 строк; сузьте фильтры")

    object_ids = [row[0].id for row in rows]
    facts_by_object: dict[int, list[DocumentFact]] = {object_id: [] for object_id in object_ids}
    checked_at_by_object: dict[int, datetime] = {}
    if object_ids:
        document_rows = session.execute(
            select(
                Document.object_id,
                Document.doc_type,
                Document.check_status,
                func.min(Document.id),
                func.max(Document.checked_at),
            )
            .where(
                Document.object_id.in_(object_ids),
                Document.doc_type.in_((DocType.guarantee, DocType.dsu_permit)),
            )
            .group_by(Document.object_id, Document.doc_type, Document.check_status)
        )
        for object_id, doc_type, check_status, representative_id, checked_at in document_rows:
            facts_by_object[object_id].append(
                DocumentFact(id=representative_id, doc_type=doc_type, check_status=check_status)
            )
            if checked_at is not None and (
                object_id not in checked_at_by_object or checked_at > checked_at_by_object[object_id]
            ):
                checked_at_by_object[object_id] = checked_at

    origin = _export_origin(request)
    values = []
    for obj, developer_name, district_name, territory_name, developer_bin in rows:
        facts = facts_by_object[obj.id]
        check_statuses = document_statuses(facts)
        link = LinkCell(str(labels["open"]), f"{origin}/objects/{obj.id}") if origin else f"/objects/{obj.id}"
        values.append(
            (
                obj.id,
                link,
                obj.code,
                obj.name,
                obj.address,
                territory_name,
                district_name,
                developer_name,
                developer_bin,
                labels["construction"].get(obj.construction_status.value, labels["unknown"]),
                labels["legal_basis"][legal_basis_status(facts).value],
                labels["check"][check_statuses[DocType.guarantee.value]],
                labels["check"][check_statuses[DocType.dsu_permit.value]],
                utc_datetime(checked_at_by_object.get(obj.id)),
                obj.score,
                labels["zone"].get(obj.zone.value, labels["unknown"]) if obj.zone else labels["unknown"],
                utc_datetime(obj.last_scored_at),
                utc_datetime(obj.next_check_at),
                utc_datetime(obj.updated_at),
            )
        )

    filters: list[tuple[str, Any]] = []
    if zone is not None:
        filters.append((str(labels["zone_filter"]), labels["zone"].get(zone.value, zone.value)))
    if district_id is not None:
        filters.append((str(labels["district_filter"]), district_id))
    if territory_id is not None:
        territory = session.get(Territory, territory_id) if scope.contains(territory_id) else None
        territory_value = territory.name if territory else labels["territory_unavailable"]
        filters.append((str(labels["territory_filter"]), territory_value))
    if q:
        filters.append((str(labels["query_filter"]), q))
    metadata = [
        (
            "Территориальная область" if user.locale.value == "ru" else "Аумақтық қамту",
            _export_scope(session, user, labels),
        ),
        (str(labels["row_count"]), len(rows)),
        *filters,
        ("Примечание о риске" if user.locale.value == "ru" else "Тәуекел туралы ескерту", labels["risk_note"]),
        ("Примечание о данных" if user.locale.value == "ru" else "Деректер туралы ескерту", labels["data_note"]),
        ("Время" if user.locale.value == "ru" else "Уақыт", labels["time_note"]),
    ]
    if not rows:
        metadata.append(
            (
                "Результат" if user.locale.value == "ru" else "Нәтиже",
                labels["empty_note"],
            )
        )
    workbook = build_workbook(
        sheet_name=str(labels["sheet"]),
        metadata_sheet_name=str(labels["metadata_sheet"]),
        columns=[
            ExportColumn(title, width, "dd.mm.yyyy hh:mm" if "UTC" in title else None)
            for title, width in zip(
                labels["columns"],
                (10, 12, 16, 34, 34, 24, 22, 28, 16, 22, 28, 24, 24, 22, 14, 16, 22, 22, 22),
                strict=True,
            )
        ],
        rows=values,
        metadata=metadata,
        export_title=str(labels["title"]),
        generated_at=generated_at,
        generated_at_label=str(labels["meta"][2]),
        metadata_headers=(str(labels["meta"][0]), str(labels["meta"][1])),
    )
    audit.record(
        session,
        user,
        "objects.export",
        "object_export",
        None,
        None,
        {
            "zone": zone.value if zone else None,
            "district_id": district_id,
            "territory_id": territory_id,
            "q": q,
            "row_count": len(rows),
        },
        request,
    )
    session.commit()
    filename = f"SAQ_ЖК_{generated_at.date().isoformat()}.xlsx"
    fallback = f"SAQ_objects_{generated_at.date().isoformat()}.xlsx"
    return Response(
        content=workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": content_disposition(filename, fallback), "Cache-Control": "no-store"},
    )


@router.post("", response_model=ObjectDetail, status_code=201)
def create_object(
    body: ObjectCreate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> ObjectDetail:
    check_references(session, scope, body.territory_id, body.district_id, body.developer_id)
    data = body.model_dump(exclude={"lat", "lon"})
    obj = ConstructionObject(**data, location=make_point(body.lat, body.lon))
    apply_status_rules(session, obj)
    session.add(obj)
    session.flush()
    session.refresh(obj)
    audit.record(session, user, "object.create", "object", obj.id, None, audit.snapshot(obj), request)
    detail = build_detail(session, obj)
    session.commit()
    object_changed(obj.id)
    return detail


@router.post("/import", response_model=ImportResult)
def import_objects(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    request: Request,
    file: Annotated[UploadFile, File()],
) -> ImportResult:
    result, changed_ids = importer.import_objects(session, scope, user, read_csv_upload(file), request)
    session.commit()
    objects_changed(changed_ids)
    return result


@router.get("/{object_id}", response_model=ObjectDetail)
def get_object(object_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep) -> ObjectDetail:
    return build_detail(session, get_object_in_scope(session, scope, object_id))


@router.get("/{object_id}/dossier.pdf")
def object_dossier(object_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request) -> Response:
    obj = get_object_in_scope(session, scope, object_id)
    document = dossier.render_pdf(session, obj, user, user.locale.value)
    audit.record(session, user, "object.dossier", "object", obj.id, None, None, request)
    session.commit()
    return Response(
        content=document,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{obj.code}-dossier.pdf"', "Cache-Control": "no-store"},
    )


@router.patch("/{object_id}", response_model=ObjectDetail)
def update_object(
    object_id: int, body: ObjectUpdate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> ObjectDetail:
    obj = get_object_in_scope(session, scope, object_id)
    changes = body.model_dump(exclude_unset=True)
    check_references(
        session,
        scope,
        changes.get("territory_id", obj.territory_id),
        changes.get("district_id", obj.district_id),
        changes.get("developer_id", obj.developer_id),
    )
    before = audit.snapshot(obj)
    lat, lon = changes.pop("lat", None), changes.pop("lon", None)
    if "lat" in body.model_fields_set:
        obj.location = make_point(lat, lon)
    for field, value in changes.items():
        setattr(obj, field, value)
    if "construction_status" in changes or "stalled_since" in changes:
        apply_status_rules(session, obj)
    session.flush()
    session.refresh(obj)
    audit.record(session, user, "object.update", "object", obj.id, before, audit.snapshot(obj), request)
    detail = build_detail(session, obj)
    session.commit()
    object_changed(obj.id)
    return detail
