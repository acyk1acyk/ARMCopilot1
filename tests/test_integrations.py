"""Tests for the LangGraph wiring and the Guardrails AI adapter.

These need `langgraph` and `guardrails-ai`, which could not be installed in the workspace where the
project was written, so they are skipped there and run on your machine after `pip install -r requirements.txt`.
"""

import importlib.util
import unittest

from arm_copilot.agent import AgentRunner, Deps
from arm_copilot.config import Settings
from arm_copilot.guardrail import GUARDRAILS_AVAILABLE, CitationGuard
from arm_copilot.kb import load_chunks
from arm_copilot.retrieval import KeywordRetriever
from arm_copilot.schemas import AnswerCard, Point, RouteDecision

from .golden_cards import GOLDEN

HAVE_LANGGRAPH = importlib.util.find_spec("langgraph") is not None
CHUNKS = load_chunks(Settings().kb_dir)
BY_ID = {c.chunk_id: c for c in CHUNKS}
QUESTION = "A client wants to place a USD time deposit with same-day value. What is the cutoff time?"


@unittest.skipUnless(HAVE_LANGGRAPH, "langgraph is not installed")
class LangGraphWiringTests(unittest.TestCase):
    def runner(self, answers, **settings):
        queue = list(answers)
        calls = []

        def answer_fn(q, chunks, feedback):
            calls.append(feedback)
            return queue.pop(0) if len(queue) > 1 else queue[0]

        s = Settings(require_guardrails=False, **settings)
        deps = Deps(
            route_fn=lambda q: RouteDecision(category="cutoff_times", search_query=q),
            answer_fn=answer_fn,
            retriever=KeywordRetriever(CHUNKS),
            guard=CitationGuard(require_guardrails=False),
            settings=s,
        )
        return AgentRunner(deps, engine="langgraph"), calls

    def test_happy_path_through_langgraph(self):
        runner, calls = self.runner([GOLDEN["Q01"]])
        resp = runner.ask(QUESTION)
        self.assertEqual(resp.status, "answered")
        self.assertEqual(len(calls), 1)

    def test_retry_then_answer_through_langgraph(self):
        bad = AnswerCard(headline="x", points=[Point(text="12:00 HKT", citations=[])])
        runner, calls = self.runner([bad, GOLDEN["Q01"]])
        resp = runner.ask(QUESTION)
        self.assertEqual(resp.status, "answered")
        self.assertEqual(resp.attempts, 2)
        self.assertIn("uncited_point", calls[1])

    def test_escalation_after_repeated_failures_through_langgraph(self):
        bad = AnswerCard(headline="x", points=[Point(text="12:00 HKT", citations=[])])
        runner, calls = self.runner([bad])
        resp = runner.ask(QUESTION)
        self.assertEqual(resp.status, "escalated")
        self.assertEqual(len(calls), 2)

    def test_step_limit_through_langgraph(self):
        runner, _ = self.runner([GOLDEN["Q01"]], recursion_limit=2)
        resp = runner.ask(QUESTION)
        self.assertEqual(resp.status, "escalated")


@unittest.skipUnless(GUARDRAILS_AVAILABLE, "guardrails-ai is not installed")
class GuardrailsAdapterTests(unittest.TestCase):
    def test_engine_is_guardrails_ai(self):
        self.assertEqual(CitationGuard(require_guardrails=True).engine, "guardrails-ai")

    def test_good_answer_passes(self):
        res = CitationGuard().validate(GOLDEN["Q01"], BY_ID, QUESTION)
        self.assertTrue(res.passed, [str(v) for v in res.violations])
        self.assertFalse(res.error)

    def test_uncited_answer_is_blocked(self):
        bad = AnswerCard(headline="x", points=[Point(text="The cutoff is 12:00 HKT.", citations=[])])
        res = CitationGuard().validate(bad, BY_ID, QUESTION)
        self.assertFalse(res.passed)
        self.assertFalse(res.error)

    def test_all_golden_answers_pass(self):
        import json
        from pathlib import Path

        cases = {c["id"]: c for c in json.loads((Path(__file__).parents[1] / "eval" / "test_set_v1.json").read_text())["cases"]}
        guard = CitationGuard()
        for qid, card in GOLDEN.items():
            res = guard.validate(card, BY_ID, cases[qid]["question"])
            self.assertTrue(res.passed, f"{qid}: {[str(v) for v in res.violations]}")


class GuardrailsRequirementTests(unittest.TestCase):
    @unittest.skipIf(GUARDRAILS_AVAILABLE, "only meaningful when guardrails-ai is missing")
    def test_missing_guardrails_is_a_loud_error_by_default(self):
        with self.assertRaises(RuntimeError):
            CitationGuard(require_guardrails=True)


if __name__ == "__main__":
    unittest.main()
