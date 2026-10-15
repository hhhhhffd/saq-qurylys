"""Text analysis for ad publications: dictionary matching by lemma sequences, phone and link extraction."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache

import phonenumbers
import pymorphy3

from app.models import Phrase
from app.phones import DEFAULT_REGION, normalize_phone

_WORD = re.compile(r"\w+")
_LINK = re.compile(
    r"(?:https?://|www\.)[^\s<>\"«»]+|\b(?:t\.me|wa\.me|instagram\.com|tiktok\.com)/[^\s<>\"«»]+",
    re.IGNORECASE,
)
_LINK_TRAILING = ".,;:!?)]}'"
# Text read from the photos of a publication is appended to `ad_post.text` after this marker (SPEC 10.2).
OCR_MARKER = "\n\n[OCR]\n"


@dataclass(frozen=True)
class Token:
    start: int
    end: int
    lemma: str


@dataclass(frozen=True)
class DictionaryMatch:
    phrase: Phrase
    start: int
    end: int
    text: str


@lru_cache(maxsize=1)
def _morph() -> pymorphy3.MorphAnalyzer:
    return pymorphy3.MorphAnalyzer()


@lru_cache(maxsize=50_000)
def _lemma(word: str) -> str:
    return str(_morph().parse(word)[0].normal_form)


def tokenize(text: str) -> list[Token]:
    """Words with their character offsets in `text` and their lemmas (case and е/ё folded)."""
    return [
        Token(match.start(), match.end(), _lemma(match.group().lower().replace("ё", "е")))
        for match in _WORD.finditer(text)
    ]


def _lemma_sequence(phrase_text: str) -> tuple[str, ...]:
    return tuple(token.lemma for token in tokenize(phrase_text))


def find_matches(text: str, phrases: Iterable[Phrase]) -> list[DictionaryMatch]:
    """Occurrences of the phrases (their text and every variant) in `text`, matched by lemma sequences.

    Matches never overlap: the longest wins, on a tie the heavier phrase. Offsets are Unicode code point
    positions in `text`.
    """
    by_first_lemma: dict[str, list[tuple[tuple[str, ...], Phrase]]] = {}
    for phrase in phrases:
        for form in (phrase.text, *phrase.variants):
            sequence = _lemma_sequence(form)
            if sequence:
                by_first_lemma.setdefault(sequence[0], []).append((sequence, phrase))

    tokens = tokenize(text)
    lemmas = [token.lemma for token in tokens]
    found: list[DictionaryMatch] = []
    for index, lemma in enumerate(lemmas):
        for sequence, phrase in by_first_lemma.get(lemma, ()):
            if tuple(lemmas[index : index + len(sequence)]) == sequence:
                start, end = tokens[index].start, tokens[index + len(sequence) - 1].end
                found.append(DictionaryMatch(phrase, start, end, text[start:end]))

    found.sort(key=lambda match: (-(match.end - match.start), -match.phrase.weight, match.start))
    accepted: list[DictionaryMatch] = []
    for match in found:
        if all(match.end <= other.start or match.start >= other.end for other in accepted):
            accepted.append(match)
    return sorted(accepted, key=lambda match: match.start)


def extract_phones(text: str) -> list[str]:
    """Valid Kazakhstan phone numbers found in `text` in E.164 format, in order of appearance, without repeats."""
    phones: list[str] = []
    for match in phonenumbers.PhoneNumberMatcher(text, DEFAULT_REGION):
        phone = normalize_phone(match.raw_string)
        if phone is not None and phone not in phones:
            phones.append(phone)
    return phones


def extract_links(text: str) -> list[str]:
    links: list[str] = []
    for match in _LINK.finditer(text):
        link = match.group().rstrip(_LINK_TRAILING)
        if link and link not in links:
            links.append(link)
    return links


def mentions_readiness(text: str, percent: int) -> bool:
    """Whether a sentence of the text speaks of readiness ("готов...") and names this percentage."""
    number = re.compile(rf"(?<![\d.,]){percent}(?:[.,]\d+)?\s*(?:%|процент)", re.IGNORECASE)
    return any(
        "готов" in sentence.lower() and number.search(sentence) for sentence in re.split(r"(?<=[.!?])\s+|\n", text)
    )


def to_utf16_offsets(text: str, offsets: Sequence[int]) -> list[int]:
    """Convert code point offsets into UTF-16 code unit offsets (JavaScript string indices)."""
    return [len(text[:offset].encode("utf-16-le")) // 2 for offset in offsets]


def split_ocr(text: str) -> tuple[str, str | None]:
    """(the publication's own text, the text read from its photos or None)."""
    own, marker, recognised = text.partition(OCR_MARKER)
    return own, recognised if marker else None
