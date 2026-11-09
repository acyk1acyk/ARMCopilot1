"""Show the raw answer card and exactly which grounding checks failed, bypassing the retry loop.

    python scripts/diagnose_raw.py --set eval/test_set_v2.json --ids T01,T05,T10

Writes eval/diagnosis_raw.txt. Contains only fictional knowledge-base content and your test questions.
"""
from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm_copilot.config import Settings  # noqa: E402
from arm_copilot.evaluation import load_cases  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default=str(ROOT / "eval" / "test_set_v2.json"))
    ap.add_argument("--ids", required=True)
    ap.add_argument("--out", default=str(ROOT / "eval" / "diagnosis_raw.txt"))
    args = ap.parse_args()

    from arm_copilot.factory import create_agent

    data = load_cases(Path(args.set))
    cases = data["cases"] + data.get("guardrail_cases", [])
    wanted = {x.strip() for x in args.ids.split(",")}
    agent = create_agent(Settings.from_env())
    deps = getattr(agent, "deps", None)
    out: list[str] = []
    for case in [c for c in cases if c["id"] in wanted]:
        start = len(out)
        out.append(f"=== {case['id']}: {case['question']}")
        print(f"... running {case['id']}", flush=True)
        try:
            q = case["question"]
            route = deps.route_fn(q)
            out.append(f"Route: category={route.category} query={route.search_query!r}")
            k = deps.settings.top_k
            scored = deps.retriever.search(route.search_query or q, route.category, k)
            out.append("Retrieved: " + ", ".join(c.chunk.chunk_id for c in scored))
            card = deps.answer_fn(q, scored, None)
            out.append("Raw card:\n" + card.model_dump_json(indent=2))
            from arm_copilot.grounding import check_grounding
            by_id = {c.chunk.chunk_id: c.chunk for c in scored}
            violations = check_grounding(card, by_id, q)
            out.append("Violations: " + ("none" if not violations else ""))
            out.extend(f"  - {v}" for v in violations)
        except Exception:
            out.append("ERROR (send this too):\n" + traceback.format_exc())
        out.append("")
        print("\n".join(out[start:]), flush=True)  # show each question as soon as it finishes
    text = "\n".join(out)
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"Saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())