"""Scoring for the internal test set (eval/test_set_v1.json). Pure Python, no network."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .grounding import canon
from .retrieval import Retriever
from .schemas import FinalResponse


def load_cases(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _fact_present(fact: Any, text: str) -> bool:
    """A fact is a phrase, or a list of acceptable alternative phrases."""
    options = fact if isinstance(fact, list) else [fact]
    haystack = canon(text)
    return any(canon(o) in haystack for o in options)


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    problems: list[str] = field(default_factory=list)
    status: str = ""
    attempts: int = 0


def evaluate_case(case: dict[str, Any], resp: FinalResponse) -> CaseResult:
    problems: list[str] = []
    expect_escalate = bool(case.get("expect_escalate", False))

    if expect_escalate:
        if resp.status == "answered":
            problems.append("expected the agent to escalate instead of answering")
    else:
        if resp.status != "answered":
            problems.append(f"expected an answer but got status '{resp.status}': {resp.message}")
        else:
            text = resp.answer_text()
            for fact in case.get("expected_facts", []):
                if not _fact_present(fact, text):
                    problems.append(f"missing fact: {fact}")
            missing = [c for c in case.get("expected_citations", []) if c not in resp.cited_chunk_ids()]
            if missing:
                problems.append(f"missing citations: {missing}")
            if case.get("expect_signoff") and not (resp.card and resp.card.requires_signoff):
                problems.append("expected requires_signoff to be true")
    return CaseResult(case["id"], not problems, problems, resp.status, resp.attempts)


def retrieval_hit(case: dict[str, Any], retriever: Retriever, k: int = 5) -> tuple[bool, list[str]]:
    """Did retrieval (with the case's category as filter) return every clause the answer needs?"""
    expected = case.get("expected_citations", [])
    if not expected:
        return True, []
    got = [s.chunk.chunk_id for s in retriever.search(case["question"], case.get("category"), k)]
    return all(e in got for e in expected), got
