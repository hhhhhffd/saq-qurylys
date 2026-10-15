import json
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AdPost, Developer, LinkedEntity, Phrase, PhraseHit, SourceAccount
from app.models.enums import (
    AdStatus,
    DetectedBy,
    LinkedEntityKind,
    LinkMethod,
    LlmStatus,
    PhraseCategory,
)
from app.modules.nlp import llm, service, tasks
from tests.conftest import World, make_object
from tests.support_ads import add_ad


def hits_of(db: Session, ad: AdPost) -> list[PhraseHit]:
    return list(db.scalars(select(PhraseHit).where(PhraseHit.ad_post_id == ad.id).order_by(PhraseHit.start)))


# ---------------------------------------------------------------- dictionary analysis


def test_analyze_creates_hits_with_offsets_and_weights(db: Session, world: World) -> None:
    text = "Успейте забронируйте квартиру! Первоначальный взнос 10%, звоните 8 777 123 45 67 или t.me/alatau."
    ad = add_ad(db, world.ust, text)

    service.analyze_ad(db, ad)

    hits = hits_of(db, ad)
    assert [(hit.category, hit.matched_text) for hit in hits] == [
        (PhraseCategory.booking, "забронируйте"),
        (PhraseCategory.down_payment, "Первоначальный взнос"),
    ]
    assert all(text[hit.start : hit.end] == hit.matched_text for hit in hits)
    assert all(hit.detected_by is DetectedBy.dictionary and hit.confirmed is None for hit in hits)
    assert ad.max_phrase_weight == 10 and ad.total_phrase_weight == 20
    assert ad.phones == ["+77771234567"]
    assert ad.links == ["t.me/alatau"]


def test_analyze_is_idempotent_and_keeps_confirmations(db: Session, world: World) -> None:
    ad = add_ad(db, world.ust, "Бронь квартир и рассрочка")
    service.analyze_ad(db, ad)
    first = {hit.id: hit for hit in hits_of(db, ad)}
    rejected = next(hit for hit in first.values() if hit.category is PhraseCategory.booking)
    rejected.confirmed = False
    service.recompute_weights(db, ad)
    assert ad.max_phrase_weight == 8  # the rejected booking hit no longer counts

    service.analyze_ad(db, ad)

    again = {hit.id: hit for hit in hits_of(db, ad)}
    assert set(again) == set(first)
    assert again[rejected.id].confirmed is False
    assert ad.max_phrase_weight == 8 and ad.total_phrase_weight == 8


def test_analyze_drops_hits_of_deactivated_phrases_and_keeps_llm_hits(db: Session, world: World) -> None:
    ad = add_ad(db, world.ust, "Бронь квартир и рассрочка")
    service.analyze_ad(db, ad)
    db.add(
        PhraseHit(
            ad_post_id=ad.id,
            category=PhraseCategory.deposit,
            matched_text="квартир",
            start=5,
            end=12,
            weight=10,
            detected_by=DetectedBy.llm,
        )
    )
    booking = db.scalars(select(Phrase).where(Phrase.category == PhraseCategory.booking)).one()
    booking.is_active = False
    db.flush()

    service.analyze_ad(db, ad)

    assert {(hit.category, hit.detected_by) for hit in hits_of(db, ad)} == {
        (PhraseCategory.installment, DetectedBy.dictionary),
        (PhraseCategory.deposit, DetectedBy.llm),
    }
    assert ad.max_phrase_weight == 8  # the unconfirmed LLM hit does not count


def test_analyze_of_empty_text_clears_everything(db: Session, world: World) -> None:
    ad = add_ad(db, world.ust, None)
    service.analyze_ad(db, ad)
    assert hits_of(db, ad) == [] and ad.phones == [] and ad.links == [] and ad.max_phrase_weight == 0


# ---------------------------------------------------------------- linking


def test_link_by_source_account(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "ЖК Алатау")
    account = SourceAccount(platform="instagram", handle="alatau_zhk", object_id=obj.id, territory_id=world.ust.id)
    db.add(account)
    db.flush()
    ad = add_ad(db, world.ust, "Скидки!", source_account_id=account.id)

    previous, current = service.link_ad(db, ad)

    assert (previous, current) == (None, obj.id)
    assert (ad.link_method, ad.link_confidence, ad.status) == (LinkMethod.account, 1.0, AdStatus.captured)


