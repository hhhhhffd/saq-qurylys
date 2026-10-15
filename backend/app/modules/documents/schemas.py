from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.models.enums import CheckSource, CheckStatus, DocType
from app.modules.evidence.schemas import EvidenceBrief
from app.schemas import ORMModel

Number = Annotated[str, StringConstraints(strip_whitespace=True, max_length=128)]
Issuer = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]


class DocumentOut(ORMModel):
    id: int
    object_id: int
    doc_type: DocType
    number: str | None
    issued_at: date | None
    issuer: str | None
    check_status: CheckStatus
    checked_at: datetime | None
    checked_by: int | None
    check_source: CheckSource | None
    note: str | None
    evidence: list[EvidenceBrief]


class DocumentUpdate(BaseModel):
    doc_type: DocType | None = None
    number: Number | None = None
    issued_at: date | None = None
    issuer: Issuer | None = None
    check_status: CheckStatus | None = None
    check_source: CheckSource | None = None
    note: str | None = None
