import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app import audit, storage
from app.config import get_settings
from app.deps import CurrentUser, PageDep, ScopeDep, SessionDep, require_roles
from app.errors import api_error
from app.models import AppUser, SignalCard, Territory
from app.models.enums import EvidenceKind, Recipient, Role, SignalStatus, Zone
from app.modules.objects.service import get_object_in_scope
from app.modules.settings.service import load_settings
from app.modules.signals import mail, pdf, service
from app.modules.signals.schemas import (
    ConfirmAndSend,
    CreateSignal,
    ResponseBody,
    ReturnBody,
    SignalDetail,
    SignalPatch,
    SignalRow,
)
from app.schemas import Page
from app.storage import EvidenceLink
from app.xlsx_exports import (
    MAX_EXPORT_ROWS,
    ExportColumn,
    LinkCell,
    app_origin,
    build_workbook,
    content_disposition,
    utc_datetime,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signals", tags=["signals"])

_EXPORT_LABELS: dict[str, dict[str, Any]] = {
    "ru": {
        "sheet": "Сигналы",
        "metadata_sheet": "Об экспорте",
        "title": "Выгрузка сигнальных карточек",
        "open": "Открыть",
        "columns": (
            "ID",
            "Карточка",
            "Номер карточки",
            "ЖК",
            "Зона риска",
            "Статус карточки",
            "Получатель",
            "Создана (UTC)",
            "Внутреннее направление (UTC)",
            "Срок ответа",
            "Просрочена на дату формирования",
            "Дата внесения ответа (UTC)",
        ),
        "meta": ("Параметр", "Значение", "Сформировано (UTC)"),
        "whole_scope": "Вся территория",
        "subtree": "{name} и подчинённые территории",
        "territory_unavailable": "Территория вне доступной области",
        "status_filter": "Статус карточки",
        "object_filter": "ID объекта",
        "row_count": "Строк выгружено",
        "empty_note": "Нет данных по выбранным фильтрам",
        "zone": {"red": "Красная", "yellow": "Жёлтая", "green": "Зелёная"},
        "zone_none": "Без оценки",
        "status": {
            "requires_confirmation": "Требует подтверждения",
            "returned": "Возвращена на доработку",
            "sent": "Направлена",
            "responded": "Ответ внесён",
            "closed": "Закрыта",
        },
        "recipient": {"mio": "МИО", "gask": "ГАСК", "law_enforcement": "Правоохранительные органы"},
        "yes": "Да",
        "no": "Нет",
        "time_note": (
            "Временные отметки приведены в UTC; срок ответа — календарная дата в часовом поясе территории объекта."
        ),
        "dispatch_note": "«Направлена» отражает запись sent_at в системе и не подтверждает доставку адресату.",
        "overdue_note": "Просрочка рассчитана на момент формирования по сроку ответа и статусу карточки.",
        "risk_note": "Зона риска помогает расставлять приоритеты проверки и сама по себе не доказывает нарушение.",
    },
    "kk": {
        "sheet": "Сигналдар",
        "metadata_sheet": "Экспорт туралы",
        "title": "Сигнал карточкаларының экспорты",
        "open": "Ашу",
        "columns": (
            "ID",
            "Карточка",
            "Карточка нөмірі",
            "Тұрғын үй кешені",
            "Тәуекел аймағы",
            "Карточка мәртебесі",
            "Алушы",
            "Құрылған (UTC)",
            "Ішкі жіберілген (UTC)",
            "Жауап мерзімі",
            "Қалыптастыру кезіндегі мерзімі өткен",
            "Жауап енгізілген (UTC)",
        ),
        "meta": ("Параметр", "Мәні", "Қалыптастырылған (UTC)"),
        "whole_scope": "Барлық аумақ",
        "subtree": "{name} және оған бағынысты аумақтар",
        "territory_unavailable": "Қолжетімді аумақтан тыс өңір",
        "status_filter": "Карточка мәртебесі",
        "object_filter": "Объект ID",
        "row_count": "Экспортталған жол саны",
        "empty_note": "Таңдалған сүзгілер бойынша дерек жоқ",
        "zone": {"red": "Қызыл", "yellow": "Сары", "green": "Жасыл"},
        "zone_none": "Бағаланбаған",
        "status": {
            "requires_confirmation": "Растауды күтуде",
            "returned": "Толықтыруға қайтарылды",
            "sent": "Жіберілді",
            "responded": "Жауап енгізілді",
            "closed": "Жабылды",
        },
        "recipient": {"mio": "ЖАО", "gask": "МҚБК", "law_enforcement": "Құқық қорғау органдары"},
        "yes": "Иә",
        "no": "Жоқ",
        "time_note": (
            "Уақыт белгілері UTC бойынша берілген; жауап мерзімі объект аумағының уақыт белдеуіндегі күнтізбелік күн."
        ),
        "dispatch_note": "«Жіберілді» жүйедегі sent_at жазбасын білдіреді және адресатқа жеткізілгенін растамайды.",
        "overdue_note": "Мерзімнің өтуі қалыптастыру сәтіндегі жауап мерзімі мен карточка мәртебесі бойынша есептелді.",
        "risk_note": "Тәуекел аймағы тексеру басымдығын көрсетеді, бірақ құқық бұзушылықты өздігінен дәлелдемейді.",
    },
}

# Only an officer of the MIO prepares, sends and closes cards; admins read them (SPEC section 4).
OfficerUser = Annotated[AppUser, Depends(require_roles(Role.mio_officer))]
# The addressee answers: a receiving body, or a mio officer when the card is addressed to the MIO itself.
ResponderUser = Annotated[AppUser, Depends(require_roles(Role.gask, Role.law_enforcement, Role.mio_officer))]


def _archive_and_mail(
    session: Session, background: BackgroundTasks, view: service.CardView, user: AppUser, recipient: Recipient
) -> None:
    """After the dispatch is committed: render the PDF of the card as sent, keep it as immutable evidence
    (OPEN_QUESTIONS #16) and mail it to the receiving body's addresses. None of this can undo the dispatch:
    a failure is logged and, when the copy could not be archived, reported to the sender as a notification."""
    card_id, number, locale = view.card.id, view.card.number, user.locale.value
    sender_id = user.id
    document: bytes | None = None
    try:
        document = pdf.render_pdf(session, view, locale)
        storage.put_evidence(
            session,
            document,
            EvidenceKind.pdf,
            "application/pdf",
            link=EvidenceLink(signal_card_id=card_id),
            created_by=sender_id,
        )
        session.commit()
    except Exception:
        logger.exception("Could not archive the PDF of %s", number)
        session.rollback()
        try:
            service.notify_archive_failed(session, view, user)
            session.commit()
        except Exception:
            # The dispatch is committed and stands; being unable to tell the sender is only logged.
            logger.exception("Could not notify the sender that the PDF of %s was not archived", number)
            session.rollback()
    emails = load_settings(session).recipient_emails.get(recipient, [])
    if document is None or not (mail.smtp_enabled() and emails):
        return
    background.add_task(
        mail.send_email,
        emails,
        f"{number}: {view.object_name}",
        f"Сигнальная карточка {number} направлена на рассмотрение. Подробности во вложении.",
        (f"{number}.pdf", document, "application/pdf"),
    )


def _filtered_card_stmt(
    user: AppUser, scope: ScopeDep, status: SignalStatus | None, object_id: int | None
) -> Select[SignalCard, str, Zone | None, str, bool]:
    stmt = service.card_stmt(user, scope)
    if status is not None:
        stmt = stmt.where(SignalCard.status == status)
    if object_id is not None:
        stmt = stmt.where(SignalCard.object_id == object_id)
    return stmt


def _export_scope(session: SessionDep, user: AppUser, labels: dict[str, Any]) -> str:
    if user.territory_id is None:
        return str(labels["whole_scope"])
    territory = session.get(Territory, user.territory_id)
    if territory is None:
        return str(labels["territory_unavailable"])
    return str(labels["subtree"]).format(name=territory.name)


@router.get("", response_model=Page[SignalRow])
def list_signals(
    session: SessionDep,
    user: CurrentUser,
    scope: ScopeDep,
    page: PageDep,
    status: Annotated[SignalStatus | None, Query()] = None,
    object_id: Annotated[int | None, Query()] = None,
) -> Page[SignalRow]:
    stmt = _filtered_card_stmt(user, scope, status, object_id)
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = session.execute(
        stmt.order_by(SignalCard.created_at.desc(), SignalCard.id.desc()).limit(page.limit).offset(page.offset)
    )
    now = datetime.now(UTC)
    items = [
        service.to_row(
            service.CardView(card=card, object_name=name, zone=zone, timezone=timezone, is_demo=is_demo), now
        )
        for card, name, zone, timezone, is_demo in rows
    ]
    return Page(items=items, total=total)


@router.get("/export.xlsx")
def export_signals(
    session: SessionDep,
    user: CurrentUser,
    scope: ScopeDep,
    request: Request,
    status: Annotated[SignalStatus | None, Query()] = None,
    object_id: Annotated[int | None, Query()] = None,
) -> Response:
    """Export the same filtered and visible signal cards as the list, without page limits."""
    labels = _EXPORT_LABELS.get(user.locale.value, _EXPORT_LABELS["ru"])
    generated_at = datetime.now(UTC)
    stmt = _filtered_card_stmt(user, scope, status, object_id)
    rows = session.execute(
        stmt.order_by(SignalCard.created_at.desc(), SignalCard.id.desc()).limit(MAX_EXPORT_ROWS + 1)
    ).all()
    if len(rows) > MAX_EXPORT_ROWS:
        raise api_error(413, "too_many_export_rows", "Выгрузка содержит больше 10 000 строк; сузьте фильтры")

    origin = app_origin(
        request.headers.get("origin"),
        get_settings().cors_origin_list,
        referer=request.headers.get("referer"),
        request_base_url=str(request.base_url),
    )
    export_rows = []
    for card, object_name, zone, timezone, is_demo in rows:
        view = service.CardView(card=card, object_name=object_name, zone=zone, timezone=timezone, is_demo=is_demo)
        listed = service.to_row(view, generated_at)
        link = LinkCell(str(labels["open"]), f"{origin}/signals/{card.id}") if origin else f"/signals/{card.id}"
        export_rows.append(
            (
                card.id,
                link,
                card.number,
                object_name,
                labels["zone"].get(zone.value, zone.value) if zone else labels["zone_none"],
                labels["status"][card.status.value],
                labels["recipient"].get(card.recipient.value, card.recipient.value) if card.recipient else None,
                utc_datetime(card.created_at),
                utc_datetime(card.sent_at),
                card.due_date,
                labels["yes"] if listed.is_overdue else labels["no"],
                utc_datetime(card.response_at),
            )
        )

    metadata: list[tuple[str, object]] = [
        (
            "Территориальная область" if user.locale.value == "ru" else "Аумақтық қамту",
            _export_scope(session, user, labels),
        ),
        (str(labels["row_count"]), len(rows)),
    ]
    if status is not None:
        metadata.append((str(labels["status_filter"]), labels["status"][status.value]))
    if object_id is not None:
        metadata.append((str(labels["object_filter"]), object_id))
    metadata.extend(
        (
            (
                "Примечание о направлении" if user.locale.value == "ru" else "Жіберу туралы ескерту",
                labels["dispatch_note"],
            ),
            (
                "Примечание о сроке" if user.locale.value == "ru" else "Мерзім туралы ескерту",
                labels["overdue_note"],
            ),
            ("Время" if user.locale.value == "ru" else "Уақыт", labels["time_note"]),
            (
                "Примечание о риске" if user.locale.value == "ru" else "Тәуекел туралы ескерту",
                labels["risk_note"],
            ),
        )
    )
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
            ExportColumn(title, width, fmt)
            for title, width, fmt in zip(
                labels["columns"],
                (10, 12, 21, 34, 18, 26, 28, 22, 22, 18, 26, 24),
                (
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "dd.mm.yyyy hh:mm",
                    "dd.mm.yyyy hh:mm",
                    "dd.mm.yyyy",
                    None,
                    "dd.mm.yyyy hh:mm",
                ),
                strict=True,
            )
        ],
        rows=export_rows,
        metadata=metadata,
        export_title=str(labels["title"]),
        generated_at=generated_at,
        generated_at_label=str(labels["meta"][2]),
        metadata_headers=(str(labels["meta"][0]), str(labels["meta"][1])),
    )
    audit.record(
        session,
        user,
        "signals.export",
        "signal_export",
        None,
        None,
        {"status": status.value if status else None, "object_id": object_id, "row_count": len(rows)},
        request,
    )
    session.commit()
    filename = f"SAQ_Сигналы_{generated_at.date().isoformat()}.xlsx"
    fallback = f"SAQ_signals_{generated_at.date().isoformat()}.xlsx"
    return Response(
        content=workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": content_disposition(filename, fallback), "Cache-Control": "no-store"},
    )


