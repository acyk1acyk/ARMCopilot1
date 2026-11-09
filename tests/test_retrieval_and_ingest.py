import unittest
from types import SimpleNamespace

from arm_copilot.config import Settings
from arm_copilot.kb import load_chunks
from arm_copilot.retrieval import KeywordRetriever, SupabaseRetriever
from scripts.ingest import rows_for_upsert

CHUNKS = load_chunks(Settings().kb_dir)


class FakeEmbedder:
    def embed_query(self, text):
        return [0.1, 0.2, 0.3]


class FakeClient:
    """Mimics supabase.rpc(...).execute() so the row mapping can be tested without a project."""

    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.rows))


def row(chunk, similarity):
    d = chunk.to_row()
    d["similarity"] = similarity
    return d


class KeywordRetrieverTests(unittest.TestCase):
    def setUp(self):
        self.r = KeywordRetriever(CHUNKS)

    def test_finds_the_deposit_cutoff_table(self):
        ids = [s.chunk.chunk_id for s in self.r.search("USD time deposit same-day cutoff", "cutoff_times", 3)]
        self.assertIn("OPS-CUT-001#1.2", ids)

    def test_category_filter_is_respected(self):
        for s in self.r.search("cutoff", "pricing_tiers", 5):
            self.assertEqual(s.chunk.category, "pricing_tiers")

    def test_no_match_returns_nothing(self):
        self.assertEqual(self.r.search("zzzz qqqq", None, 5), [])

    def test_scores_are_between_zero_and_one(self):
        for s in self.r.search("overdraft rate penalty", None, 5):
            self.assertTrue(0 < s.score <= 1.0)


class SupabaseRetrieverTests(unittest.TestCase):
    def test_maps_rows_and_filters_by_similarity(self):
        rows = [row(CHUNKS[0], 0.62), row(CHUNKS[1], 0.10)]
        client = FakeClient(rows)
        r = SupabaseRetriever(Settings(min_similarity=0.30), embedder=FakeEmbedder(), client=client)
        out = r.search("anything", "cutoff_times", 5)
        self.assertEqual([s.chunk.chunk_id for s in out], [CHUNKS[0].chunk_id])
        self.assertAlmostEqual(out[0].score, 0.62)
        name, params = client.calls[0]
        self.assertEqual(name, "match_chunks")
        self.assertEqual(params, {"query_embedding": [0.1, 0.2, 0.3], "match_count": 5, "filter_category": "cutoff_times"})

    def test_empty_result(self):
        r = SupabaseRetriever(Settings(), embedder=FakeEmbedder(), client=FakeClient([]))
        self.assertEqual(r.search("x", None, 5), [])

    def test_extra_clauses_from_other_areas_are_added_when_routed(self):
        class TwoStep(FakeClient):
            def rpc(self, name, params):
                self.calls.append((name, params))
                rows = self.rows[0] if params["filter_category"] else self.rows[1]
                return SimpleNamespace(execute=lambda: SimpleNamespace(data=rows))

        cut = [c for c in CHUNKS if c.category == "cutoff_times"]
        other = [c for c in CHUNKS if c.category == "pricing_tiers"]
        client = TwoStep([[row(cut[0], 0.7)], [row(cut[0], 0.7), row(other[0], 0.6), row(other[1], 0.5), row(other[2], 0.4)]])
        r = SupabaseRetriever(Settings(min_similarity=0.30), embedder=FakeEmbedder(), client=client)
        ids = [s.chunk.chunk_id for s in r.search("q", "cutoff_times", 5)]
        self.assertEqual(ids, [cut[0].chunk_id, other[0].chunk_id, other[1].chunk_id])  # own area first, at most 2 extras
        self.assertEqual([c[1]["filter_category"] for c in client.calls], ["cutoff_times", None])
        client2 = TwoStep([[row(cut[0], 0.7)], [row(other[0], 0.6)]])
        r2 = SupabaseRetriever(Settings(), embedder=FakeEmbedder(), client=client2)
        r2.search("q", None, 5)
        self.assertEqual(len(client2.calls), 1)  # no routed area: a single search


class IngestTests(unittest.TestCase):
    def test_rows_carry_embeddings_and_metadata(self):
        rows = rows_for_upsert(CHUNKS[:2], [[0.0] * 4, [1.0] * 4], expected_dim=4)
        self.assertEqual(rows[0]["chunk_id"], CHUNKS[0].chunk_id)
        self.assertEqual(len(rows[1]["embedding"]), 4)
        self.assertIn("effective_date", rows[0])

    def test_wrong_embedding_size_is_rejected(self):
        with self.assertRaises(ValueError):
            rows_for_upsert(CHUNKS[:1], [[0.0] * 3], expected_dim=4)

    def test_count_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            rows_for_upsert(CHUNKS[:2], [[0.0] * 4], expected_dim=4)


if __name__ == "__main__":
    unittest.main()
