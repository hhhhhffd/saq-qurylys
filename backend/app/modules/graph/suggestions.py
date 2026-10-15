"""Candidate sources (SPEC 10.3): accounts that publications link to, but nobody watches yet."""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AdPost, ConstructionObject, DismissedSourceSuggestion, SourceAccount
from app.models.enums import Platform, Zone
from app.modules.graph.schemas import SourceSuggestion
from app.modules.graph.service import SOCIAL_PLATFORMS, ad_recency, ad_window_start, normalize_account
from app.scope import TerritoryScope

MAX_SUGGESTIONS = 50
_PROFILE_URL = {
    Platform.instagram: "https://www.instagram.com/{}/",
    Platform.telegram: "https://t.me/{}",
    Platform.tiktok: "https://www.tiktok.com/@{}",
}
# Posts that point at objects in these zones make an account more urgent.
_ZONE_SEVERITY = {Zone.red: 2, Zone.yellow: 1}


@dataclass
class _Mentions:
    posts: int = 0
    object_ids: set[int] = field(default_factory=set)
    severity: int = 0
    last_seen_at: datetime | None = None


def list_suggestions(session: Session, scope: TerritoryScope) -> list[SourceSuggestion]:
    """Accounts named in the links of recent publications, most mentioned first, then those whose posts point at
    yellow or red objects, then the most recently seen."""
    posts = session.execute(
        scope.restrict(
            select(AdPost.object_id, AdPost.links, ad_recency, ConstructionObject.zone).outerjoin(
                ConstructionObject, ConstructionObject.id == AdPost.object_id
            ),
            AdPost.territory_id,
        ).where(ad_recency >= ad_window_start(session), func.cardinality(AdPost.links) > 0)
    )
    mentioned: dict[tuple[Platform, str], _Mentions] = {}
    for object_id, links, seen_at, zone in posts:
        profiles = {
            profile for link in links if (profile := normalize_account(link)) and profile[0] in SOCIAL_PLATFORMS
        }
        for profile in profiles:
            mentions = mentioned.setdefault(profile, _Mentions())
            mentions.posts += 1
            mentions.severity = max(mentions.severity, _ZONE_SEVERITY.get(zone, 0) if zone else 0)
            if object_id is not None:
                mentions.object_ids.add(object_id)
            if mentions.last_seen_at is None or seen_at > mentions.last_seen_at:
                mentions.last_seen_at = seen_at

    excluded = {
        (platform, handle.lower())
        for model in (SourceAccount, DismissedSourceSuggestion)
        for platform, handle in session.execute(select(model.platform, model.handle))
    }
    ranked = sorted(
        (item for item in mentioned.items() if item[0] not in excluded),
        key=lambda item: (
            -item[1].posts,
            -item[1].severity,
            -(item[1].last_seen_at.timestamp() if item[1].last_seen_at else 0),
            item[0][1],
        ),
    )
    return [
        SourceSuggestion(
            platform=platform,
            handle=handle,
            url=_PROFILE_URL[platform].format(handle),
            posts_count=mentions.posts,
            object_ids=sorted(mentions.object_ids),
            last_seen_at=mentions.last_seen_at,
        )
        for (platform, handle), mentions in ranked[:MAX_SUGGESTIONS]
    ]
