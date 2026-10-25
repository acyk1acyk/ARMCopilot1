"""Embed the knowledge base and upload it to Supabase.

    python scripts/ingest.py --dry-run     # parse and check the documents only (no keys needed)
    python scripts/ingest.py               # embed with the configured provider and upsert into Supabase

Before the first real run: create a Supabase project, run db/schema.sql in its SQL editor,
and fill in .env (see .env.example). Re-running is safe: rows are updated by chunk_id.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm_copilot.config import Settings  # noqa: E402
from arm_copilot.kb import Chunk, load_chunks  # noqa: E402

BATCH = 32


def rows_for_upsert(chunks: list[Chunk], vectors: list[list[float]], expected_dim: int) -> list[dict]:
    if len(chunks) != len(vectors):
        raise ValueError(f"{len(chunks)} chunks but {len(vectors)} embeddings")
    rows = []
    for chunk, vec in zip(chunks, vectors):
        if len(vec) != expected_dim:
            raise ValueError(f"{chunk.chunk_id}: embedding has {len(vec)} dimensions, expected {expected_dim}")
        rows.append(chunk.to_row(vec))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Parse and validate only; no network calls.")
    args = ap.parse_args()

    settings = Settings.from_env()
    chunks = load_chunks(settings.kb_dir)
    docs = sorted({c.doc_id for c in chunks})
    print(f"Parsed {len(chunks)} clauses from {len(docs)} documents: {', '.join(docs)}")
    if args.dry_run:
        for c in chunks:
            print(f"  {c.chunk_id:<18} {c.category:<22} {c.clause_title}")
        print("Dry run complete. Nothing was sent anywhere.")
        return 0

    from langchain_openai import OpenAIEmbeddings
    from supabase import create_client

    if not (settings.supabase_url and settings.supabase_service_key):
        print("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env", file=sys.stderr)
        return 1

    if settings.llm_provider == "openrouter":
        embedder = OpenAIEmbeddings(
            model=settings.embedding_model,
            openai_api_base=settings.openrouter_base_url,
            openai_api_key=settings.openrouter_api_key,
        )
    else:
        embedder = OpenAIEmbeddings(model=settings.embedding_model)
    client = create_client(settings.supabase_url, settings.supabase_service_key)

    total = 0
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i : i + BATCH]
        vectors = embedder.embed_documents([c.embedding_text for c in batch])
        rows = rows_for_upsert(batch, vectors, settings.embedding_dim)
        client.table("kb_chunks").upsert(rows, on_conflict="chunk_id").execute()
        total += len(rows)
        print(f"  uploaded {total}/{len(chunks)}")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
