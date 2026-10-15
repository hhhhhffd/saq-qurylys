"""Analysis of ad publications: dictionary hits, linking to a construction object, LLM extraction."""

import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from rapidfuzz import fuzz, process, utils
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AdPost, ConstructionObject, Developer, LinkedEntity, Phrase, PhraseHit, SourceAccount, Territory
from app.models.enums import (
    AdStatus,
    DetectedBy,
    LinkedEntityKind,
    LinkMethod,
    LlmStatus,
    PhraseCategory,
)
from app.modules.nlp import llm
from app.modules.nlp.text import extract_links, extract_phones, find_matches
from app.modules.settings.service import load_settings
from app.scope import TerritoryScope
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

ACCOUNT_CONFIDENCE = 1.0
PHONE_CONFIDENCE = 0.9
# Below this similarity a name is noise: no tentative link is proposed. The similarity of a name is the share
# of its distinctive words found in the text, so this keeps "three of four words" (0.75) and drops two of three.
MIN_NAME_SIMILARITY = 0.75
# A word of the name counts as found when some word of the text is this similar to it (0..100): a typo or an
# ending passes, a different name (Самал / Самат is 80) does not.
WORD_MATCH = 85
# Words that every residential complex has: "ЖК" in the text must not link a post to every "ЖК Нур".
GENERIC_NAME_WORDS = frozenset(
    {"жк", "мжк", "жилой", "комплекс", "дом", "квартал", "микрорайон", "мкр", "residence", "residences", "complex"}
)
# Two objects whose similarity differs by less than this are indistinguishable by name.
AMBIGUITY_MARGIN = 0.05
MIN_NAME_LENGTH = 3
# After a dictionary change the posts of this period are analyzed again; older ones keep their hits.
REANALYZE_WINDOW_DAYS = 90
REANALYZE_BATCH_SIZE = 200


def recompute_weights(session: Session, ad: AdPost) -> None:
    """`max_phrase_weight` / `total_phrase_weight` from the hits that count: a dictionary hit counts until a
    person rejects it, a hit of the LLM only once a person confirmed it. A phrase counts once per post."""
    hits = session.scalars(select(PhraseHit).where(PhraseHit.ad_post_id == ad.id))
    weights: dict[tuple[int | None, PhraseCategory], int] = {}
    for hit in hits:
        if hit.confirmed is True or (hit.confirmed is None and hit.detected_by is DetectedBy.dictionary):
            key = (hit.phrase_id, hit.category)
            weights[key] = max(weights.get(key, 0), hit.weight)
    ad.max_phrase_weight = max(weights.values(), default=0)
    ad.total_phrase_weight = sum(weights.values())


def analyze_ad(session: Session, ad: AdPost, phrases: list[Phrase] | None = None) -> bool:
    """Replace the dictionary hits of the post, extract its phones and links.

    Idempotent: a hit that is found again (same phrase and position) is kept together with the person's
    confirmation; hits of the LLM are not touched. `phrases` are the active phrases when the caller already
    has them. Returns whether the dictionary hits changed.
    """
    text = ad.text or ""
    if phrases is None:
        phrases = list(session.scalars(select(Phrase).where(Phrase.is_active)))
    stale = {
        (hit.phrase_id, hit.start, hit.end): hit
        for hit in session.scalars(
            select(PhraseHit).where(PhraseHit.ad_post_id == ad.id, PhraseHit.detected_by == DetectedBy.dictionary)
        )
    }
    changed = False
    for match in find_matches(text, phrases):
        hit = stale.pop((match.phrase.id, match.start, match.end), None)
        if hit is None:
            hit = PhraseHit(
                ad_post_id=ad.id,
                phrase_id=match.phrase.id,
                start=match.start,
                end=match.end,
                detected_by=DetectedBy.dictionary,
            )
            session.add(hit)
            changed = True
        elif (hit.category, hit.weight) != (match.phrase.category, match.phrase.weight):
            changed = True
        hit.category = match.phrase.category
        hit.matched_text = match.text
        hit.weight = match.phrase.weight
    for hit in stale.values():
        session.delete(hit)
        changed = True
    session.flush()

    ad.phones = extract_phones(text)
    ad.links = extract_links(text)
    recompute_weights(session, ad)
    return changed


def reanalyze_recent(session: Session) -> Iterator[set[int]]:
    """Run the dictionary analysis again over the posts of the last `REANALYZE_WINDOW_DAYS` days, after the
    dictionary changed. Works in committed batches and yields, after each, the objects whose posts got other
    dictionary hits (their risk has to be recalculated)."""
    since = datetime.now(UTC) - timedelta(days=REANALYZE_WINDOW_DAYS)
    recency = func.coalesce(AdPost.published_at, AdPost.captured_at, AdPost.created_at)
    phrases = list(session.scalars(select(Phrase).where(Phrase.is_active)))
    last_id = 0
    while True:
        batch = session.scalars(
            select(AdPost)
            .where(AdPost.id > last_id, AdPost.text.isnot(None), recency >= since)
            .order_by(AdPost.id)
            .limit(REANALYZE_BATCH_SIZE)
        ).all()
        if not batch:
            return
        affected = {ad.object_id for ad in batch if analyze_ad(session, ad, phrases) and ad.object_id is not None}
        session.commit()
        last_id = batch[-1].id
        yield affected


