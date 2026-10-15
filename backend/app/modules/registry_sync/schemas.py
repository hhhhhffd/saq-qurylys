from datetime import datetime

from pydantic import BaseModel, Field


class SyncResult(BaseModel):
    """Outcome of one run of the registry sync; the last one is kept in `app_setting.homeportal_last_sync`."""

    ok: bool
    region_id: int
    started_at: datetime
    finished_at: datetime
    fetched: int = 0
    objects_created: int = 0
    documents_created: int = 0
    documents_updated: int = 0
    # Confirmed by the registry before, absent now: set back to `checking` for a manual check.
    documents_unconfirmed: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)


class SyncStarted(BaseModel):
    task_id: str


class SyncStatus(BaseModel):
    # Whether the scheduled daily run is on (HOMEPORTAL_SYNC_ENABLED). A run can always be started by hand.
    scheduled_enabled: bool
    last_sync: SyncResult | None
