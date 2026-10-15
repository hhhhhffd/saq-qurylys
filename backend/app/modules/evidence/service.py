from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AdPost, AppUser, ConstructionObject, Document, Evidence, Inspection, SignalCard
from app.models.enums import Recipient, Role, SignalStatus
from app.scope import TerritoryScope

_RECIPIENT_BY_ROLE = {Role.gask: Recipient.gask, Role.law_enforcement: Recipient.law_enforcement}
_DELIVERED = {SignalStatus.sent, SignalStatus.responded, SignalStatus.closed}


def _object_territory(session: Session, object_id: int | None) -> int | None:
    if object_id is None:
        return None
    return session.scalar(select(ConstructionObject.territory_id).where(ConstructionObject.id == object_id))


def can_access_evidence(session: Session, user: AppUser, scope: TerritoryScope, evidence: Evidence) -> bool:
    """Staff see evidence of entities in their territory; receiving bodies only see evidence of
    signal cards that were sent to them."""
    if evidence.signal_card_id is not None:
        card = session.get(SignalCard, evidence.signal_card_id)
        if card is None or not scope.contains(_object_territory(session, card.object_id)):
            return False
        if user.role in _RECIPIENT_BY_ROLE:
            return card.recipient == _RECIPIENT_BY_ROLE[user.role] and card.status in _DELIVERED
        return user.role in {Role.admin, Role.mio_officer}

    if user.role not in {Role.admin, Role.mio_officer}:
        return False
    if evidence.document_id is not None:
        object_id = session.scalar(select(Document.object_id).where(Document.id == evidence.document_id))
        return scope.contains(_object_territory(session, object_id))
    if evidence.inspection_id is not None:
        object_id = session.scalar(select(Inspection.object_id).where(Inspection.id == evidence.inspection_id))
        return scope.contains(_object_territory(session, object_id))
    if evidence.ad_post_id is not None:
        territory_id, object_id = session.execute(
            select(AdPost.territory_id, AdPost.object_id).where(AdPost.id == evidence.ad_post_id)
        ).one()
        return scope.contains(territory_id if territory_id is not None else _object_territory(session, object_id))
    return False
