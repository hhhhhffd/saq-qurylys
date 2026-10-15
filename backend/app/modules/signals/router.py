import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import CurrentUser, PageDep, ScopeDep, SessionDep, require_roles
from app.models import AppUser, SignalCard
from app.models.enums import Recipient, Role, SignalOrigin, SignalStatus
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signals", tags=["signals"])

# Only an officer of the MIO prepares, sends and closes cards; admins read them (SPEC section 4).
OfficerUser = Annotated[AppUser, Depends(require_roles(Role.mio_officer))]
ReceivingUser = Annotated[AppUser, Depends(require_roles(Role.gask, Role.law_enforcement))]


def _queue_email(
    session: Session, background: BackgroundTasks, view: service.CardView, user: AppUser, recipient: Recipient
) -> None:
    """E-mail the PDF to the receiving body's addresses after the dispatch is committed. A mail or rendering
    problem is logged and never undoes the dispatch."""
    emails = load_settings(session).recipient_emails.get(recipient, [])
    if not (mail.smtp_enabled() and emails):
        return
    number = view.card.number
    try:
        document = pdf.render_pdf(session, view, user.locale.value)
    except Exception:
        logger.exception("Could not render the PDF of %s for e-mail", number)
        return
    background.add_task(
        mail.send_email,
        emails,
        f"{number}: {view.object_name}",
        f"Сигнальная карточка {number} направлена на рассмотрение. Подробности во вложении.",
        (f"{number}.pdf", document, "application/pdf"),
    )


@router.get("", response_model=Page[SignalRow])
def list_signals(
    session: SessionDep,
    user: CurrentUser,
    scope: ScopeDep,
    page: PageDep,
    status: Annotated[SignalStatus | None, Query()] = None,
    object_id: Annotated[int | None, Query()] = None,
) -> Page[SignalRow]:
    stmt = service.card_stmt(user, scope)
    if status is not None:
        stmt = stmt.where(SignalCard.status == status)
    if object_id is not None:
        stmt = stmt.where(SignalCard.object_id == object_id)
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = session.execute(
        stmt.order_by(SignalCard.created_at.desc(), SignalCard.id.desc()).limit(page.limit).offset(page.offset)
    )
    now = datetime.now(UTC)
    items = [
        service.to_row(service.CardView(card=card, object_name=name, zone=zone, timezone=timezone), now)
        for card, name, zone, timezone in rows
    ]
    return Page(items=items, total=total)


@router.post("", response_model=SignalDetail, status_code=201)
def create_signal(
    body: CreateSignal, session: SessionDep, user: OfficerUser, scope: ScopeDep, request: Request
) -> SignalDetail:
    obj = get_object_in_scope(session, scope, body.object_id)
    card = service.create_card(session, obj, SignalOrigin.manual, user, request)
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
    detail = service.to_detail(session, user, view)
    session.commit()
    _queue_email(session, background, view, user, body.recipient)
    return detail


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
    signal_id: int, body: ResponseBody, session: SessionDep, user: ReceivingUser, scope: ScopeDep, request: Request
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
