import re
import unittest

from arm_copilot.config import Settings
from arm_copilot.kb import load_chunks
from arm_copilot.schemas import CATEGORIES

REAL_BANK_WORDS = [r"\bubs\b", r"\bhsbc\b", r"\bciti\b", r"\bcitibank\b", r"jp ?morgan", r"credit suisse",
                   r"standard chartered", r"bank of china", r"hang seng", r"\bdbs\b", r"goldman"]


class KnowledgeBaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb_dir = Settings().kb_dir
        cls.chunks = load_chunks(cls.kb_dir)
        cls.by_id = {c.chunk_id: c for c in cls.chunks}

    def test_all_five_categories_are_covered(self):
        self.assertEqual({c.category for c in self.chunks}, set(CATEGORIES))

    def test_chunk_ids_are_unique_and_well_formed(self):
        ids = [c.chunk_id for c in self.chunks]
        self.assertEqual(len(ids), len(set(ids)))
        for i in ids:
            self.assertRegex(i, r"^OPS-[A-Z]{3}-\d{3}#\d+\.\d+$")

    def test_clause_numbers_match_the_document_number(self):
        for c in self.chunks:
            doc_number = int(c.doc_id.split("-")[-1])
            self.assertEqual(int(c.clause_id.split(".")[0]), doc_number, c.chunk_id)

    def test_every_document_is_labelled_fictional(self):
        for f in self.kb_dir.glob("*.md"):
            self.assertIn("FICTIONAL DOCUMENT", f.read_text(encoding="utf-8"), f.name)

    def test_no_real_bank_names_appear(self):
        for f in self.kb_dir.glob("*.md"):
            text = f.read_text(encoding="utf-8").lower()
            for pat in REAL_BANK_WORDS:
                self.assertIsNone(re.search(pat, text), f"{f.name} mentions a real bank ({pat})")

    def test_cross_references_resolve(self):
        doc_ids = {c.doc_id for c in self.chunks}
        for c in self.chunks:
            for ref in re.findall(r"OPS-[A-Z]{3}-\d{3}", c.content):
                self.assertIn(ref, doc_ids, f"{c.chunk_id} refers to unknown document {ref}")
            for clause in re.findall(r"clauses? (\d+\.\d+)", c.content):
                self.assertIn(f"{c.doc_id}#{clause}", self.by_id, f"{c.chunk_id} refers to missing clause {clause}")
            for a, b in re.findall(r"clauses (\d+\.\d+) to (\d+\.\d+)", c.content):
                for clause in (a, b):
                    self.assertIn(f"{c.doc_id}#{clause}", self.by_id)

    def test_expected_size(self):
        self.assertEqual(len(self.chunks), 49)


if __name__ == "__main__":
    unittest.main()
