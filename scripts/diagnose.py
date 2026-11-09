"""Show what the agent actually did for test cases, so failures can be understood.

    python scripts/diagnose.py --set eval/test_set_v2.json --ids T01,T04,T10
    python scripts/diagnose.py --set eval/test_set_v2.json --failed-only     # re-runs everything, shows only failures

Writes eval/diagnosis_latest.txt (and prints it). Needs the same .env and ingested data as run_eval.py.
Send me the text file: it contains only fictional knowledge-base content and your test questions.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm_copilot.config import Settings  # noqa: E402
from arm_copilot.evaluation import evaluate_case, load_cases  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default=str(ROOT / "eval" / "test_set_v2.json"))
    ap.add_argument("--ids", default="", help="Comma-separated case ids, e.g. T01,T04")
    ap.add_argument("--failed-only", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "eval" / "diagnosis_latest.txt"))
    args = ap.parse_args()

    from arm_copilot.factory import create_agent

    data = load_cases(Path(args.set))
    cases = data["cases"] + data.get("guardrail_cases", [])
    wanted = {x.strip() for x in args.ids.split(",") if x.strip()}
    if wanted:
        cases = [c for c in cases if c["id"] in wanted]
    agent = create_agent(Settings.from_env())

    blocks: list[str] = []
    for case in cases:
        try:
            resp = agent.ask(case["question"])
        except Exception as exc:
            blocks.append(f"=== {case['id']}  ERROR {type(exc).__name__}: {exc}\n")
            continue
        res = evaluate_case(case, resp)
        if args.failed_only and res.passed:
            continue
        lines = [f"=== {case['id']}  {'PASS' if res.passed else 'FAIL'}  status={resp.status} attempts={resp.attempts}",
                 f"Question: {case['question']}",
                 f"Expected facts: {case.get('expected_facts', [])}",
                 f"Expected citations: {case.get('expected_citations', [])}"]
        lines += [f"Problem: {p}" for p in res.problems]
        lines.append(f"Cited clauses: {sorted(resp.cited_chunk_ids())}")
        lines.append("Answer:" if resp.status == "answered" else f"Message: {resp.message}")
        lines.append(resp.answer_text() if resp.status == "answered" else "")
        if resp.card and resp.card.note:
            lines.append(f"Note: {resp.card.note}")
        lines.append("Trace:")
        lines += [f"  {t}" for t in resp.trace]
        blocks.append("\n".join(lines) + "\n")

    text = "\n".join(blocks) or "Nothing to show.\n"
    Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
