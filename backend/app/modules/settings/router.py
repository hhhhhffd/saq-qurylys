from typing import Annotated

from fastapi import APIRouter, Body, Request
from sqlalchemy import select

from app import audit
from app.deps import GlobalAdmin, SessionDep, StaffUser
from app.errors import api_error
from app.events import objects_changed
from app.models import ConstructionObject
from app.modules.settings.service import AppSettings, load_settings, save_settings

router = APIRouter(prefix="/settings", tags=["settings"])

# Settings the risk calculation reads: a change of any of them rescores every object.
SCORING_KEYS = (
    "ad_window_days",
    "readiness_gap_pp",
    "stalled_days",
    "significant_delay_days",
    "zone_yellow_min",
    "zone_red_min",
)


@router.get("", response_model=AppSettings)
def read_settings(session: SessionDep, user: StaffUser) -> AppSettings:
    return load_settings(session)


@router.put("", response_model=AppSettings)
def update_settings(
    body: Annotated[AppSettings, Body()], session: SessionDep, user: GlobalAdmin, request: Request
) -> AppSettings:
    """Partial update: only keys present in the request body are changed."""
    before = load_settings(session)
    changes = body.model_dump(mode="json", include=body.model_fields_set)
    merged = {**before.model_dump(mode="json"), **changes}
    if merged["zone_yellow_min"] >= merged["zone_red_min"]:
        raise api_error(422, "invalid_zone_thresholds", "Порог жёлтой зоны должен быть ниже порога красной зоны")
    after = save_settings(session, changes)
    audit.record(
        session,
        user,
        "settings.update",
        "setting",
        None,
        before.model_dump(mode="json", include=set(changes)),
        after.model_dump(mode="json", include=set(changes)),
        request,
    )
    # Settings are country-wide and only a global admin may change them, so "every object" is meant literally.
    rescore = [key for key in SCORING_KEYS if getattr(before, key) != getattr(after, key)]
    object_ids = list(session.scalars(select(ConstructionObject.id))) if rescore else []
    session.commit()
    objects_changed(object_ids)
    return after