def test_link_by_object_phone_beats_name(db: Session, world: World) -> None:
    by_phone = make_object(db, world.ust, "ЖК Первый")
    make_object(db, world.ust, "ЖК Второй")
    db.add(LinkedEntity(object_id=by_phone.id, kind=LinkedEntityKind.phone, value="+77771234567"))
    db.flush()
    ad = add_ad(db, world.ust, "ЖК Второй. Звоните 8 777 123 45 67", phones=["+77771234567"])

    service.link_ad(db, ad)

    assert (ad.object_id, ad.link_method, ad.link_confidence) == (by_phone.id, LinkMethod.phone, 0.9)
    assert ad.status is AdStatus.captured


def test_link_by_developer_phone(db: Session, world: World) -> None:
    developer = Developer(bin="123456789012", name="Застройщик", phones=["+77012223344"])
    db.add(developer)
    db.flush()
    obj = make_object(db, world.ust, "ЖК Один", developer_id=developer.id)
    ad = add_ad(db, world.ust, "Звоните", phones=["+77012223344"])

    service.link_ad(db, ad)

    assert (ad.object_id, ad.link_method) == (obj.id, LinkMethod.phone)


def test_phone_shared_by_several_objects_is_disambiguated_by_name_or_sent_to_verification(
    db: Session, world: World
) -> None:
    developer = Developer(bin="123456789012", name="Застройщик", phones=["+77012223344"])
    db.add(developer)
    db.flush()
    first = make_object(db, world.ust, "ЖК Алатау", developer_id=developer.id)
    make_object(db, world.ust, "ЖК Тулпар", developer_id=developer.id)

    named = add_ad(db, world.ust, "ЖК Алатау, звоните", phones=["+77012223344"])
    service.link_ad(db, named)
    assert (named.object_id, named.link_method, named.status) == (first.id, LinkMethod.phone, AdStatus.captured)

    anonymous = add_ad(db, world.ust, "Звоните", phones=["+77012223344"])
    service.link_ad(db, anonymous)
    assert anonymous.object_id is None and anonymous.status is AdStatus.verification


def test_link_by_name_and_alias(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "Жилой комплекс Алатау", aliases=["Alatau Park"])
    make_object(db, world.ust, "ЖК Тулпар")

    by_name = add_ad(db, world.ust, "Жилой комплекс Алатау: квартиры от застройщика")
    service.link_ad(db, by_name)
    assert (by_name.object_id, by_name.link_method, by_name.link_confidence) == (obj.id, LinkMethod.name, 1.0)
    assert by_name.status is AdStatus.captured and by_name.territory_id == world.ust.id

    by_alias = add_ad(db, world.ust, "Новинка: Alatau Park, бронь открыта")
    service.link_ad(db, by_alias)
    assert by_alias.object_id == obj.id


def test_weak_name_match_is_proposed_but_needs_verification(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "Жилой комплекс Алатау Парк Резиденс")
    ad = add_ad(db, world.ust, "Алатау скоро")

    service.link_ad(db, ad)

    assert ad.object_id == obj.id and ad.link_method is LinkMethod.name
    assert ad.link_confidence is not None and 0.5 <= ad.link_confidence < 0.8
    assert ad.status is AdStatus.verification


def test_unrelated_text_is_not_linked_and_needs_verification(db: Session, world: World) -> None:
    make_object(db, world.ust, "ЖК Алатау")
    ad = add_ad(db, world.ust, "Продам гараж недорого")

    service.link_ad(db, ad)

    assert ad.object_id is None and ad.link_method is None and ad.link_confidence is None
    assert ad.status is AdStatus.verification


def test_two_equally_good_names_are_ambiguous(db: Session, world: World) -> None:
    first = make_object(db, world.ust, "ЖК Алатау")
    make_object(db, world.ust, "ЖК Алатау")
    ad = add_ad(db, world.ust, "ЖК Алатау, квартиры")

    service.link_ad(db, ad)

    assert ad.object_id == first.id  # tentative: the lowest id
    assert ad.status is AdStatus.verification


def test_linking_is_restricted_to_the_territory_of_the_post(db: Session, world: World) -> None:
    make_object(db, world.semey, "ЖК Алатау")
    ust_ad = add_ad(db, world.ust, "ЖК Алатау, квартиры")
    service.link_ad(db, ust_ad)
    assert ust_ad.object_id is None

    region_ad = add_ad(db, world.region, "ЖК Алатау, квартиры")
    service.link_ad(db, region_ad)
    assert region_ad.object_id is not None and region_ad.territory_id == world.semey.id


