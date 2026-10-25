import json
import unittest
from pathlib import Path

from arm_copilot.config import Settings
from arm_copilot.evaluation import evaluate_case, retrieval_hit
from arm_copilot.grounding import canon
from arm_copilot.kb import load_chunks
from arm_copilot.retrieval import KeywordRetriever
from arm_copilot.schemas import FinalResponse

from .golden_cards import GOLDEN

DATA = json.loads((Path(__file__).parents[1] / "eval" / "test_set_v1.json").read_text(encoding="utf-8"))


class EvalSetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chunks = {c.chunk_id: c for c in load_chunks(Settings().kb_dir)}
        cls.cases = DATA["cases"]

    def test_ten_core_questions_plus_guardrail_case(self):
        self.assertEqual(len(self.cases), 10)
        self.assertEqual(len(DATA["guardrail_cases"]), 1)

    def test_all_five_categories_have_questions(self):
        self.assertEqual(len({c["category"] for c in self.cases}), 5)

    def test_expected_citations_exist_and_match_category(self):
        for c in self.cases:
            for cid in c["expected_citations"]:
                self.assertIn(cid, self.chunks, c["id"])
                self.assertEqual(self.chunks[cid].category, c["category"], c["id"])

    def test_every_expected_fact_is_written_in_the_cited_clauses_or_question(self):
        for c in self.cases:
            source = canon(" ".join(self.chunks[i].content for i in c["expected_citations"]) + " " + c["question"])
            for fact in c["expected_facts"]:
                options = fact if isinstance(fact, list) else [fact]
                self.assertTrue(any(canon(o) in source for o in options), f"{c['id']}: '{fact}' not found in cited clauses")

    def test_keyword_retrieval_baseline_finds_every_needed_clause(self):
        retriever = KeywordRetriever(list(self.chunks.values()))
        for c in self.cases:
            ok, got = retrieval_hit(c, retriever, k=5)
            self.assertTrue(ok, f"{c['id']}: wanted {c['expected_citations']}, got {got}")

    def test_golden_answers_pass_the_evaluator(self):
        for c in self.cases:
            resp = FinalResponse(status="answered", card=GOLDEN[c["id"]], attempts=1)
            res = evaluate_case(c, resp)
            self.assertTrue(res.passed, f"{c['id']}: {res.problems}")

    def test_evaluator_catches_a_wrong_answer(self):
        c = self.cases[0]
        wrong = GOLDEN["Q02"]  # answers a different question
        res = evaluate_case(c, FinalResponse(status="answered", card=wrong, attempts=1))
        self.assertFalse(res.passed)

    def test_evaluator_requires_escalation_for_the_guardrail_case(self):
        g = DATA["guardrail_cases"][0]
        self.assertTrue(evaluate_case(g, FinalResponse(status="escalated", message="no source")).passed)
        self.assertFalse(evaluate_case(g, FinalResponse(status="answered", card=GOLDEN["Q01"])).passed)

    def test_evaluator_checks_signoff_flag(self):
        c = next(x for x in self.cases if x["id"] == "Q05")
        no_flag = GOLDEN["Q05"].model_copy(update={"requires_signoff": False})
        self.assertFalse(evaluate_case(c, FinalResponse(status="answered", card=no_flag)).passed)


if __name__ == "__main__":
    unittest.main()
