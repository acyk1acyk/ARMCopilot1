"""Control-flow tests for the agent, using stand-ins for the two model calls (no network, no keys)."""

import unittest

from arm_copilot.agent import (
    MSG_NO_SOURCE,
    MSG_OUT_OF_SCOPE,
    MSG_UNVERIFIED,
    AgentRunner,
    Deps,
)
from arm_copilot.config import Settings
from arm_copilot.guardrail import CitationGuard
from arm_copilot.kb import load_chunks
from arm_copilot.retrieval import KeywordRetriever
from arm_copilot.schemas import AnswerCard, Citation, KeyValue, Point, RouteDecision

from .golden_cards import GOLDEN

QUESTION = "A client wants to place a USD time deposit with same-day value. What is the cutoff time?"
CHUNKS = load_chunks(Settings().kb_dir)


def good_card(**kw):
    return GOLDEN["Q01"].model_copy(update=kw)


def bad_card():
    return AnswerCard(headline="12:00 HKT", points=[Point(text="The cutoff is 12:00 HKT.", citations=[])])


class Recorder:
    """Stand-in for a model call that returns queued results and records how it was called."""

    def __init__(self, results):
        self.results, self.calls = list(results), []

    def __call__(self, *args):
        self.calls.append(args)
        r = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(r, Exception):
            raise r
        return r


def route_to(category="cutoff_times", query="USD deposit same-day cutoff time"):
    return Recorder([RouteDecision(category=category, search_query=query)])


def make(route, answer, **settings):
    s = Settings(require_guardrails=False, **settings)
    deps = Deps(route, answer, KeywordRetriever(CHUNKS), CitationGuard(require_guardrails=False), s)
    return AgentRunner(deps, engine="sequential")


class AgentFlowTests(unittest.TestCase):
    def test_happy_path(self):
        answer = Recorder([good_card()])
        resp = make(route_to(), answer).ask(QUESTION)
        self.assertEqual(resp.status, "answered")
        self.assertEqual(resp.attempts, 1)
        self.assertEqual(len(answer.calls), 1)
        self.assertEqual([s.chunk_id for s in resp.sources], ["OPS-CUT-001#1.2"])
        self.assertIn("12:00", resp.answer_text())
        self.assertTrue(any("validate" in line and "passed" in line for line in resp.trace))

    def test_a_failed_check_triggers_one_retry_with_feedback(self):
        answer = Recorder([bad_card(), good_card()])
        resp = make(route_to(), answer).ask(QUESTION)
        self.assertEqual(resp.status, "answered")
        self.assertEqual(resp.attempts, 2)
        feedback_on_retry = answer.calls[1][2]
        self.assertIn("uncited_point", feedback_on_retry)
        self.assertIsNone(answer.calls[0][2])

    def test_escalates_instead_of_guessing_when_answers_keep_failing(self):
        answer = Recorder([bad_card()])
        resp = make(route_to(), answer).ask(QUESTION)
        self.assertEqual(resp.status, "escalated")
        self.assertEqual(resp.message, MSG_UNVERIFIED)
        self.assertIsNone(resp.card)
        self.assertEqual(len(answer.calls), 2)  # never more than max_answer_attempts
        self.assertTrue(resp.sources)  # tells the user which clauses to read

    def test_attempt_limit_is_a_hard_cap(self):
        answer = Recorder([bad_card()])
        make(route_to(), answer, max_answer_attempts=1).ask(QUESTION)
        self.assertEqual(len(answer.calls), 1)

    def test_out_of_scope_questions_never_reach_the_answer_model(self):
        answer = Recorder([good_card()])
        resp = make(route_to("out_of_scope", "weather"), answer).ask("What is the weather like?")
        self.assertEqual(resp.status, "out_of_scope")
        self.assertEqual(resp.message, MSG_OUT_OF_SCOPE)
        self.assertEqual(answer.calls, [])

    def test_no_matching_clause_means_escalation(self):
        answer = Recorder([good_card()])
        resp = make(route_to(query="zzzz qqqq xxxx"), answer).ask("zzzz qqqq xxxx")
        self.assertEqual(resp.status, "escalated")
        self.assertEqual(resp.message, MSG_NO_SOURCE)
        self.assertEqual(answer.calls, [])

    def test_model_says_it_cannot_answer(self):
        answer = Recorder([AnswerCard(cannot_answer=True, note="crypto withdrawals are not covered")])
        resp = make(route_to(), answer).ask("What is the cutoff time for crypto withdrawals?")
        self.assertEqual(resp.status, "escalated")
        self.assertIn("crypto withdrawals are not covered", resp.message)
        self.assertEqual(len(answer.calls), 1)  # no pointless retry

    def test_low_confidence_and_signoff_are_flagged(self):
        resp = make(route_to(), Recorder([good_card(confidence="low", requires_signoff=True, signoff_by="Desk Head")])).ask(QUESTION)
        self.assertEqual(resp.status, "answered")
        self.assertEqual(set(resp.flags), {"low_confidence", "requires_signoff"})
        self.assertIn("confirm", resp.message.lower())

    def test_overlong_question_is_refused_before_any_model_call(self):
        route = route_to()
        resp = make(route, Recorder([good_card()]), max_question_chars=50).ask("x" * 51)
        self.assertEqual(resp.status, "escalated")
        self.assertEqual(route.calls, [])

    def test_empty_question(self):
        route = route_to()
        resp = make(route, Recorder([good_card()])).ask("   ")
        self.assertEqual(resp.status, "escalated")
        self.assertEqual(route.calls, [])

    def test_router_failure_escalates(self):
        resp = make(Recorder([RuntimeError("boom")]), Recorder([good_card()])).ask(QUESTION)
        self.assertEqual(resp.status, "escalated")
        self.assertNotIn("boom", resp.message)

    def test_answer_model_error_counts_as_an_attempt_and_retries(self):
        answer = Recorder([TimeoutError("slow"), good_card()])
        resp = make(route_to(), answer).ask(QUESTION)
        self.assertEqual(resp.status, "answered")
        self.assertEqual(resp.attempts, 2)

    def test_step_limit_stops_runaway_runs(self):
        resp = make(route_to(), Recorder([good_card()]), recursion_limit=2).ask(QUESTION)
        self.assertEqual(resp.status, "escalated")
        self.assertIn("too many steps", resp.message)

    def test_invented_number_is_caught_end_to_end(self):
        wrong = good_card(key_values=[KeyValue(label="USD deposit cutoff (T)", value="13:00 HKT")])
        resp = make(route_to(), Recorder([wrong])).ask(QUESTION)
        self.assertEqual(resp.status, "escalated")
        self.assertTrue(any("ungrounded_value" in line for line in resp.trace))

    def test_wrong_clause_citation_is_caught(self):
        card = good_card(points=[Point(text="The cutoff is 12:00 HKT.", citations=[Citation(chunk_id="OPS-PRC-002#2.4", quote="| B | 8 bps | 13 bps |")])])
        resp = make(route_to(), Recorder([card])).ask(QUESTION)  # 2.4 is not retrieved for this query
        self.assertEqual(resp.status, "escalated")


if __name__ == "__main__":
    unittest.main()
