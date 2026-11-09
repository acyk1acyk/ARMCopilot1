"""Build promptfoo/tests.json from eval/test_set_v2.json (the single source of the questions).

    python scripts/make_promptfoo_tests.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "eval" / "test_set_v2.json").read_text(encoding="utf-8"))
tests = []
for c in data["cases"] + data.get("guardrail_cases", []):
    tests.append({
        "description": f"{c['id']} [{c.get('category', '')}] {c['question'][:70]}",
        "vars": {"question": c["question"], "case_id": c["id"]},
        "assert": [{"type": "python", "value": "file://promptfoo/assert_case.py"}],
    })
out = ROOT / "promptfoo" / "tests.json"
out.write_text(json.dumps(tests, indent=2), encoding="utf-8")
print(f"Wrote {len(tests)} tests to {out.relative_to(ROOT)}")