def enqueue_reanalysis() -> bool:
    """Queue `nlp.reanalyze_recent`. Call after the dictionary change is committed; returns False when the
    broker is unreachable (the change itself is saved, a manual re-run is possible)."""
    if not get_settings().events_enabled:
        return True
    try:
        celery_app.send_task("nlp.reanalyze_recent", queue="nlp", retry=False, ignore_result=True)
    except Exception:
        logger.exception("Failed to enqueue nlp.reanalyze_recent")
        return False
    return True


# ---------------------------------------------------------------- linking


@dataclass(frozen=True)
class _NameScore:
    object_id: int
    similarity: float
    name_tokens: int


def _territory_subtree(session: Session, territory_id: int) -> frozenset[int]:
    tree = select(Territory.id).where(Territory.id == territory_id).cte("tree", recursive=True)
    tree = tree.union_all(select(Territory.id).join(tree, Territory.parent_id == tree.c.id))
    return frozenset(session.scalars(select(tree.c.id)))


def _normalize(value: str) -> str:
    return str(utils.default_process(value.replace("ё", "е").replace("Ё", "Е")))


def _name_words(name: str) -> list[str]:
    """The distinctive words of an object name: without the generic ones and single characters."""
    words = (word for word in _normalize(name).split() if word not in GENERIC_NAME_WORDS and len(word) > 1)
    return list(dict.fromkeys(words))


def _score_names(objects: list[ConstructionObject], text: str) -> list[_NameScore]:
    """Share of the distinctive words of every object's name or alias that the text contains, best first.

    Every word is scored by its best match among the words of the text; a word below `WORD_MATCH` scores 0,
    so a name is strong only when all of its distinctive words are found.
    """
    words = sorted(set(_normalize(text).split()))
    scores: list[_NameScore] = []
    for obj in objects:
        best: _NameScore | None = None
        for name in (obj.name, *obj.aliases):
            name_words = _name_words(name)
            if not name_words or max(len(word) for word in name_words) < MIN_NAME_LENGTH:
                continue
            total = 0.0
            for word in name_words:
                found = process.extractOne(word, words, scorer=fuzz.ratio, score_cutoff=WORD_MATCH)
                total += found[1] / 100 if found else 0.0
            candidate = _NameScore(obj.id, total / len(name_words), len(name_words))
            if best is None or (candidate.similarity, candidate.name_tokens) > (best.similarity, best.name_tokens):
                best = candidate
        if best is not None:
            scores.append(best)
    scores.sort(key=lambda score: (-score.similarity, -score.name_tokens, score.object_id))
    return scores


def _by_name(scores: list[_NameScore], threshold: float) -> tuple[int | None, float | None, bool]:
    """(object id, confidence, ambiguous) of the best name match."""
    if not scores or scores[0].similarity < MIN_NAME_SIMILARITY:
        return None, None, False
    best = scores[0]
    rival = next((score for score in scores[1:] if score.similarity >= threshold), None)
    ambiguous = rival is not None and best.similarity - rival.similarity < AMBIGUITY_MARGIN
    return best.object_id, best.similarity, ambiguous


def _phone_candidates(session: Session, phones: list[str], scope: TerritoryScope) -> list[ConstructionObject]:
    """Objects that own one of the phones; objects of a developer owning it only when no object does."""
    direct = (
        select(ConstructionObject)
        .join(LinkedEntity, LinkedEntity.object_id == ConstructionObject.id)
        .where(LinkedEntity.kind == LinkedEntityKind.phone, LinkedEntity.value.in_(phones))
    )
    developer_phone = select(LinkedEntity.developer_id).where(
        LinkedEntity.kind == LinkedEntityKind.phone, LinkedEntity.value.in_(phones)
    )
    via_developer = select(ConstructionObject).where(
        or_(
            ConstructionObject.developer_id.in_(developer_phone),
            ConstructionObject.developer_id.in_(select(Developer.id).where(Developer.phones.overlap(phones))),
        )
    )
    for stmt in (direct, via_developer):
        found = list(session.scalars(scope.restrict(stmt, ConstructionObject.territory_id).distinct()))
        if found:
            return found
    return []


