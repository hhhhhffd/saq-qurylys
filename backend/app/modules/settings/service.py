from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSetting
from app.models.enums import Recipient


def _empty_recipients() -> dict[Recipient, list[str]]:
    return {recipient: [] for recipient in Recipient}


class AppSettings(BaseModel):
    """Typed application settings. Defaults here are the defaults from SPEC section 3."""

    model_config = ConfigDict(extra="forbid")

    review_days: int = Field(default=5, ge=1, le=60)
    ad_window_days: int = Field(default=30, ge=1, le=365)
    readiness_gap_pp: int = Field(default=20, ge=1, le=100)
    # R6: a delay of at least this many days (forecast over plan, or the plan passed long ago) counts as significant.
    significant_delay_days: int = Field(default=90, ge=1, le=3650)
    # Zones by score (SPEC 6.2): green below `zone_yellow_min`, red from `zone_red_min` when R1 and R2 both fired.
    zone_yellow_min: int = Field(default=25, ge=1, le=100)
    zone_red_min: int = Field(default=60, ge=1, le=100)
    # No longer used by the risk model (R4 needs a verified collective complaint); kept for stored settings.
    complaints_threshold: int = Field(default=3, ge=1, le=1000)
    stalled_days: int = Field(default=30, ge=1, le=3650)
    recheck_after_days: int = Field(default=3, ge=1, le=365)
    link_confidence_threshold: float = Field(default=0.8, ge=0, le=1)
    green_interval_days: int = Field(default=30, ge=1, le=365)
    yellow_interval_days: int = Field(default=7, ge=1, le=365)
    # Addresses of the receiving bodies for the signal card e-mail (SPEC 7.2).
    recipient_emails: dict[Recipient, list[str]] = Field(default_factory=_empty_recipients)

    @field_validator("recipient_emails")
    @classmethod
    def _check_emails(cls, value: dict[Recipient, list[str]]) -> dict[Recipient, list[str]]:
        for emails in value.values():
            for email in emails:
                if "@" not in email or any(char.isspace() for char in email):
                    raise ValueError(f"invalid e-mail address: {email!r}")
        return value


def load_settings(session: Session) -> AppSettings:
    """Stored values merged over the defaults."""
    stored = {row.key: row.value for row in session.scalars(select(AppSetting))}
    return AppSettings.model_validate({key: value for key, value in stored.items() if key in AppSettings.model_fields})


def get_setting(session: Session, key: str) -> Any:
    if key not in AppSettings.model_fields:
        raise KeyError(f"unknown setting: {key}")
    return getattr(load_settings(session), key)


def save_settings(session: Session, changes: dict[str, Any]) -> AppSettings:
    """Upsert the given keys (already validated by AppSettings) and return the full settings."""
    for key, value in changes.items():
        row = session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    session.flush()
    return load_settings(session)


def ensure_defaults(session: Session) -> None:
    """Insert the defaults for keys that are not stored yet (used by the seed)."""
    defaults = AppSettings().model_dump(mode="json")
    existing = set(session.scalars(select(AppSetting.key)))
    for key, value in defaults.items():
        if key not in existing:
            session.add(AppSetting(key=key, value=value))
    session.flush()
