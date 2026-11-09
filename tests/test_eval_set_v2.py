import json
import unittest
from pathlib import Path

from arm_copilot.config import Settings
from arm_copilot.evaluation import retrieval_hit
from arm_copilot.grounding import canon
from arm_copilot.kb import load_chunks
from arm_copilot.retrieval import KeywordRetriever

DATA = json.loads((Path(__file__).parents[1] / "eval" / "test_set_v2.json").read_text(encoding="utf-8"))


class EvalSetV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chunks = {c.chunk_id: c for c in load_chunks(Settings().kb_dir)}
        cls.cases = DATA["cases"]

    def test_thirty_questions_plus_guardrail_cases(self):
        self.assertEqual(len(self.cases), 30)
        self.assertEqual(len({c["id"] for c in self.cases}), 30)
        self.assertGreaterEqual(len(DATA["guardrail_cases"]), 3)

    def test_all_five_categories_covered(self):
        self.assertEqual(len({c["category"] for c in self.cases}), 5)

    def test_expected_citations_exist_and_match_category(self):
        for c in self.cases:
            self.assertTrue(c["expected_citations"], c["id"])
            for cid in c["expected_citations"]:
                self.assertIn(cid, self.chunks, c["id"])
                self.assertEqual(self.chunks[cid].category, c["category"], c["id"])

    def test_every_expected_fact_is_written_in_the_cited_clauses_or_question(self):
        for c in self.cases:
            source = canon(" ".join(self.chunks[i].content for i in c["expected_citations"]) + " " + c["question"])
            for fact in c["expected_facts"]:
                options = fact if isinstance(fact, list) else [fact]
                self.assertTrue(any(canon(o) in source for o in options), f"{c['id']}: '{fact}' not in cited clauses")

    def test_keyword_retrieval_finds_needed_clauses(self):
        retriever = KeywordRetriever(list(self.chunks.values()))
        misses = []
        for c in self.cases:
            ok, got = retrieval_hit(c, retriever, k=5)
            if not ok:
                misses.append((c["id"], c["expected_citations"], got))
        self.assertEqual(misses, [], misses)


if __name__ == "__main__":
    unittest.main()


class MustNotSayTests(unittest.TestCase):
    def _resp(self, status, headline="", cite=True):
        from arm_copilot.schemas import AnswerCard, Citation, FinalResponse, Point

        if status != "answered":
            return FinalResponse(status=status, message="no")
        pts = [Point(text=headline, citations=[Citation(chunk_id="OPS-CUT-001#1.2", quote="12:00")] if cite else [])]
        return FinalResponse(status="answered", card=AnswerCard(headline=headline, points=pts))

    def test_injection_case_rules(self):
        from arm_copilot.evaluation import evaluate_case

        case = next(c for c in DATA["guardrail_cases"] if c["id"] == "G03")
        self.assertTrue(evaluate_case(case, self._resp("escalated")).passed)
        self.assertTrue(evaluate_case(case, self._resp("answered", "USD same-day deposit cutoff is 12:00 HKT")).passed)
        self.assertFalse(evaluate_case(case, self._resp("answered", "The cutoff is 6pm")).passed)
        self.assertFalse(evaluate_case(case, self._resp("answered", "Cutoff is 12:00 HKT", cite=False)).passed)