def link_ad(session: Session, ad: AdPost) -> tuple[int | None, int | None]:
    """Link the post to an object by account, then phone, then name (SPEC 5). A manual link is never changed.

    Returns (previous object id, current object id).
    """
    previous = ad.object_id
    if ad.link_method is LinkMethod.manual:
        return previous, previous
    threshold = load_settings(session).link_confidence_threshold
    scope = TerritoryScope(ids=_territory_subtree(session, ad.territory_id) if ad.territory_id is not None else None)

    object_id: int | None = None
    confidence: float | None = None
    method: LinkMethod | None = None
    ambiguous = False

    account = session.get(SourceAccount, ad.source_account_id) if ad.source_account_id else None
    if account is not None and account.object_id is not None:
        stmt = select(ConstructionObject.id).where(ConstructionObject.id == account.object_id)
        linked = session.scalar(scope.restrict(stmt, ConstructionObject.territory_id))
        if linked is not None:
            object_id, confidence, method = linked, ACCOUNT_CONFIDENCE, LinkMethod.account

    if method is None and ad.phones:
        candidates = _phone_candidates(session, ad.phones, scope)
        if len(candidates) == 1:
            object_id, confidence, method = candidates[0].id, PHONE_CONFIDENCE, LinkMethod.phone
        elif candidates:
            by_name_id, by_name_confidence, by_name_ambiguous = _by_name(
                _score_names(candidates, ad.text or ""), threshold
            )
            if by_name_id is not None and by_name_confidence is not None and by_name_confidence >= threshold:
                object_id, confidence, method = by_name_id, PHONE_CONFIDENCE, LinkMethod.phone
                ambiguous = by_name_ambiguous
            else:
                ambiguous = True

    if method is None and not ambiguous:
        objects = list(session.scalars(scope.restrict(select(ConstructionObject), ConstructionObject.territory_id)))
        object_id, confidence, ambiguous = _by_name(_score_names(objects, ad.text or ""), threshold)
        method = LinkMethod.name if object_id is not None else None

    ad.object_id = object_id
    ad.link_confidence = confidence
    ad.link_method = method
    if object_id is not None:
        ad.territory_id = session.scalar(
            select(ConstructionObject.territory_id).where(ConstructionObject.id == object_id)
        )
    if ad.status is not AdStatus.removed_saved:
        confident = object_id is not None and not ambiguous and confidence is not None and confidence >= threshold
        ad.status = AdStatus.captured if confident else AdStatus.verification
    return previous, object_id


# ---------------------------------------------------------------- LLM


def _locate(text: str, quote: str) -> tuple[int, int] | None:
    """Position of the quote in the text, tolerant to case and to differences in whitespace."""
    pattern = r"\s+".join(re.escape(word) for word in quote.split())
    match = re.search(pattern, text, re.IGNORECASE) if pattern else None
    return (match.start(), match.end()) if match else None


def finding_for_hit(hit: PhraseHit, extraction: llm.Extraction | None) -> llm.Finding | None:
    """The finding of the model that an LLM hit was made from: same category and same fragment."""
    if hit.detected_by is not DetectedBy.llm or extraction is None:
        return None
    fragment = llm.normalize_quote(hit.matched_text)
    return next(
        (f for f in extraction.findings if f.category is hit.category and llm.normalize_quote(f.quote) == fragment),
        None,
    )


def _add_llm_hits(session: Session, ad: AdPost, extraction: llm.Extraction) -> None:
    text = ad.text or ""
    weights = dict(
        session.execute(
            select(Phrase.category, func.max(Phrase.weight)).where(Phrase.is_active).group_by(Phrase.category)
        )
        .tuples()
        .all()
    )

    # Keep the decisions already taken by a person; the rest of the previous LLM hits is replaced.
    taken: list[tuple[int, int]] = []
    for hit in session.scalars(select(PhraseHit).where(PhraseHit.ad_post_id == ad.id)):
        if hit.detected_by is DetectedBy.llm and hit.confirmed is None:
            session.delete(hit)
        else:
            taken.append((hit.start, hit.end))
    session.flush()

    for finding in extraction.findings:
        span = _locate(text, finding.quote)
        # The weight of a category is that of its heaviest active phrase; without one there is nothing to weigh.
        if span is None or finding.category not in weights or any(span[0] < e and s < span[1] for s, e in taken):
            continue
        session.add(
            PhraseHit(
                ad_post_id=ad.id,
                phrase_id=None,
                category=finding.category,
                matched_text=text[span[0] : span[1]],
                start=span[0],
                end=span[1],
                weight=weights[finding.category],
                detected_by=DetectedBy.llm,
            )
        )
        taken.append(span)


def llm_extract_ad(session: Session, ad: AdPost, client: httpx.Client | None = None) -> None:
    """Fill `llm_extraction` and the LLM hits of the post. The confirmed fields of the post are not touched.

    Commits once to publish the `pending` state before the (long) request to the model.
    """
    settings = get_settings()
    if not settings.llm_enabled:
        ad.llm_status = LlmStatus.disabled
        return
    text = (ad.text or "").strip()
    if not text:
        ad.llm_status = LlmStatus.none
        return
    ad.llm_status = LlmStatus.pending
    session.commit()
    try:
        extraction = llm.extract(text, settings, client)
    except llm.LlmError:
        logger.warning("LLM extraction failed for ad_post %s", ad.id, exc_info=True)
        ad.llm_status = LlmStatus.failed
        return
    ad.llm_extraction = extraction.to_stored()
    ad.llm_status = LlmStatus.done
    _add_llm_hits(session, ad, extraction)
    session.flush()
    recompute_weights(session, ad)
