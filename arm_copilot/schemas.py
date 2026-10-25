"""Typed data shapes used across the agent."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Category = Literal[
    "cutoff_times",
    "pricing_tiers",
    "overdraft_rates",
    "authentication",
    "pretrade_requirements",
    "out_of_scope",
]

CATEGORIES = [
    "cutoff_times",
    "pricing_tiers",
    "overdraft_rates",
    "authentication",
    "pretrade_requirements",
]


class RouteDecision(BaseModel):
    """What the light routing model decides before any retrieval happens."""

    category: Category = Field(description="Which knowledge area the question belongs to, or out_of_scope.")
    search_query: str = Field(
        description="A short, self-contained search query that includes any currency, client tier or product mentioned."
    )
    currency: Optional[str] = Field(default=None, description="Currency code if the question names one.")
    client_tier: Optional[str] = Field(default=None, description="Client tier (A, B or C) if the question names one.")
    product: Optional[str] = Field(default=None, description="Product (e.g. bond, accumulator) if the question names one.")


class Citation(BaseModel):
    chunk_id: str = Field(description="The chunk_id of the clause being cited, copied exactly from the context.")
    quote: str = Field(description="A short phrase copied word for word from that clause that supports the statement.")


class Point(BaseModel):
    text: str = Field(description="One short statement for the user.")
    citations: list[Citation] = Field(default_factory=list)


class KeyValue(BaseModel):
    label: str
    value: str


class AnswerCard(BaseModel):
    """The structured answer shown to frontline staff."""

    cannot_answer: bool = Field(
        default=False,
        description="True if the context does not contain the answer. Never guess.",
    )
    headline: str = Field(default="", description="One-line direct answer.")
    key_values: list[KeyValue] = Field(
        default_factory=list, description="The key facts to highlight, e.g. label 'USD deposit cutoff (T)' value '12:00 HKT'."
    )
    points: list[Point] = Field(default_factory=list, description="Supporting statements, each with citations.")
    exceptions: list[str] = Field(default_factory=list, description="Exceptions or conditions that change the answer.")
    requires_signoff: bool = Field(default=False, description="True if a manager approval is needed.")
    signoff_by: Optional[str] = Field(default=None, description="Who must approve, if known from the context.")
    confidence: Literal["high", "low"] = Field(
        default="high", description="'low' if the context is ambiguous or details are missing from the question."
    )
    note: Optional[str] = Field(default=None, description="Why the question cannot be answered, or what to check.")


class SourceRef(BaseModel):
    chunk_id: str
    doc_id: str
    doc_title: str
    clause_id: str
    clause_title: str
    version: str
    effective_date: str


class FinalResponse(BaseModel):
    status: Literal["answered", "escalated", "out_of_scope"]
    message: str = ""
    card: Optional[AnswerCard] = None
    sources: list[SourceRef] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list, description="e.g. low_confidence, requires_signoff")
    attempts: int = 0
    trace: list[str] = Field(default_factory=list, description="Step-by-step decision trace for audit.")

    def cited_chunk_ids(self) -> set[str]:
        if not self.card:
            return set()
        return {c.chunk_id for p in self.card.points for c in p.citations}

    def answer_text(self) -> str:
        """All user-facing answer text in one string (used by the evaluator)."""
        if not self.card:
            return self.message
        parts = [self.card.headline]
        parts += [f"{kv.label} {kv.value}" for kv in self.card.key_values]
        parts += [p.text for p in self.card.points]
        parts += self.card.exceptions
        if self.card.signoff_by:
            parts.append(self.card.signoff_by)
        return "\n".join(x for x in parts if x)
