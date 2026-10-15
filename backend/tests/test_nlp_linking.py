"""Linking a post to an object by name: only the distinctive words of the name count, and a name is strong only
when all of them are found."""

import pytest
from sqlalchemy.orm import Session

from app.models import SourceAccount
from app.models.enums import AdOrigin, AdStatus, LinkMethod, Platform
from app.modules.nlp import service
from app.modules.settings.service import save_settings
from tests.conftest import World, make_object
from tests.support_ads import add_ad


def link(db: Session, world: World, text: str) -> tuple[int | None, float | None, AdStatus]:
    ad = add_ad(db, world.ust, text)
    service.link_ad(db, ad)
    return ad.object_id, ad.link_confidence, ad.status


@pytest.mark.parametrize(
    "text",
    [
        "ЖК Алатау: квартиры от застройщика",
        "Жилой комплекс «Тулпар» принимает заявки",
        "Новый ЖК в центре, звоните",
        "жк",
        "Residence в центре города",
    ],
)
def test_a_generic_word_alone_never_links_a_post(db: Session, world: World, text: str) -> None:
    make_object(db, world.ust, "ЖК Нур")
    make_object(db, world.ust, "Жилой комплекс Residence Самал")

    object_id, confidence, status = link(db, world, text)

    assert (object_id, confidence) == (None, None) and status is AdStatus.verification


def test_an_object_whose_name_is_only_generic_words_is_never_matched(db: Session, world: World) -> None:
    make_object(db, world.ust, "ЖК")
    make_object(db, world.ust, "Жилой комплекс")
    assert link(db, world, "ЖК Алатау, жилой комплекс в центре")[0] is None


def test_all_distinctive_words_found_is_a_strong_match_whatever_the_generic_words(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "Жилой комплекс Нур Плаза")

    for text in ("Нур Плаза: старт продаж", "ЖК «Нур-Плаза» — квартиры", "квартиры в нур плаза"):
        object_id, confidence, status = link(db, world, text)
        assert (object_id, confidence, status) == (obj.id, 1.0, AdStatus.captured), text


def test_partial_names_are_not_proposed_below_the_minimum(db: Session, world: World) -> None:
    make_object(db, world.ust, "ЖК Алатау Парк Резиденс")  # one word of three found: 0.33
    make_object(db, world.ust, "ЖК Нур Сити Плаза")  # two of three: 0.67
    assert link(db, world, "Алатау, Нур Сити — скоро старт") == (None, None, AdStatus.verification)


def test_three_of_four_words_is_a_tentative_link_that_needs_verification(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "Алатау Парк Сити Плаза")
    assert link(db, world, "Алатау Парк Сити скоро") == (obj.id, 0.75, AdStatus.verification)


def test_a_typo_still_matches_but_a_different_name_does_not(db: Session, world: World) -> None:
    sure = make_object(db, world.ust, "ЖК Нурсат")
    make_object(db, world.ust, "ЖК Самал")

    object_id, confidence, status = link(db, world, "Продажа в ЖК Нурсаат")  # ratio 92
    assert object_id == sure.id and status is AdStatus.captured
    assert confidence is not None and 0.9 < confidence < 1

    assert link(db, world, "Продажа в ЖК Самат")[0] is None  # ratio 80: another name


def test_a_stricter_threshold_turns_a_typo_into_a_tentative_link(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "ЖК Нурсат")
    save_settings(db, {"link_confidence_threshold": 0.95})
    object_id, confidence, status = link(db, world, "Продажа в ЖК Нурсаат")
    assert (object_id, status) == (obj.id, AdStatus.verification)
    assert confidence is not None and 0.75 <= confidence < 0.95


def test_digits_and_single_characters_are_no_evidence(db: Session, world: World) -> None:
    make_object(db, world.ust, "Квартал 5")
    make_object(db, world.ust, "Дом А 7")
    make_object(db, world.ust, "Нур 7")  # "7" proves nothing, "Нур" must be there as well
    assert link(db, world, "5-комнатные квартиры, дом 7, подъезд А, квартал")[0] is None


def test_aliases_are_scored_like_names(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "Жилой комплекс Алатау", aliases=["Alatau Residence Park"])
    assert link(db, world, "Alatau Park — новая очередь")[0] == obj.id
    assert link(db, world, "Новинка Residence")[0] is None


@pytest.mark.parametrize("origin", [AdOrigin.collector, AdOrigin.citizen])
def test_a_post_nobody_reviewed_needs_a_person_to_confirm_a_guessed_link(
    db: Session, world: World, origin: AdOrigin
) -> None:
    obj = make_object(db, world.ust, "Жилой комплекс Нур Плаза")
    ad = add_ad(db, world.ust, "Нур Плаза: старт продаж", origin=origin)

    service.link_ad(db, ad)

    assert (ad.object_id, ad.link_method, ad.status) == (obj.id, LinkMethod.name, AdStatus.verification)


def test_a_collected_post_of_an_account_bound_by_staff_counts_at_once(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "Жилой комплекс Нур Плаза")
    account = SourceAccount(platform=Platform.telegram, handle="nur_plaza", object_id=obj.id, territory_id=world.ust.id)
    db.add(account)
    db.flush()
    ad = add_ad(db, world.ust, "Старт продаж", origin=AdOrigin.collector, source_account_id=account.id)

    service.link_ad(db, ad)

    assert (ad.object_id, ad.link_method, ad.status) == (obj.id, LinkMethod.account, AdStatus.captured)


def test_a_saved_search_bound_to_an_object_does_not_link_what_it_finds(db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "Жилой комплекс Нур Плаза")
    other = make_object(db, world.ust, "Жилой комплекс Самал Парк")
    search = SourceAccount(
        platform=Platform.aggregator, handle="poisk", object_id=obj.id, territory_id=world.ust.id
    )  # bound before the rule that forbids it
    db.add(search)
    db.flush()
    stranger = add_ad(db, world.ust, "Квартира в Самал Парк", origin=AdOrigin.collector, source_account_id=search.id)
    nameless = add_ad(db, world.ust, "Продаётся квартира", origin=AdOrigin.collector, source_account_id=search.id)

    service.link_ad(db, stranger)
    service.link_ad(db, nameless)

    # The listing is one of anybody's: it is linked by what it says, and as a guess a person has to confirm.
    assert (stranger.object_id, stranger.link_method, stranger.status) == (
        other.id,
        LinkMethod.name,
        AdStatus.verification,
    )
    assert (nameless.object_id, nameless.link_method) == (None, None)