def test_manual_link_is_never_overridden(db: Session, world: World) -> None:
    chosen = make_object(db, world.ust, "ЖК Выбранный")
    make_object(db, world.ust, "ЖК Алатау")
    ad = add_ad(db, world.ust, "ЖК Алатау", object_id=chosen.id, link_method=LinkMethod.manual, link_confidence=1.0)

    assert service.link_ad(db, ad) == (chosen.id, chosen.id)
    assert (ad.object_id, ad.link_method, ad.status) == (chosen.id, LinkMethod.manual, AdStatus.captured)


def test_link_does_not_touch_a_removed_post_status(db: Session, world: World) -> None:
    ad = add_ad(db, world.ust, "Продам гараж", status=AdStatus.removed_saved)
    service.link_ad(db, ad)
    assert ad.status is AdStatus.removed_saved


# ---------------------------------------------------------------- LLM


def ollama_reply(content: object) -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps(content)}})


def mock_client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def llm_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_enabled", True)
    monkeypatch.setattr(get_settings(), "ollama_url", "http://ollama.test:11434/")
    monkeypatch.setattr(get_settings(), "ollama_model", "test-model")


def test_llm_disabled_marks_the_post_and_makes_no_request(db: Session, world: World) -> None:
    ad = add_ad(db, world.ust, "Бронь")
    service.llm_extract_ad(db, ad, mock_client(lambda request: pytest.fail("no request expected")))
    assert ad.llm_status is LlmStatus.disabled and ad.llm_extraction is None


def extraction_reply(findings: list[tuple[str, str, float]] | None = None, **fields: Any) -> dict[str, Any]:
    """An answer of the model in the schema of SPEC 5."""
    return {
        "findings": [{"category": c, "quote": q, "confidence": confidence} for c, q, confidence in findings or []],
        "payment_schemes": [],
        "claimed_readiness_pct": None,
        "price_before_completion": False,
        "confidence": 0.8,
        **fields,
    }


@pytest.mark.usefixtures("llm_on")
def test_llm_extraction_is_stored_as_an_assumption_with_located_findings(db: Session, world: World) -> None:
    text = "ЖК Алатау готов на 70%.  Оставьте  залог 500 000 тг, квартира  по   фиксированной цене!"
    ad = add_ad(db, world.ust, text)
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        assert str(request.url) == "http://ollama.test:11434/api/chat"
        return ollama_reply(
            extraction_reply(
                [
                    ("deposit", "залог 500 000 тг", 0.9),
                    ("price_before_completion", "по фиксированной цене", 0.3),
                    ("booking", "этого нет в тексте", 0.9),
                    ("deposit", "залог  500 000   тг", 0.9),  # the same finding again
                    ("covert_contract", "", 0.9),
                ],
                payment_schemes=["deposit", "deposit"],
                claimed_readiness_pct=70,
            )
        )

    service.llm_extract_ad(db, ad, mock_client(handler))

    [body] = requests
    assert body["model"] == "test-model" and body["stream"] is False and body["think"] is False
    assert body["options"] == {"temperature": 0}
    assert set(body["format"]["required"]) == {
        "findings",
        "payment_schemes",
        "claimed_readiness_pct",
        "price_before_completion",
        "confidence",
    }
    category_enum = body["format"]["properties"]["findings"]["items"]["properties"]["category"]["enum"]
    assert set(category_enum) == {category.value for category in PhraseCategory}
    assert body["messages"][0]["role"] == "system" and text in body["messages"][1]["content"]

    assert ad.llm_status is LlmStatus.done
    # Stored as the model said it (de-duplicated), without the flags the API derives.
    assert ad.llm_extraction == {
        "findings": [
            {"category": "deposit", "quote": "залог 500 000 тг", "confidence": 0.9},
            {"category": "price_before_completion", "quote": "по фиксированной цене", "confidence": 0.3},
            {"category": "booking", "quote": "этого нет в тексте", "confidence": 0.9},
        ],
        "payment_schemes": ["deposit"],
        "claimed_readiness_pct": 70,
        "price_before_completion": False,
        "confidence": 0.8,
    }
    # The confirmed fields stay as they were until a person accepts the extraction.
    assert ad.payment_schemes == [] and ad.claimed_readiness_pct is None and ad.price_before_completion is False

    hits = hits_of(db, ad)
    assert [(hit.matched_text, hit.category) for hit in hits] == [
        ("залог 500 000 тг", PhraseCategory.deposit),
        ("по   фиксированной цене", PhraseCategory.price_before_completion),
    ]
    assert all(text[hit.start : hit.end] == hit.matched_text for hit in hits)
    assert all((hit.detected_by, hit.confirmed, hit.phrase_id) == (DetectedBy.llm, None, None) for hit in hits)
    assert [hit.weight for hit in hits] == [10, 6]  # the heaviest active phrase of the category
    # An LLM hit weighs nothing before a person confirms it.
    assert ad.max_phrase_weight == 0 and ad.total_phrase_weight == 0

    extraction = llm.Extraction.model_validate(ad.llm_extraction)
    assert [service.finding_for_hit(hit, extraction) for hit in hits] == extraction.findings[:2]
    assert [finding.uncertain for finding in extraction.findings] == [False, True, False]
    assert extraction.uncertain is False


