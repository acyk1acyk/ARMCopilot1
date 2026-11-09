"""Run the internal test set.

    python scripts/run_eval.py --retrieval-only    # keyword baseline, no keys needed
    python scripts/run_eval.py                     # the real agent (needs .env with all keys, and the data ingested)

The October milestone is 10 of 10 questions passing. Results are written to eval/results_latest.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm_copilot.config import Settings  # noqa: E402
from arm_copilot.evaluation import evaluate_case, load_cases, retrieval_hit  # noqa: E402
from arm_copilot.kb import load_chunks  # noqa: E402
from arm_copilot.retrieval import KeywordRetriever  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default=str(ROOT / "eval" / "test_set_v2.json"))
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--engine", default="langgraph", choices=["langgraph", "sequential"])
    ap.add_argument("--min-pass", type=float, default=1.0, help="Required pass rate (default 1.0 = all questions).")
    args = ap.parse_args()

    settings = Settings.from_env()
    data = load_cases(Path(args.set))
    cases = data["cases"]

    if args.retrieval_only:
        retriever = KeywordRetriever(load_chunks(settings.kb_dir))
        hits = 0
        for case in cases:
            ok, got = retrieval_hit(case, retriever, settings.top_k)
            hits += ok
            print(f"{'PASS' if ok else 'FAIL'}  {case['id']}  retrieved: {', '.join(got)}")
        print(f"\nKeyword retrieval baseline: {hits}/{len(cases)} questions had every needed clause in the top {settings.top_k}.")
        return 0

    from arm_copilot.factory import create_agent

    agent = create_agent(settings, engine=args.engine)
    results, passed = [], 0
    for case in cases + data.get("guardrail_cases", []):
        try:
            resp = agent.ask(case["question"])
            res = evaluate_case(case, resp)
            trace = resp.trace
        except Exception as exc:  # record the failure and keep going
            from arm_copilot.evaluation import CaseResult

            res = CaseResult(case["id"], False, [f"{type(exc).__name__}: {exc}"])
            trace = []
        core = case in cases
        passed += res.passed if core else 0
        print(f"{'PASS' if res.passed else 'FAIL'}  {res.case_id}  status={res.status or 'error'} attempts={res.attempts}")
        for p in res.problems:
            print(f"      - {p}")
        results.append({"id": res.case_id, "passed": res.passed, "problems": res.problems, "status": res.status,
                        "attempts": res.attempts, "trace": trace, "guardrail_case": not core})

    rate = passed / len(cases)
    print(f"\nCore questions passed: {passed}/{len(cases)} ({rate:.0%}). Required: {args.min_pass:.0%}.")
    out = ROOT / "eval" / "results_latest.json"
    out.write_text(json.dumps({"passed": passed, "total": len(cases), "results": results}, indent=2), encoding="utf-8")
    print(f"Saved {out.relative_to(ROOT)}")
    return 0 if rate >= args.min_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
