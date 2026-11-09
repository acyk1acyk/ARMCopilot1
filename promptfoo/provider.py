"""Promptfoo provider: runs the real ARM Copilot pipeline for one question.

Promptfoo calls call_api() once per test. We return the full FinalResponse as JSON so the
assertion file can score it exactly like scripts/run_eval.py does.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        from arm_copilot.config import Settings
        from arm_copilot.factory import create_agent

        _agent = create_agent(Settings.from_env())
    return _agent


def call_api(prompt, options, context):
    try:
        resp = _get_agent().ask(prompt)
        return {"output": resp.model_dump_json()}
    except Exception as exc:  # report as an error row instead of stopping the whole run
        return {"error": f"{type(exc).__name__}: {exc}"}
