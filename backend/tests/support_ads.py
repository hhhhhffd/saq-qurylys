"""Builders for the ads and NLP tests (not a test module: nothing here is collected)."""

import itertools

from sqlalchemy.orm import Session

from app.models import AdPost, Territory
from app.models.enums import Platform

_ids = itertools.count(1)


def add_ad(
    db: Session, territory: Territory | None, text: str | None = "Квартиры в рассрочку", **fields: object
) -> AdPost:
    """A stored publication with a unique external id; `fields` override any column."""
    number = next(_ids)
    values: dict[str, object] = {
        "platform": Platform.instagram,
        "external_id": f"test-ad-{number}",
        "territory_id": territory.id if territory else None,
        "text": text,
    }
    ad = AdPost(**{**values, **fields})
    db.add(ad)
    db.flush()
    db.refresh(ad)
    return ad
