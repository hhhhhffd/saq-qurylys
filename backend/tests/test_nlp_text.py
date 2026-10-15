from app.models import Phrase
from app.models.enums import PhraseCategory
from app.modules.nlp.text import extract_links, extract_phones, find_matches, to_utf16_offsets


def phrase(category: PhraseCategory, text: str, variants: list[str], weight: int = 10) -> Phrase:
    return Phrase(category=category, text=text, variants=variants, weight=weight, is_active=True)


BOOKING = phrase(PhraseCategory.booking, "бронирование", ["бронь", "забронировать", "бронирование квартиры"], 10)
DOWN_PAYMENT = phrase(PhraseCategory.down_payment, "первоначальный взнос", ["первый взнос"], 7)
INSTALLMENT = phrase(PhraseCategory.installment, "рассрочка", ["в рассрочку", "рассрочка без процентов"], 8)


def test_inflected_variant_hits_the_phrase_with_correct_offsets() -> None:
    text = "Успейте, забронируйте квартиру до конца месяца!"
    [match] = find_matches(text, [BOOKING])
    assert match.phrase is BOOKING
    assert match.text == "забронируйте"
    assert text[match.start : match.end] == "забронируйте"


def test_case_yo_and_word_forms_are_ignored() -> None:
    text = "ПЕРВОНАЧАЛЬНЫЙ ВЗНОС от 10%, а также Первого взноса не требуется. Рассрочка!"
    matches = find_matches(text, [DOWN_PAYMENT, INSTALLMENT])
    assert [(m.phrase.category, m.text) for m in matches] == [
        (PhraseCategory.down_payment, "ПЕРВОНАЧАЛЬНЫЙ ВЗНОС"),
        (PhraseCategory.down_payment, "Первого взноса"),
        (PhraseCategory.installment, "Рассрочка"),
    ]
    assert all(text[m.start : m.end] == m.text for m in matches)


def test_longest_variant_wins_and_matches_do_not_overlap() -> None:
    text = "Рассрочка без процентов на 3 года"
    [match] = find_matches(text, [INSTALLMENT])
    assert match.text == "Рассрочка без процентов"


def test_phrase_words_must_follow_each_other() -> None:
    assert find_matches("Взнос первоначальный не нужен", [DOWN_PAYMENT]) == []
    assert find_matches("Купите бронированную дверь и сейф", [BOOKING]) == []
    assert find_matches("", [BOOKING]) == []


def test_repeated_phrase_gives_a_hit_per_occurrence() -> None:
    text = "Бронь открыта. Бронь без комиссии."
    assert [m.start for m in find_matches(text, [BOOKING])] == [0, 15]


def test_phones_are_normalized_to_e164_without_repeats() -> None:
    text = "Звоните 8 (777) 123-45-67 или +7 701 555 12 34, ещё раз 87771234567; номер 12345 не телефон"
    assert extract_phones(text) == ["+77771234567", "+77015551234"]
    assert extract_phones("без телефонов") == []


def test_links_lose_trailing_punctuation() -> None:
    text = "Смотрите https://example.com/a?b=1, канал t.me/zhk_alatau/12. Сайт www.site.kz)."
    assert extract_links(text) == ["https://example.com/a?b=1", "t.me/zhk_alatau/12", "www.site.kz"]


def test_utf16_offsets_count_astral_characters_twice() -> None:
    text = "😀 Бронь"
    [match] = find_matches(text, [BOOKING])
    assert (match.start, match.end) == (2, 7)
    assert to_utf16_offsets(text, [match.start, match.end]) == [3, 8]