@router.post("", response_model=SignalDetail, status_code=201)
def create_signal(
    body: CreateSignal, session: SessionDep, user: OfficerUser, scope: ScopeDep, request: Request
) -> SignalDetail:
    obj = get_object_in_scope(session, scope, body.object_id)
    card = service.create_manual_card(session, obj, user, request)
    detail = service.to_detail(session, user, service.get_card_view(session, user, scope, card.id))
    session.commit()
    return detail


@router.get("/{signal_id}", response_model=SignalDetail)
def get_signal(signal_id: int, session: SessionDep, user: CurrentUser, scope: ScopeDep) -> SignalDetail:
    return service.to_detail(session, user, service.get_card_view(session, user, scope, signal_id))


@router.patch("/{signal_id}", response_model=SignalDetail)
def update_signal(
    signal_id: int, body: SignalPatch, session: SessionDep, user: OfficerUser, scope: ScopeDep, request: Request
) -> SignalDetail:
    view = service.get_card_view(session, user, scope, signal_id, lock=True)
    service.update_card(session, view.card, body, user, request)
    detail = service.to_detail(session, user, view)
    session.commit()
    return detail


@router.post("/{signal_id}/confirm-and-send", response_model=SignalDetail)
def confirm_and_send(
    signal_id: int,
    body: ConfirmAndSend,
    session: SessionDep,
    user: OfficerUser,
    scope: ScopeDep,
    request: Request,
    background: BackgroundTasks,
) -> SignalDetail:
    """The only way a card leaves the system: a person with the MIO officer role confirms the dispatch."""
    view = service.get_card_view(session, user, scope, signal_id, lock=True)
    service.confirm_and_send(session, view, user, body.recipient, request)
    session.commit()
    _archive_and_mail(session, background, view, user, body.recipient)
    return service.to_detail(session, user, view)


