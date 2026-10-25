"""Deterministic citation and number checks (no model involved).

An answer card passes only if:
  1. it has at least one point, and every point has at least one citation;
  2. every citation points to a clause that was actually retrieved;
  3. every citation quote appears word for word in that clause;
  4. every time, percentage, bps value, currency amount and duration in the answer also
     appears in the cited clauses (or in the user's own question).

This is the "answers without documented backing are blocked" rule from the project design.
It is plain Python so it can be tested without any model or network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from .kb import Chunk
from .schemas import AnswerCard

_WS = re.compile(r"\s+")
_TRANSLATE = str.maketrans(
    {"*": "", "`": "", "|": " ", "“": '"', "”": '"', "’": "'", "‘": "'", "–": "-", "—": "-"}
)

_RISKY = [
    re.compile(r"\b\d{1,2}:\d{2}\b"),                                           # times, e.g. 15:30
    re.compile(r"\b\d+(?:\.\d+)?%"),                                            # percentages
    re.compile(r"\b\d+(?:\.\d+)?bps\b"),                                        # basis points
    re.compile(r"\b(?:usd|hkd|cnh|eur|gbp|jpy|aud)\s?\d+(?:\.\d+)?(?:\s?(?:million|billion|m|k))?\b"),  # amounts
    re.compile(r"\b\d+\s?(?:business days?|days?|months?|years?|hours?|minutes?)\b"),  # durations
]

MIN_QUOTE_CHARS = 8


@dataclass(frozen=True)
class Violation:
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


def canon(text: str) -> str:
    """Lowercase, strip markdown, collapse whitespace, and make number formatting comparable."""
    t = text.translate(_TRANSLATE).lower()
    t = _WS.sub(" ", t).strip()
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)          # 2,000 -> 2000
    t = re.sub(r"(\d)\s+(%|bps\b)", r"\1\2", t)        # '5 bps' -> '5bps', '20 %' -> '20%'
    return t


def risky_tokens(text: str) -> list[str]:
    t = canon(text)
    found: list[str] = []
    for pat in _RISKY:
        found.extend(m.group(0) for m in pat.finditer(t))
    seen: set[str] = set()
    return [x for x in found if not (x in seen or seen.add(x))]


def _present(token: str, haystack: str) -> bool:
    return re.search(r"(?<![\w.:])" + re.escape(token) + r"(?!\w)", haystack) is not None


def quote_in_chunk(quote: str, content: str) -> bool:
    q = canon(quote)
    return len(q) >= MIN_QUOTE_CHARS and q in canon(content)


def check_grounding(card: AnswerCard, chunks_by_id: Mapping[str, Chunk], question: str = "") -> list[Violation]:
    """Return every reason the card is not fully backed by the retrieved clauses (empty list = pass)."""
    if card.cannot_answer:
        return []

    violations: list[Violation] = []
    q = canon(question)

    if not card.points:
        violations.append(Violation("no_points", "The answer has no supporting points with citations."))

    cited_texts: dict[str, str] = {}
    for i, point in enumerate(card.points, start=1):
        if not point.citations:
            violations.append(Violation("uncited_point", f"Point {i} has no citation: '{point.text[:60]}'"))
            continue
        point_texts: list[str] = []
        for c in point.citations:
            chunk = chunks_by_id.get(c.chunk_id)
            if chunk is None:
                violations.append(Violation("unknown_chunk", f"Point {i} cites '{c.chunk_id}', which was not retrieved."))
                continue
            if not quote_in_chunk(c.quote, chunk.content):
                violations.append(
                    Violation("quote_mismatch", f"Point {i}: the quote '{c.quote[:60]}' is not word for word in {c.chunk_id}.")
                )
            canon_content = canon(chunk.content)
            cited_texts[c.chunk_id] = canon_content
            point_texts.append(canon_content)
        support = "\n".join(point_texts) + "\n" + q
        for tok in risky_tokens(point.text):
            if not _present(tok, support):
                violations.append(Violation("ungrounded_value", f"Point {i} states '{tok}', which is not in its cited clauses."))

    # Headline and key values are checked against everything that was cited.
    all_cited = "\n".join(cited_texts.values()) + "\n" + q
    summary_parts = [("headline", card.headline)] + [(f"key value '{kv.label}'", kv.value) for kv in card.key_values]
    for where, text in summary_parts:
        for tok in risky_tokens(text):
            if not _present(tok, all_cited):
                violations.append(Violation("ungrounded_value", f"The {where} states '{tok}', which is not in any cited clause."))
    for exc in card.exceptions:
        for tok in risky_tokens(exc):
            if not _present(tok, all_cited):
                violations.append(Violation("ungrounded_value", f"An exception states '{tok}', which is not in any cited clause."))
    return violations


def format_violations(violations: list[Violation]) -> str:
    return "\n".join(f"- {v}" for v in violations)
