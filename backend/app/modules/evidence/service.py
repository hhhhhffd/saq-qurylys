from typing import Any

from sqlalchemy import ColumnClause, cast, func, literal_column, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.models import AdPost, AppUser, ConstructionObject, Document, Evidence, Inspection, SignalCard
from app.models.enums import Recipient, Role, SignalStatus
from app.scope import TerritoryScope

_RECIPIENT_BY_ROLE = {Role.gask: Recipient.gask, Role.law_enforcement: Recipient.law_enforcement}
# Constant jsonpath: any `evidence_ids` array anywhere in the sections that contains $id.
_EVIDENCE_IN_SECTIONS: ColumnClause[Any] = literal_column("'$.**.evidence_ids[*] ? (@ == $id)'::jsonpath")
_DELIVERED = {SignalStatus.sent, SignalStatus.responded, SignalStatus.closed}


def _object_territory(session: Session, object_id: int | None) -> int | None:
    if object_id is None:
        return None
    return session.scalar(select(ConstructionObject.territory_id).where(ConstructionObject.id == object_id))


def _card_listing_evidence(session: Session, user: AppUser, scope: TerritoryScope, evidence_id: int) -> bool:
    """Whether a card delivered to the user's body lists this evidence in its sections
    (permit_checks[].evidence_ids, publications[].evidence_ids)."""
    stmt = (
        select(SignalCard.id)
        .join(ConstructionObject, ConstructionObject.id == SignalCard.object_id)
        .where(
            SignalCard.recipient == _RECIPIENT_BY_ROLE[user.role],
            SignalCard.status.in_(_DELIVERED),
            func.jsonb_path_exists(
                SignalCard.sections,
                _EVIDENCE_IN_SECTIONS,
                cast({"id": evidence_id}, JSONB),
            ),
        )
        .limit(1)
    )
    return session.scalar(scope.restrict(stmt, ConstructionObject.territory_id)) is not None


def can_access_evidence(session: Session, user: AppUser, scope: TerritoryScope, evidence: Evidence) -> bool:
    """Staff see evidence of entities in their territory. Receiving bodies see only evidence of signal
    cards that were sent to them: the card's own files and the files its sections refer to."""
    if user.role in _RECIPIENT_BY_ROLE:
        if evidence.signal_card_id is not None:
            card = session.get(SignalCard, evidence.signal_card_id)
            return (
                card is not None
                and card.recipient == _RECIPIENT_BY_ROLE[user.role]
                and card.status in _DELIVERED
                and scope.contains(_object_territory(session, card.object_id))
            )
        return _card_listing_evidence(session, user, scope, evidence.id)

    if user.role not in {Role.admin, Role.mio_officer}:
        return False
    if evidence.signal_card_id is not None:
        card = session.get(SignalCard, evidence.signal_card_id)
        return card is not None and scope.contains(_object_territory(session, card.object_id))
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