@router.post("/{signal_id}/return", response_model=SignalDetail)
def return_signal(
    signal_id: int, body: ReturnBody, session: SessionDep, user: OfficerUser, scope: ScopeDep, request: Request
) -> SignalDetail:
    view = service.get_card_view(session, user, scope, signal_id, lock=True)
    service.return_card(session, view, user, body.comment, request)
    detail = service.to_detail(session, user, view)
    session.commit()
    return detail


@router.post("/{signal_id}/response", response_model=SignalDetail)
def respond_to_signal(
    signal_id: int, body: ResponseBody, session: SessionDep, user: ResponderUser, scope: ScopeDep, request: Request
) -> SignalDetail:
    view = service.get_card_view(session, user, scope, signal_id, lock=True)
    service.respond(session, view, user, body.response_text, request)
    detail = service.to_detail(session, user, view)
    session.commit()
    return detail


@router.post("/{signal_id}/close", response_model=SignalDetail)
def close_signal(
    signal_id: int, session: SessionDep, user: OfficerUser, scope: ScopeDep, request: Request
) -> SignalDetail:
    view = service.get_card_view(session, user, scope, signal_id, lock=True)
    service.close_card(session, view, user, request)
    detail = service.to_detail(session, user, view)
    session.commit()
    return detail


@router.get("/{signal_id}/pdf")
def signal_pdf(signal_id: int, session: SessionDep, user: CurrentUser, scope: ScopeDep) -> Response:
    view = service.get_card_view(session, user, scope, signal_id)
    document = pdf.render_pdf(session, view, user.locale.value)
    return Response(
        content=document,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{view.card.number}.pdf"', "Cache-Control": "no-store"},
    )