@pytest.mark.usefixtures("llm_on")
def test_llm_findings_overlapping_dictionary_hits_are_not_duplicated(db: Session, world: World) -> None:
    text = "Оформим рассрочку на год, а залог вернём"
    ad = add_ad(db, world.ust, text)
    service.analyze_ad(db, ad)  # the dictionary finds рассрочку itself
    reply = extraction_reply([("installment", "Оформим рассрочку на год", 0.9), ("deposit", "залог вернём", 0.7)])

    service.llm_extract_ad(db, ad, mock_client(lambda request: ollama_reply(reply)))

    llm_hits = [hit for hit in hits_of(db, ad) if hit.detected_by is DetectedBy.llm]
    assert [(hit.matched_text, hit.category) for hit in llm_hits] == [("залог вернём", PhraseCategory.deposit)]
    assert service.finding_for_hit(hits_of(db, ad)[0], llm.Extraction.model_validate(ad.llm_extraction)) is None


@pytest.mark.usefixtures("llm_on")
def test_llm_category_without_active_phrases_gets_no_hit(db: Session, world: World) -> None:
    for row in db.scalars(select(Phrase).where(Phrase.category == PhraseCategory.deposit)):
        row.is_active = False
    db.flush()
    ad = add_ad(db, world.ust, "Оставьте залог сегодня")

    service.llm_extract_ad(
        db, ad, mock_client(lambda request: ollama_reply(extraction_reply([("deposit", "залог", 0.9)])))
    )

    assert ad.llm_status is LlmStatus.done and hits_of(db, ad) == []
    assert llm.Extraction.model_validate(ad.llm_extraction).findings[0].quote == "залог"


@pytest.mark.usefixtures("llm_on")
def test_llm_rerun_replaces_unreviewed_hits_but_keeps_decided_ones(db: Session, world: World) -> None:
    text = "Внесите залог сегодня, обеспечение возвращается"
    ad = add_ad(db, world.ust, text)

    def reply(*quotes: str) -> Any:
        return lambda request: ollama_reply(extraction_reply([("deposit", quote, 0.9) for quote in quotes]))

    service.llm_extract_ad(db, ad, mock_client(reply("Внесите залог", "возвращается")))
    decided, unreviewed = hits_of(db, ad)
    decided.confirmed = True
    db.flush()

    service.llm_extract_ad(db, ad, mock_client(reply("Внесите залог", "обеспечение возвращается")))

    remaining = hits_of(db, ad)
    assert [hit.matched_text for hit in remaining] == ["Внесите залог", "обеспечение возвращается"]
    assert remaining[0].id == decided.id and remaining[0].confirmed is True
    assert db.get(PhraseHit, unreviewed.id) is None
    assert ad.max_phrase_weight == 10  # the confirmed LLM hit counts


@pytest.mark.usefixtures("llm_on")
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="boom"),
        httpx.Response(200, json={"message": {"content": "not json"}}),
        httpx.Response(200, json={"message": {"content": ""}}),
        httpx.Response(200, json={"message": {"content": json.dumps({"claimed_readiness_pct": 150})}}),
        httpx.Response(200, json={"message": {"content": json.dumps({"payment_schemes": ["barter"]})}}),
        httpx.Response(200, json={"message": {"content": json.dumps(extraction_reply([("weird", "x", 0.5)]))}}),
        httpx.Response(200, json={"message": {"content": json.dumps(extraction_reply([("booking", "x", -1)]))}}),
        httpx.Response(200, json={"message": {"content": json.dumps(extraction_reply(confidence=1000))}}),
        httpx.Response(200, json={"unexpected": True}),
    ],
)
def test_llm_failures_are_recorded_without_changing_the_post(
    db: Session, world: World, response: httpx.Response
) -> None:
    ad = add_ad(db, world.ust, "Бронь")
    service.llm_extract_ad(db, ad, mock_client(lambda request: response))
    assert ad.llm_status is LlmStatus.failed and ad.llm_extraction is None
    assert ad.payment_schemes == [] and hits_of(db, ad) == []


