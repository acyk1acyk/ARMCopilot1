"""The ARM Copilot agent: route -> retrieve -> answer -> validate (with one retry) -> finalize.

All decision logic lives in plain node functions that take and return a state dict. ``build_graph``
wires the same functions into a LangGraph StateGraph, and ``run_sequential`` runs them in a simple
loop, which is how the control flow is tested without LangGraph installed.

Hard limits (see config.py): at most ``max_answer_attempts`` answer calls per question, and a
``recursion_limit`` on graph steps. If an answer cannot be backed by citations, the agent escalates
to a human and lists the clauses to read instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, TypedDict

from .config import Settings
from .guardrail import CitationGuard
from .kb import Chunk
from .retrieval import Retriever, ScoredChunk
from .schemas import AnswerCard, FinalResponse, RouteDecision, SourceRef

MSG_NO_SOURCE = (
    "I couldn't find this in the knowledge base, so I won't guess. "
    "Please check with your Desk Head or the policy owner."
)
MSG_UNVERIFIED = (
    "I found related clauses but couldn't give an answer that is fully backed by quotes from them. "
    "Please read the clauses listed below or check with your Desk Head."
)
MSG_OUT_OF_SCOPE = (
    "This looks outside what ARM Copilot covers (cutoff times, pricing tiers, overdraft rates, "
    "authentication, pre-trade requirements). Please check the relevant policy or your Desk Head."
)
MSG_LOW_CONFIDENCE = "Low confidence: the clauses do not fully settle this. Please confirm with your Desk Head before acting."


class AgentState(TypedDict, total=False):
    question: str
    route: RouteDecision
    chunks: list[ScoredChunk]
    card: Optional[AnswerCard]
    feedback: Optional[str]
    violations: list[str]
    attempts: int
    outcome: str  # answered | escalated | out_of_scope (set when the run is decided)
    message: str
    trace: list[str]
    response: FinalResponse


@dataclass
class Deps:
    route_fn: Callable[[str], RouteDecision]
    answer_fn: Callable[[str, list[ScoredChunk], Optional[str]], AnswerCard]
    retriever: Retriever
    guard: CitationGuard
    settings: Settings


# --------------------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------------------


def _t(state: AgentState, line: str) -> list[str]:
    return list(state.get("trace", [])) + [line]


def route_node(state: AgentState, deps: Deps) -> dict[str, Any]:
    q = (state.get("question") or "").strip()
    if not q:
        return {"outcome": "escalated", "message": "Please type a question.", "trace": _t(state, "route: empty question")}
    if len(q) > deps.settings.max_question_chars:
        return {
            "outcome": "escalated",
            "message": f"That question is too long (limit {deps.settings.max_question_chars} characters). Please shorten it.",
            "trace": _t(state, "route: question too long, no model call made"),
        }
    try:
        route = deps.route_fn(q)
    except Exception as exc:
        return {
            "outcome": "escalated",
            "message": "I couldn't classify that question. Please try again or check with your Desk Head.",
            "trace": _t(state, f"route: failed ({type(exc).__name__})"),
        }
    line = f"route: category={route.category} query='{route.search_query}'"
    if route.category == "out_of_scope":
        return {"route": route, "outcome": "out_of_scope", "message": MSG_OUT_OF_SCOPE, "trace": _t(state, line)}
    return {"route": route, "trace": _t(state, line)}


def retrieve_node(state: AgentState, deps: Deps) -> dict[str, Any]:
    route = state["route"]
    query = route.search_query or state["question"]
    k = deps.settings.top_k
    chunks = deps.retriever.search(query, route.category, k)
    note = ""
    if not chunks:  # the router may have picked the wrong area: look across everything once
        chunks = deps.retriever.search(query, None, k)
        note = " (widened to all areas)"
    ids = ", ".join(c.chunk.chunk_id for c in chunks) or "none"
    trace = _t(state, f"retrieve: {len(chunks)} clauses{note}: {ids}")
    if not chunks:
        return {"chunks": [], "outcome": "escalated", "message": MSG_NO_SOURCE, "trace": trace}
    return {"chunks": chunks, "trace": trace}


def answer_node(state: AgentState, deps: Deps) -> dict[str, Any]:
    attempts = state.get("attempts", 0) + 1
    try:
        card = deps.answer_fn(state["question"], state["chunks"], state.get("feedback"))
        return {"card": card, "attempts": attempts, "trace": _t(state, f"answer: attempt {attempts}")}
    except Exception as exc:
        return {
            "card": None,
            "attempts": attempts,
            "trace": _t(state, f"answer: attempt {attempts} failed ({type(exc).__name__})"),
        }


def validate_node(state: AgentState, deps: Deps) -> dict[str, Any]:
    card = state.get("card")
    attempts = state.get("attempts", 0)
    if card is None:
        fb = "The previous output could not be turned into the answer card format. Return a complete AnswerCard."
        return {"violations": [fb], "feedback": fb, "trace": _t(state, "validate: no usable card")}
    if card.cannot_answer:
        why = card.note or "the clauses do not contain the answer"
        return {
            "outcome": "escalated",
            "message": f"The retrieved clauses don't answer this: {why}. Please check with your Desk Head.",
            "trace": _t(state, "validate: model reports the clauses do not contain the answer"),
        }
    by_id = {sc.chunk.chunk_id: sc.chunk for sc in state["chunks"]}
    result = deps.guard.validate(card, by_id, state["question"])
    if result.passed:
        return {"outcome": "answered", "violations": [], "trace": _t(state, f"validate[{result.engine}]: passed")}
    codes = ", ".join(sorted({v.code for v in result.violations})) or "failed"
    feedback = "\n".join(f"- {v}" for v in result.violations)
    update: dict[str, Any] = {
        "violations": [str(v) for v in result.violations],
        "feedback": feedback,
        "trace": _t(state, f"validate[{result.engine}]: failed ({codes}) after attempt {attempts}"),
    }
    if result.error:  # the guard itself broke: retrying the model will not help
        update.update(outcome="escalated", message=MSG_UNVERIFIED)
    return update


def finalize_node(state: AgentState, deps: Deps) -> dict[str, Any]:
    outcome = state.get("outcome")
    chunks = state.get("chunks", [])
    by_id = {sc.chunk.chunk_id: sc.chunk for sc in chunks}
    attempts = state.get("attempts", 0)
    card = state.get("card")

    if outcome is None:  # validation kept failing and the attempt budget is spent
        outcome = "escalated"
        state = {**state, "message": MSG_UNVERIFIED}

    trace = _t(state, f"finalize: {outcome}")

    if outcome == "answered" and card is not None:
        cited: list[str] = []
        for p in card.points:
            for c in p.citations:
                if c.chunk_id not in cited:
                    cited.append(c.chunk_id)
        flags = []
        message = ""
        if card.confidence == "low":
            flags.append("low_confidence")
            message = MSG_LOW_CONFIDENCE
        if card.requires_signoff:
            flags.append("requires_signoff")
        response = FinalResponse(
            status="answered",
            message=message,
            card=card,
            sources=[_source_ref(by_id[i]) for i in cited if i in by_id],
            flags=flags,
            attempts=attempts,
            trace=trace,
        )
    else:
        status = "out_of_scope" if outcome == "out_of_scope" else "escalated"
        response = FinalResponse(
            status=status,
            message=state.get("message") or MSG_UNVERIFIED,
            card=None,
            sources=[_source_ref(sc.chunk) for sc in chunks[:3]],
            flags=["escalated"],
            attempts=attempts,
            trace=trace,
        )
    return {"response": response, "trace": trace}


def _source_ref(c: Chunk) -> SourceRef:
    return SourceRef(
        chunk_id=c.chunk_id,
        doc_id=c.doc_id,
        doc_title=c.doc_title,
        clause_id=c.clause_id,
        clause_title=c.clause_title,
        version=c.version,
        effective_date=c.effective_date,
    )


# --------------------------------------------------------------------------------------
# Routing between nodes
# --------------------------------------------------------------------------------------


def after_route(state: AgentState) -> str:
    return "finalize" if state.get("outcome") else "retrieve"


def after_retrieve(state: AgentState) -> str:
    return "finalize" if state.get("outcome") else "answer"


def after_validate(deps: Deps) -> Callable[[AgentState], str]:
    def _after(state: AgentState) -> str:
        if state.get("outcome"):
            return "finalize"
        if state.get("attempts", 0) < deps.settings.max_answer_attempts:
            return "answer"  # retry once with the checker's feedback
        return "finalize"

    return _after


# --------------------------------------------------------------------------------------
# Runners
# --------------------------------------------------------------------------------------


class RecursionLimitExceeded(RuntimeError):
    pass


def run_sequential(deps: Deps, initial: AgentState) -> AgentState:
    """Run the same nodes and routing rules in a plain loop (no LangGraph)."""
    state: AgentState = dict(initial)  # type: ignore[assignment]
    nodes = {
        "route": lambda s: route_node(s, deps),
        "retrieve": lambda s: retrieve_node(s, deps),
        "answer": lambda s: answer_node(s, deps),
        "validate": lambda s: validate_node(s, deps),
        "finalize": lambda s: finalize_node(s, deps),
    }
    nxt = {
        "route": after_route,
        "retrieve": after_retrieve,
        "answer": lambda s: "validate",
        "validate": after_validate(deps),
        "finalize": lambda s: "END",
    }
    node, steps = "route", 0
    while node != "END":
        steps += 1
        if steps > deps.settings.recursion_limit:
            raise RecursionLimitExceeded(f"More than {deps.settings.recursion_limit} steps")
        state.update(nodes[node](state))  # type: ignore[typeddict-item]
        node = nxt[node](state)
    return state


def build_graph(deps: Deps):
    """Wire the nodes into a LangGraph StateGraph (requires `langgraph`)."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AgentState)
    graph.add_node("classify", lambda s: route_node(s, deps))
    graph.add_node("retrieve", lambda s: retrieve_node(s, deps))
    graph.add_node("answer", lambda s: answer_node(s, deps))
    graph.add_node("validate", lambda s: validate_node(s, deps))
    graph.add_node("finalize", lambda s: finalize_node(s, deps))

    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", after_route, {"retrieve": "retrieve", "finalize": "finalize"})
    graph.add_conditional_edges("retrieve", after_retrieve, {"answer": "answer", "finalize": "finalize"})
    graph.add_edge("answer", "validate")
    graph.add_conditional_edges("validate", after_validate(deps), {"answer": "answer", "finalize": "finalize"})
    graph.add_edge("finalize", END)
    return graph.compile()


class AgentRunner:
    def __init__(self, deps: Deps, engine: str = "langgraph"):
        if engine not in ("langgraph", "sequential"):
            raise ValueError("engine must be 'langgraph' or 'sequential'")
        self.deps = deps
        self.engine = engine
        self._graph = build_graph(deps) if engine == "langgraph" else None

    def ask(self, question: str) -> FinalResponse:
        initial: AgentState = {"question": question, "attempts": 0, "trace": []}
        try:
            if self._graph is not None:
                final = self._graph.invoke(initial, config={"recursion_limit": self.deps.settings.recursion_limit})
            else:
                final = run_sequential(self.deps, initial)
        except Exception as exc:
            if isinstance(exc, RecursionLimitExceeded) or type(exc).__name__ == "GraphRecursionError":
                return FinalResponse(
                    status="escalated",
                    message="This took too many steps, so I stopped. Please check with your Desk Head.",
                    flags=["escalated"],
                    trace=["stopped: step limit reached"],
                )
            raise
        return final["response"]
