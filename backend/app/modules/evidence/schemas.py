from datetime import datetime

from app.models.enums import EvidenceKind, LockMode
from app.schemas import ORMModel


class EvidenceBrief(ORMModel):
    id: int
    kind: EvidenceKind
    content_type: str
    size_bytes: int
    sha256: str
    captured_at: datetime


class EvidenceOut(EvidenceBrief):
    source_url: str | None
    retention_until: datetime
    lock_mode: LockMode
    has_tsa_token: bool
    ad_post_id: int | None
    document_id: int | None
    inspection_id: int | None
    signal_card_id: int | None
    created_by: int | None