def test_llm_confidence_given_in_percent_is_normalized() -> None:
    extraction = llm.Extraction.model_validate(
        extraction_reply([("booking", "Бронь", 85), ("deposit", "залог", 1)], confidence=40)
    )
    assert [finding.confidence for finding in extraction.findings] == [0.85, 1.0]
    assert extraction.confidence == 0.4 and extraction.uncertain is True
    assert [finding.uncertain for finding in extraction.findings] == [False, False]


def test_llm_findings_are_limited_and_unique() -> None:
    many = [("booking", f"фрагмент {number}", 0.9) for number in range(25)]
    assert len(llm.Extraction.model_validate(extraction_reply(many)).findings) == llm.MAX_FINDINGS
    repeated = [("booking", "Бронь", 0.9), ("booking", "  бронь ", 0.2), ("deposit", "бронь", 0.9)]
    assert len(llm.Extraction.model_validate(extraction_reply(repeated)).findings) == 2


@pytest.mark.usefixtures("llm_on")
def test_llm_unreachable_server_fails_gracefully(db: Session, world: World) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    ad = add_ad(db, world.ust, "Бронь")
    service.llm_extract_ad(db, ad, mock_client(refuse))
    assert ad.llm_status is LlmStatus.failed


@pytest.mark.usefixtures("llm_on")
def test_llm_retries_without_think_when_the_server_does_not_know_it(db: Session, world: World) -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if "think" in body:
            return httpx.Response(400, json={"error": '"test-model" does not support thinking: think value invalid'})
        return ollama_reply(extraction_reply())

    ad = add_ad(db, world.ust, "Просто текст")
    service.llm_extract_ad(db, ad, mock_client(handler))

    assert [("think" in body) for body in bodies] == [True, False]
    assert ad.llm_status is LlmStatus.done


@pytest.mark.usefixtures("llm_on")
def test_llm_thinking_block_in_the_answer_is_ignored() -> None:
    answer = "<think>рассуждаю</think>" + json.dumps(extraction_reply(payment_schemes=["installment"]))
    client = mock_client(lambda request: httpx.Response(200, json={"message": {"content": answer, "thinking": "..."}}))
    extraction = llm.extract("Рассрочка", get_settings(), client)
    assert [scheme.value for scheme in extraction.payment_schemes] == ["installment"]


def test_llm_text_without_content_is_not_sent(db: Session, world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_enabled", True)
    ad = add_ad(db, world.ust, "   ")
    service.llm_extract_ad(db, ad, mock_client(lambda request: pytest.fail("no request expected")))
    assert ad.llm_status is LlmStatus.none


# ---------------------------------------------------------------- Celery tasks


class SessionFactory:
    """Stands in for the sessionmaker so that the tasks work inside the test transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def __call__(self) -> "SessionFactory":
        return self

    def __enter__(self) -> Session:
        return self.session

    def __exit__(self, *args: object) -> None:
        return None


def test_tasks_run_the_pipeline_steps(db: Session, world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    changed: list[int] = []
    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: SessionFactory(db))
    monkeypatch.setattr(tasks, "object_changed", changed.append)
    monkeypatch.setattr(tasks, "objects_changed", lambda ids: changed.extend(ids))
    obj = make_object(db, world.ust, "ЖК Алатау")
    ad = add_ad(db, world.ust, "ЖК Алатау: бронь квартир, звоните 8 777 123 45 67")

    tasks.analyze(ad.id)
    tasks.link(ad.id)
    tasks.llm_extract(ad.id)

    assert ad.max_phrase_weight == 10 and ad.phones == ["+77771234567"]
    assert ad.object_id == obj.id
    assert ad.llm_status is LlmStatus.disabled
    assert changed == [obj.id, obj.id]  # after linking and at the end of the pipeline


def test_tasks_ignore_a_missing_post(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: SessionFactory(db))
    for task in (tasks.analyze, tasks.link, tasks.llm_extract):
        task(987654321)
