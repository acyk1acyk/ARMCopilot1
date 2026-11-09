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
    re.compile(r"\b(?:usd|hkd|cnh|eur|gbp|jpy|aud)\s?\d+(?:\.\d+)?(?:\s?(?:million|billion|m|k))?\b(?!:\d)"),  # amounts (not "HKD 17:00", which is a currency next to a time)
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


_ELLIPSIS = re.compile(r"\.{3,}|\u2026")
MIN_FRAGMENT_CHARS = 3


def _row_cells_match(quote: str, content: str) -> bool:
    """A quote that is part of one table row: every cell is copied exactly, in order, from the same row.

    This accepts a row with some columns left out, for example `| Hong Kong listed equities | 0.20% (min HKD 200) |`
    taken from a row that also has a Tier A and a Tier C column. Cells must still match whole cells exactly.
    """
    if "|" not in quote:
        return False
    cells = [canon(c).strip() for c in quote.split("|")]
    cells = [c for c in cells if c]
    if len(cells) < 2 or len(" ".join(cells)) < MIN_QUOTE_CHARS:
        return False
    for line in content.splitlines():
        if "|" not in line:
            continue
        row = [canon(c).strip() for c in line.split("|")]
        it = iter(c for c in row if c)
        if all(any(c == r for r in it) for c in cells):  # cells appear in the row, in order
            return True
    return False


def quote_in_chunk(quote: str, content: str) -> bool:
    """True if the quote is word for word in the clause.

    A quote may skip text with '...': then every fragment must appear word for word, in the same order.
    Each fragment must be long enough to mean something, so '...' cannot be used to smuggle in claims.
    A table-row quote may leave out whole columns (see _row_cells_match).
    """
    haystack = canon(content)
    fragments = [canon(f).strip(" .,;:") for f in _ELLIPSIS.split(quote)]
    fragments = [f for f in fragments if f]
    if not fragments or len(canon(quote)) < MIN_QUOTE_CHARS:
        return False
    pos, ok = 0, True
    for f in fragments:
        if len(f) < MIN_FRAGMENT_CHARS and len(fragments) > 1:
            ok = False
            break
        i = haystack.find(f, pos)
        if i < 0:
            ok = False
            break
        pos = i + len(f)
    return ok or _row_cells_match(quote, content)


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
    # Exceptions flag conditions from related clauses, so their numbers may come from any retrieved clause
    # (an invented number is still blocked because it will not be in any of them).
    all_retrieved = "\n".join(canon(c.content) for c in chunks_by_id.values()) + "\n" + q
    for exc in card.exceptions:
        for tok in risky_tokens(exc):
            if not _present(tok, all_retrieved):
                violations.append(Violation("ungrounded_value", f"An exception states '{tok}', which is not in any retrieved clause."))
    return violations


def format_violations(violations: list[Violation]) -> str:
    return "\n".join(f"- {v}" for v in violations)
