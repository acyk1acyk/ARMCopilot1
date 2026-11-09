"""Settings, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

try:  # optional: python-dotenv is in requirements.txt but is not needed for tests
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except Exception:  # pragma: no cover - missing package or unreadable file
    pass


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    kb_dir: Path = PROJECT_ROOT / "knowledge_base"

    # Which service the chat models go through: "anthropic" (direct) or "openrouter" (one key, many models).
    llm_provider: str = "anthropic"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Model tiering: a light model for routing, a stronger one for cited answers.
    # With OpenRouter, names look like "vendor/model" - copy them from openrouter.ai/models.
    router_model: str = "claude-haiku-5-5"
    answer_model: str = "claude-sonnet-5-5"

    # Embeddings for the Supabase vector store (OpenAI text-embedding-3-small = 1536 dims).
    # OpenRouter model IDs are provider-prefixed; direct OpenAI users may override this in .env.
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dim: int = 1536
    openrouter_api_key: str = ""

    supabase_url: str = ""
    supabase_service_key: str = ""

    # Retrieval
    top_k: int = 8
    min_similarity: float = 0.30  # cosine similarity; tune with the 30-question set in November

    # Hard limits that keep cost and behaviour predictable
    max_answer_attempts: int = 2   # answer + at most one retry after a failed citation check
    recursion_limit: int = 12      # absolute cap on graph steps per question
    max_question_chars: int = 800  # longer inputs are refused before any model call
    max_answer_tokens: int = 900

    # Guardrails AI must be installed unless this is explicitly switched off (offline tests only).
    require_guardrails: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        d = cls()
        return cls(
            kb_dir=Path(os.getenv("ARM_KB_DIR", str(d.kb_dir))),
            llm_provider=os.getenv("ARM_LLM_PROVIDER", d.llm_provider).strip().lower(),
            openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", d.openrouter_base_url),
            router_model=os.getenv("ARM_ROUTER_MODEL", d.router_model),
            answer_model=os.getenv("ARM_ANSWER_MODEL", d.answer_model),
            embedding_model=os.getenv("ARM_EMBEDDING_MODEL", d.embedding_model),
            embedding_dim=_env_int("ARM_EMBEDDING_DIM", d.embedding_dim),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
            supabase_url=os.getenv("SUPABASE_URL", ""),
            supabase_service_key=os.getenv("SUPABASE_SERVICE_KEY", ""),
            top_k=_env_int("ARM_TOP_K", d.top_k),
            min_similarity=_env_float("ARM_MIN_SIMILARITY", d.min_similarity),
            max_answer_attempts=_env_int("ARM_MAX_ANSWER_ATTEMPTS", d.max_answer_attempts),
            recursion_limit=_env_int("ARM_RECURSION_LIMIT", d.recursion_limit),
            max_question_chars=_env_int("ARM_MAX_QUESTION_CHARS", d.max_question_chars),
            max_answer_tokens=_env_int("ARM_MAX_ANSWER_TOKENS", d.max_answer_tokens),
            require_guardrails=os.getenv("ARM_ALLOW_NO_GUARDRAILS", "0") != "1",
        )
