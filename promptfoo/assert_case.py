"""Promptfoo assertion: scores one response with the same rules as scripts/run_eval.py
(arm_copilot.evaluation.evaluate_case): answered or escalated as expected, expected facts in the
visible text, expected clauses cited, sign-off flag, and must_not_say for the guardrail case."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def get_assert(output, context):
    from arm_copilot.evaluation import evaluate_case, load_cases
    from arm_copilot.schemas import FinalResponse

    case_id = context["vars"]["case_id"]
    data = load_cases(ROOT / "eval" / "test_set_v2.json")
    case = next(c for c in data["cases"] + data.get("guardrail_cases", []) if c["id"] == case_id)
    resp = FinalResponse.model_validate(json.loads(output))
    res = evaluate_case(case, resp)
    return {
        "pass": res.passed,
        "score": 1.0 if res.passed else 0.0,
        "reason": "OK" if res.passed else "; ".join(res.problems),
    }
