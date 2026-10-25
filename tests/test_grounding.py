import unittest

from arm_copilot.config import Settings
from arm_copilot.grounding import check_grounding, risky_tokens
from arm_copilot.kb import load_chunks
from arm_copilot.schemas import AnswerCard, Citation, KeyValue, Point

from .golden_cards import GOLDEN


def card(points, headline="", key_values=None, **kw):
    return AnswerCard(headline=headline, points=points, key_values=key_values or [], **kw)


def pt(text, chunk_id, quote):
    return Point(text=text, citations=[Citation(chunk_id=chunk_id, quote=quote)])


class GroundingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chunks = {c.chunk_id: c for c in load_chunks(Settings().kb_dir)}

    def codes(self, c, question=""):
        return sorted({v.code for v in check_grounding(c, self.chunks, question)})

    def test_correct_answer_passes(self):
        c = card([pt("USD same-day cutoff is 12:00 HKT.", "OPS-CUT-001#1.2", "| USD | 12:00 | 16:30 | 17:00 |")])
        self.assertEqual(self.codes(c), [])

    def test_uncited_point_fails(self):
        c = card([Point(text="USD same-day cutoff is 12:00 HKT.", citations=[])])
        self.assertEqual(self.codes(c), ["uncited_point"])

    def test_no_points_fails(self):
        self.assertEqual(self.codes(card([])), ["no_points"])

    def test_citing_a_clause_that_was_not_retrieved_fails(self):
        c = card([pt("Anything.", "OPS-XXX-999#9.9", "some quote that is long enough")])
        self.assertEqual(self.codes(c), ["unknown_chunk"])

    def test_quote_must_be_word_for_word(self):
        c = card([pt("Cutoff is 12:00 HKT.", "OPS-CUT-001#1.2", "the USD cutoff is twelve noon sharp")])
        self.assertIn("quote_mismatch", self.codes(c))

    def test_made_up_time_is_blocked(self):
        c = card([pt("The USD same-day cutoff is 13:00 HKT.", "OPS-CUT-001#1.2", "| USD | 12:00 | 16:30 | 17:00 |")])
        self.assertEqual(self.codes(c), ["ungrounded_value"])

    def test_made_up_value_in_key_values_is_blocked(self):
        c = card(
            [pt("USD same-day cutoff is 12:00 HKT.", "OPS-CUT-001#1.2", "| USD | 12:00 | 16:30 | 17:00 |")],
            key_values=[KeyValue(label="USD cutoff", value="13:00 HKT")],
        )
        self.assertEqual(self.codes(c), ["ungrounded_value"])

    def test_numbers_from_the_question_are_allowed(self):
        c = card([pt("Your USD 3 million order is above USD 2 million equivalent, so the Head of Private Banking must also approve.",
                     "OPS-PTR-005#5.7", "the Head of Private Banking must also approve")])
        self.assertEqual(self.codes(c, "accumulator with a USD 3 million notional"), [])
        self.assertEqual(self.codes(c, "accumulator"), ["ungrounded_value"])

    def test_number_formatting_differences_are_tolerated(self):
        c = card([pt("The Tier B spread is 8bps.", "OPS-PRC-002#2.4", "| B | 8 bps | 13 bps |")])
        self.assertEqual(self.codes(c), [])

    def test_a_number_cannot_match_inside_a_longer_number(self):
        c = card([pt("The Tier B spread is 3 bps.", "OPS-PRC-002#2.4", "| B | 8 bps | 13 bps |")])
        self.assertEqual(self.codes(c), ["ungrounded_value"])

    def test_cannot_answer_has_nothing_to_check(self):
        self.assertEqual(self.codes(AnswerCard(cannot_answer=True, note="not covered")), [])

    def test_risky_token_extraction(self):
        toks = risky_tokens("Cutoff 15:30 HKT, 1.85% over base, 5 bps, USD 2 million, within 30 minutes, 2 business days.")
        for expected in ["15:30", "1.85%", "5bps", "usd 2 million", "30 minutes", "2 business days"]:
            self.assertIn(expected, toks)

    def test_golden_answers_for_all_ten_questions_pass(self):
        import json
        from pathlib import Path

        cases = {c["id"]: c for c in json.loads((Path(__file__).parents[1] / "eval" / "test_set_v1.json").read_text())["cases"]}
        self.assertEqual(set(GOLDEN), set(cases))
        for qid, golden in GOLDEN.items():
            v = check_grounding(golden, self.chunks, cases[qid]["question"])
            self.assertEqual(v, [], f"{qid}: {[str(x) for x in v]}")


if __name__ == "__main__":
    unittest.main()
