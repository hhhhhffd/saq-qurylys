import json
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app import seed, seed_history, seed_versions
from app.models import (
    AdPost,
    AdPostVersion,
    Assignment,
    Complaint,
    ConstructionObject,
    Notification,
    PhraseHit,
    SignalCard,
    SourceAccount,
    VisionAsset,
    VisionFinding,
    VisionSession,
)
from app.models.enums import (
    AdOrigin,
    AdReviewState,
    AssignmentStatus,
    ComplaintSource,
    LlmStatus,
    Platform,
    SignalStatus,
    VisionAssetKind,
    Zone,
)
from app.seed_activity import ACTIVITY_FILE, ActivityData, seed_demo_activity

DATA = ActivityData.model_validate_json((seed.SEED_DATA_DIR / ACTIVITY_FILE).read_text(encoding="utf-8"))


def _n(db: Session, stmt: Select[int]) -> int:
    return db.scalar(stmt) or 0


@pytest.fixture
def activity(db: Session) -> Session:
    """The whole demo as `--demo` loads it, up to and including the living demo."""
    seed.seed_reference(db)
    seed.load_districts(db)
    seed.seed_demo_users(db)
    object_ids = seed.seed_demo_objects(db) + seed.seed_demo_objects(db, seed.DEMO_NETWORK_FILE)
    object_ids += seed_versions.seed_demo_versions(db)
    seed_history.seed_demo_history(db, object_ids)
    seed_demo_activity(db)
    return db


def test_risky_wordings_of_the_pools_are_found_by_the_dictionary(db: Session) -> None:
    seed.seed_reference(db)
    from app.models import Phrase
    from app.modules.nlp.text import find_matches

    phrases = list(db.scalars(select(Phrase)))
    for template in DATA.pools.risky_ru + DATA.pools.citizen:
        assert find_matches(template.format(obj="ЖК «Демо»", phone="+7 700 000 00 00"), phrases), template
    for template in DATA.pools.ordinary_ru:
        assert not find_matches(template.format(obj="ЖК «Демо»", phone="+7 700 000 00 00"), phrases), template


def test_the_file_is_fictional() -> None:
    raw = (seed.SEED_DATA_DIR / ACTIVITY_FILE).read_text(encoding="utf-8")
    for source in DATA.sources:
        assert (source.url or "").count("example.invalid") == 1 or source.url is None
        for post in source.posts:
            assert post.url is None or "example.invalid" in post.url
        assert source.feed is None or "example.invalid" in source.feed.post_url
    assert "https://t.me/" not in raw and "https://www." not in raw


def test_demo_sources_are_never_polled(activity: Session) -> None:
    accounts = list(activity.scalars(select(SourceAccount)))
    assert {account.platform for account in accounts} == set(Platform) - {Platform.outdoor}
    assert all(not account.is_watched and account.last_error is None for account in accounts)
    assert all(account.last_collected_at is not None for account in accounts)


def test_the_feed_is_full_and_comes_from_every_platform(activity: Session) -> None:
    collected = list(activity.scalars(select(AdPost).where(AdPost.origin == AdOrigin.collector)))
    assert len(collected) > 200
    assert {ad.platform for ad in collected} == set(Platform) - {Platform.outdoor}
    assert all(ad.is_demo and ad.source_account_id is not None for ad in collected)
    assert _n(activity, select(func.count()).select_from(AdPost).where(AdPost.origin == AdOrigin.citizen)) >= 20
    assert {AdReviewState.reviewed, AdReviewState.deferred, AdReviewState.irrelevant} <= {
        ad.review_state for ad in collected
    }
    assert _n(activity, select(func.count()).select_from(AdPostVersion)) >= 10
    assert _n(activity, select(func.count()).select_from(PhraseHit)) > 300
    assert any(ad.llm_status is LlmStatus.done for ad in collected)
    assert any(ad.removed_detected_at for ad in collected)
    oldest = min(ad.published_at for ad in collected if ad.published_at)
    assert (datetime.now(UTC) - oldest).days > 90


def test_complaints_come_from_every_channel(activity: Session) -> None:
    sources = {c.source for c in activity.scalars(select(Complaint))}
    assert {ComplaintSource.telegram, ComplaintSource.eotinish, ComplaintSource.manual} <= sources
    assert _n(activity, select(func.count()).select_from(Complaint).where(Complaint.is_collective)) >= 4


def test_signal_cards_cover_every_status_and_the_receiving_bodies_see_theirs(activity: Session) -> None:
    cards = list(activity.scalars(select(SignalCard)))
    assert {card.status for card in cards} == set(SignalStatus)
    sent_to = {card.recipient for card in cards if card.status is SignalStatus.sent}
    assert len(sent_to) >= 2
    red = list(activity.scalars(select(ConstructionObject).where(ConstructionObject.zone == Zone.red)))
    assert len(red) >= 3 and all(any(card.object_id == obj.id for card in cards) for obj in red)
    # One open card per object at most.
    open_per_object = activity.execute(
        select(SignalCard.object_id, func.count())
        .where(SignalCard.status.in_([SignalStatus.requires_confirmation, SignalStatus.returned, SignalStatus.sent]))
        .group_by(SignalCard.object_id)
    ).all()
    assert all(count == 1 for _, count in open_per_object)


def test_assignments_and_notifications(activity: Session) -> None:
    assignments = list(activity.scalars(select(Assignment)))
    assert {a.status for a in assignments} == set(AssignmentStatus)
    assert any(a.status is AssignmentStatus.open and a.due_date < date.today() for a in assignments)
    assert _n(activity, select(func.count()).select_from(Notification).where(Notification.read_at.is_not(None))) > 0
    assert _n(activity, select(func.count()).select_from(Notification).where(Notification.read_at.is_(None))) > 0


def test_vision_sessions_have_video_frames_and_findings(activity: Session) -> None:
    assert _n(activity, select(func.count()).select_from(VisionSession)) >= 7
    videos = list(activity.scalars(select(VisionAsset).where(VisionAsset.kind == VisionAssetKind.video)))
    assert len(videos) >= 2 and all(video.content_type == "video/mp4" for video in videos)
    assert _n(activity, select(func.count()).select_from(VisionFinding)) >= 20
    vision_ads = list(activity.scalars(select(AdPost).where(AdPost.origin == AdOrigin.vision)))
    assert len(vision_ads) >= 4 and all(ad.platform is Platform.outdoor and ad.is_outdoor for ad in vision_ads)


def test_scores_of_the_scenarios_stay_as_documented(activity: Session) -> None:
    expected = {
        "ЖК «Северный бриз»": 35,
        "ЖК «Золотая осень»": 70,
        "ЖК «Тихая гавань»": 10,
        "ЖК «Кедровый квартал»": 45,
    }
    for name, score in expected.items():
        assert activity.scalars(select(ConstructionObject.score).where(ConstructionObject.name == name)).one() == score


def test_repeating_the_activity_adds_nothing(activity: Session) -> None:
    def counts() -> list[int]:
        return [
            _n(activity, select(func.count()).select_from(model)) or 0
            for model in (
                AdPost,
                Complaint,
                SignalCard,
                Assignment,
                SourceAccount,
                VisionSession,
                Notification,
                AdPostVersion,
            )
        ]

    before = counts()
    seed_demo_activity(activity)
    assert counts() == before


def test_the_file_round_trips() -> None:
    json.loads((seed.SEED_DATA_DIR / ACTIVITY_FILE).read_text(encoding="utf-8"))
