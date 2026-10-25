"""Build the real agent (Supabase retriever + Anthropic models + Guardrails AI)."""

from __future__ import annotations

from typing import Optional

from .agent import AgentRunner, Deps
from .config import Settings
from .guardrail import CitationGuard
from .llm import make_answerer, make_router
from .retrieval import SupabaseRetriever


def create_agent(settings: Optional[Settings] = None, engine: str = "langgraph") -> AgentRunner:
    settings = settings or Settings.from_env()
    deps = Deps(
        route_fn=make_router(settings),
        answer_fn=make_answerer(settings),
        retriever=SupabaseRetriever(settings),
        guard=CitationGuard(require_guardrails=settings.require_guardrails),
        settings=settings,
    )
    return AgentRunner(deps, engine=engine)
