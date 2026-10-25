"""Model calls (Anthropic direct, or any model through OpenRouter, via LangChain). Model tiering: a light model routes, a stronger one answers.

These two functions are the only places that talk to a model. The rest of the agent receives them as
plain callables, which is what lets the control flow be tested offline with stand-ins.
"""

from __future__ import annotations

from typing import Callable, Optional

from .config import Settings
from .prompts import ROUTER_SYSTEM, build_answer_messages
from .retrieval import ScoredChunk
from .schemas import AnswerCard, RouteDecision

RouteFn = Callable[[str], RouteDecision]
AnswerFn = Callable[[str, list[ScoredChunk], Optional[str]], AnswerCard]


def _chat_model(settings: Settings, model_name: str, max_tokens: int, timeout: int):
    """Build a chat model for the configured provider. Imports are lazy so tests need no packages."""
    provider = settings.llm_provider
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model_name, temperature=0.0, max_tokens=max_tokens, timeout=timeout, max_retries=1)
    if provider == "openrouter":
        if "/" not in model_name:
            raise ValueError(
                f"'{model_name}' is not an OpenRouter model name. Use the 'vendor/model' form "
                "from openrouter.ai/models in ARM_ROUTER_MODEL and ARM_ANSWER_MODEL."
            )
        key = settings.openrouter_api_key
        if not key:
            raise ValueError("OPENROUTER_API_KEY is not set.")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name, api_key=key, base_url=settings.openrouter_base_url,
            temperature=0.0, max_tokens=max_tokens, timeout=timeout, max_retries=1,
        )
    raise ValueError(f"Unknown ARM_LLM_PROVIDER '{provider}'. Use 'anthropic' or 'openrouter'.")


def _structured(model, schema):
    # function_calling is the most widely supported structured-output mode across OpenRouter models.
    try:
        return model.with_structured_output(schema, method="function_calling")
    except TypeError:  # ChatAnthropic does not take this argument
        return model.with_structured_output(schema)


def make_router(settings: Settings) -> RouteFn:
    model = _chat_model(settings, settings.router_model, 300, 30)
    structured = _structured(model, RouteDecision)

    def route(question: str) -> RouteDecision:
        result = structured.invoke([("system", ROUTER_SYSTEM), ("human", question)])
        if result is None:
            raise ValueError("The routing model returned no structured output.")
        return result if isinstance(result, RouteDecision) else RouteDecision.model_validate(result)

    return route


def make_answerer(settings: Settings) -> AnswerFn:
    model = _chat_model(settings, settings.answer_model, settings.max_answer_tokens, 60)
    structured = _structured(model, AnswerCard)

    def answer(question: str, chunks: list[ScoredChunk], feedback: Optional[str]) -> AnswerCard:
        result = structured.invoke(build_answer_messages(question, chunks, feedback))
        if result is None:
            raise ValueError("The answer model returned no structured output.")
        return result if isinstance(result, AnswerCard) else AnswerCard.model_validate(result)

    return answer
