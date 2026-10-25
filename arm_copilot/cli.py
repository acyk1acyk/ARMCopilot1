"""Command line: ask a question, or inspect retrieval without any API keys.

    python -m arm_copilot.cli "What is the USD deposit cutoff for same-day value?"
    python -m arm_copilot.cli --retrieve-only "USD deposit cutoff"     # keyword search, no keys needed
"""

from __future__ import annotations

import argparse
import json

from .config import Settings
from .kb import load_chunks
from .render import render_response
from .retrieval import KeywordRetriever


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="arm-copilot")
    p.add_argument("question")
    p.add_argument("--retrieve-only", action="store_true", help="Show keyword-search results only (no models, no keys).")
    p.add_argument("--json", action="store_true", help="Print the full response, including the decision trace, as JSON.")
    args = p.parse_args(argv)
    settings = Settings.from_env()

    if args.retrieve_only:
        retriever = KeywordRetriever(load_chunks(settings.kb_dir))
        for sc in retriever.search(args.question, None, settings.top_k):
            c = sc.chunk
            print(f"{sc.score:.2f}  {c.chunk_id}  {c.clause_title}")
        return 0

    from .factory import create_agent  # imported here so --retrieve-only works without extra packages

    resp = create_agent(settings).ask(args.question)
    print(json.dumps(resp.model_dump(), indent=2) if args.json else render_response(resp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
