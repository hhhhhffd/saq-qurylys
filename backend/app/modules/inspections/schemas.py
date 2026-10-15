from datetime import date

from app.modules.evidence.schemas import EvidenceBrief
from app.schemas import ORMModel


class InspectionOut(ORMModel):
    id: int
    object_id: int
    inspected_at: date
    readiness_pct: int
    lat: float | None
    lon: float | None
    inspector_id: int | None
    note: str | None
    evidence: list[EvidenceBrief]
