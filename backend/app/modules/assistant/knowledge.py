"""Officer guide for the assistant: markdown files split into sections and searched with BM25 over lemmas.

File format: the first line is `# Title`; an optional `<!-- page: /work -->` names the SAQ path the file is about;
every `## ` section is a chunk. Text before the first section is a chunk of its own.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.modules.nlp.text import tokenize

GUIDE_DIR = Path(__file__).parent / "guide"
BM25_K1 = 1.5
BM25_B = 0.75
_PAGE = re.compile(r"<!--\s*page:\s*(\S+)\s*-->")


@dataclass(frozen=True)
class Chunk:
    id: str
    title: str
    page: str | None
    text: str


def _terms(text: str) -> list[str]:
    """Lemmas of the words that can carry meaning: one-letter tokens (prepositions, 'и', 'в') are dropped."""
    return [token.lemma for token in tokenize(text) if len(token.lemma) > 1]


def _split(path: Path) -> list[Chunk]:
    lines = path.read_text(encoding="utf-8").splitlines()
    file_title = path.stem
    if lines and lines[0].startswith("# "):
        file_title = lines[0][2:].strip()
        lines = lines[1:]
    page: str | None = None
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in lines:
        match = _PAGE.fullmatch(line.strip())
        if match:
            page = match[1]
        elif line.startswith("## "):
            sections.append((line[3:].strip(), []))
        else:
            sections[-1][1].append(line)
    chunks: list[Chunk] = []
    for title, body in sections:
        text = "\n".join(body).strip()
        if title is None and not text:
            continue
        full_title = file_title if title is None else f"{file_title} — {title}"
        chunks.append(Chunk(f"{path.stem}#{len(chunks)}", full_title, page, text))
    return chunks


class GuideIndex:
    def __init__(self, directory: Path) -> None:
        self.chunks: list[Chunk] = []
        for path in sorted(directory.glob("*.md")):
            self.chunks.extend(_split(path))
        # The title counts as text of the chunk.
        self._counts = [Counter(_terms(f"{chunk.title}\n{chunk.text}")) for chunk in self.chunks]
        self._lengths = [sum(counts.values()) for counts in self._counts]
        self._avg_length = sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        document_frequency: Counter[str] = Counter()
        for counts in self._counts:
            document_frequency.update(counts.keys())
        total = len(self.chunks)
        self._idf = {
            term: math.log(1 + (total - freq + 0.5) / (freq + 0.5)) for term, freq in document_frequency.items()
        }

    def search(self, query: str, k: int) -> list[Chunk]:
        """Up to `k` chunks that share at least one lemma with the query, best first."""
        terms = set(_terms(query))
        scored: list[tuple[float, int]] = []
        for index, counts in enumerate(self._counts):
            norm = 1 - BM25_B + BM25_B * self._lengths[index] / self._avg_length
            score = 0.0
            for term in terms:
                freq = counts.get(term, 0)
                if freq:
                    score += self._idf[term] * freq * (BM25_K1 + 1) / (freq + BM25_K1 * norm)
            if score > 0:
                scored.append((score, index))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [self.chunks[index] for _, index in scored[:k]]


def load_index(directory: Path) -> GuideIndex:
    return GuideIndex(directory)


@lru_cache(maxsize=1)
def guide_index() -> GuideIndex:
    """The production index, built once per process."""
    return load_index(GUIDE_DIR)


def search(query: str, k: int = 4) -> list[Chunk]:
    return guide_index().search(query, k)
