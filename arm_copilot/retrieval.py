"""Retrievers: a Supabase/pgvector retriever for production and a keyword (BM25) retriever
that needs no network, used for offline tests and as a sanity-check baseline."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from .config import Settings
from .kb import Chunk


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float  # 0..1, higher is more relevant


class Retriever(Protocol):
    def search(self, query: str, category: Optional[str], k: int) -> list[ScoredChunk]: ...


# --------------------------------------------------------------------------------------
# Keyword retriever (BM25), pure Python
# --------------------------------------------------------------------------------------

_TOKEN = re.compile(r"[a-z0-9]+(?:[.:+][a-z0-9]+)*")
_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "has", "have",
    "how", "i", "if", "in", "is", "it", "of", "on", "or", "that", "the", "their", "this", "to", "what",
    "when", "which", "who", "whose", "will", "with", "need", "needs", "client", "wants", "want", "asks",
}


def _stem(tok: str) -> str:
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in _STOP]


class KeywordRetriever:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self._chunks = list(chunks)
        self._k1, self._b = k1, b
        self._docs = [Counter(tokenize(c.embedding_text)) for c in self._chunks]
        self._len = [sum(d.values()) for d in self._docs]
        self._avg = sum(self._len) / max(len(self._len), 1)
        df: Counter[str] = Counter()
        for d in self._docs:
            df.update(d.keys())
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, category: Optional[str], k: int) -> list[ScoredChunk]:
        q = tokenize(query)
        scored: list[tuple[float, Chunk]] = []
        for chunk, doc, dl in zip(self._chunks, self._docs, self._len):
            if category and chunk.category != category:
                continue
            s = 0.0
            for t in q:
                f = doc.get(t, 0)
                if not f:
                    continue
                s += self._idf.get(t, 0.0) * f * (self._k1 + 1) / (f + self._k1 * (1 - self._b + self._b * dl / self._avg))
            if s > 0:
                scored.append((s, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored:
            return []
        top = scored[0][0]
        return [ScoredChunk(c, s / top) for s, c in scored[:k]]


# --------------------------------------------------------------------------------------
# Supabase / pgvector retriever (needs network, keys and the schema in db/schema.sql)
# --------------------------------------------------------------------------------------


class SupabaseRetriever:
    def __init__(self, settings: Settings, embedder: Any = None, client: Any = None):
        self._settings = settings
        self._embedder = embedder
        self._client = client

    def _get_embedder(self) -> Any:
        if self._embedder is None:
            from langchain_openai import OpenAIEmbeddings  # lazy import

            if self._settings.llm_provider == "openrouter":
                self._embedder = OpenAIEmbeddings(
                    model=self._settings.embedding_model,
                    openai_api_base=self._settings.openrouter_base_url,
                    openai_api_key=self._settings.openrouter_api_key,
                )
            else:
                self._embedder = OpenAIEmbeddings(model=self._settings.embedding_model)
        return self._embedder

    def _get_client(self) -> Any:
        if self._client is None:
            from supabase import create_client  # lazy import

            if not (self._settings.supabase_url and self._settings.supabase_service_key):
                raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set (see .env.example).")
            self._client = create_client(self._settings.supabase_url, self._settings.supabase_service_key)
        return self._client

    CROSS_CATEGORY_EXTRA = 2  # clauses from other areas added when the question was routed to one area

    def _rpc(self, vector: list[float], k: int, category: Optional[str]) -> list[ScoredChunk]:
        resp = (
            self._get_client()
            .rpc("match_chunks", {"query_embedding": vector, "match_count": k, "filter_category": category})
            .execute()
        )
        out: list[ScoredChunk] = []
        for row in resp.data or []:
            sim = float(row.get("similarity", 0.0))
            if sim >= self._settings.min_similarity:
                out.append(ScoredChunk(Chunk.from_row(row), sim))
        return out

    def search(self, query: str, category: Optional[str], k: int) -> list[ScoredChunk]:
        vector = self._get_embedder().embed_query(query)
        out = self._rpc(vector, k, category)
        if category is not None and self.CROSS_CATEGORY_EXTRA > 0:
            # Safety net: the router can pick a neighbouring area (pre-trade instead of pricing, for example).
            seen = {s.chunk.chunk_id for s in out}
            extras = [s for s in self._rpc(vector, k, None) if s.chunk.chunk_id not in seen]
            out.extend(extras[: self.CROSS_CATEGORY_EXTRA])
        return out
