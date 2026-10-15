from datetime import datetime

from pydantic import BaseModel

from app.modules.objects.schemas import ObjectRow


class DashboardCounts(BaseModel):
    green: int
    yellow: int
    red: int
    unscored: int
    total: int


class Dashboard(BaseModel):
    counts: DashboardCounts
    last_updated_at: datetime | None
    objects: list[ObjectRow]
