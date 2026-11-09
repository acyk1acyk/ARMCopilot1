import unittest
from datetime import date

from arm_copilot.config import Settings
from arm_copilot.grounding import quote_in_chunk
from arm_copilot.kb import load_chunks
from arm_copilot.panel import checklists as cl
from arm_copilot.panel.clients import load_clients, risk_profile_valid
from arm_copilot.panel.facts import PRODUCTS, ScenarioInputs, adjust_cutoff, build_facts, cutoff_time

CHUNKS = {c.chunk_id: c for c in load_chunks(Settings().kb_dir)}
CLIENTS = {c.client_id: c for c in load_clients()}
TODAY = date(2026, 11, 2)


def facts(client_id, product, **kw):
    return {f.title: f for f in build_facts(CHUNKS, ScenarioInputs(client=CLIENTS[client_id], product=product, today=TODAY, **kw))}


class ChecklistDataTests(unittest.TestCase):
    def test_every_product_has_a_checklist(self):
        raw = cl.load_raw()
        self.assertEqual(set(raw["products"]), set(PRODUCTS))

    def test_every_quote_is_written_in_its_clause(self):
        raw = cl.load_raw()
        for product in PRODUCTS:
            for ph in cl.all_phases(product, raw):
                for step in ph.steps:
                    self.assertTrue(step.why, f"{product}/{step.step_id} has no citation")
                    for w in step.why:
                        self.assertIn(w.chunk_id, CHUNKS, f"{product}/{step.step_id}")
                        self.assertTrue(quote_in_chunk(w.quote, CHUNKS[w.chunk_id].content),
                                        f"{product}/{step.step_id}: quote not in {w.chunk_id}: {w.quote}")

    def test_conditions_are_known_and_step_ids_unique(self):
        for product in PRODUCTS:
            seen = set()
            for ph in cl.all_phases(product):
                for s in ph.steps:
                    self.assertIn(s.when, cl.CONDITIONS)
                    self.assertNotIn(s.step_id, seen, f"duplicate id {s.step_id} in {product}")
                    seen.add(s.step_id)

    def test_conditional_steps_appear_only_when_they_apply(self):
        base = ScenarioInputs(client=CLIENTS["C-1001"], product="structured", amount_usd=1_000_000, today=TODAY)
        ids = {s.step_id for ph in cl.checklist_for("structured", base, False) for s in ph.steps}
        self.assertNotIn("st_appr_head", ids)
        big = ScenarioInputs(client=CLIENTS["C-1001"], product="structured", amount_usd=3_000_000, today=TODAY)
        ids = {s.step_id for ph in cl.checklist_for("structured", big, False) for s in ph.steps}
        self.assertIn("st_appr_head", ids)
        ids = {s.step_id for ph in cl.checklist_for("structured", base, True) for s in ph.steps}
        self.assertIn("risk_profile_blocked", ids)


class ClientTests(unittest.TestCase):
    def test_clients_are_marked_fictional(self):
        self.assertEqual(len(CLIENTS), 4)
        for c in CLIENTS.values():
            self.assertIn("(fictional)", c.display_name)
            self.assertIn(c.tier, "ABC")

    def test_risk_profile_validity(self):
        self.assertTrue(risk_profile_valid(date(2026, 3, 12), TODAY))
        self.assertFalse(risk_profile_valid(date(2025, 8, 20), TODAY))
        self.assertTrue(risk_profile_valid(date(2025, 11, 2), TODAY))
        self.assertFalse(risk_profile_valid(date(2025, 11, 1), TODAY))
        self.assertTrue(risk_profile_valid(date(2024, 2, 29), date(2025, 2, 28)))


class FactTests(unittest.TestCase):
    def test_cutoff_reads_the_tables(self):
        self.assertEqual(cutoff_time(CHUNKS, True, "USD", "T"), "12:00")
        self.assertEqual(cutoff_time(CHUNKS, False, "USD", "T"), "11:30")
        self.assertEqual(cutoff_time(CHUNKS, True, "HKD", "T+1"), "17:00")
        self.assertEqual(cutoff_time(CHUNKS, True, "AUD", "T+2 or later"), "17:00")

    def test_deposit_and_loan_cutoffs_shown(self):
        f = facts("C-1003", "time_deposit", currency="USD", value_date="T")
        self.assertEqual(f["USD T cutoff"].value, "12:00 HKT")
        f = facts("C-1003", "loan", currency="USD", value_date="T")
        self.assertEqual(f["USD T cutoff"].value, "11:30 HKT")

    def test_half_day_and_severe_weather(self):
        self.assertEqual(adjust_cutoff("15:00", "T", True, False)[0], "12:00")
        self.assertEqual(adjust_cutoff("11:00", "T", True, False)[0], "11:00")
        self.assertIsNone(adjust_cutoff("15:00", "T", False, True)[0])
        self.assertEqual(adjust_cutoff("15:00", "T+1", False, True)[0], "15:00")
        f = facts("C-1003", "time_deposit", currency="EUR", half_day=True)
        self.assertEqual(f["EUR T cutoff"].value, "12:00 HKT")
        self.assertIn("OPS-CUT-001#1.7", f["EUR T cutoff"].sources)
        f = facts("C-1003", "time_deposit", currency="EUR", severe_weather=True)
        self.assertEqual(f["EUR T cutoff"].tone, "blocked")

    def test_fx_pricing_and_additional_markup(self):
        f = facts("C-1004", "spot_fx", amount_usd=1_000_000)  # Tier B with 3 bps add-on
        self.assertEqual(f["Tier B spot FX spread"].value, "8 bps major / 13 bps other")
        self.assertEqual(f["Client-specific additional markup"].value, "+ 3 bps")
        self.assertIn("Above USD 250,000 up to USD 5 million", f["Amount band"].value)
        f = facts("C-1004", "spot_fx", amount_usd=100_000)
        self.assertIn("2 bps small-ticket supplement", f["Amount band"].value)
        f = facts("C-1004", "spot_fx", amount_usd=9_000_000)
        self.assertIn("Manual quote", f["Amount band"].value)
        self.assertNotIn("Client-specific additional markup", facts("C-1002", "spot_fx"))

    def test_brokerage_and_custody(self):
        f = facts("C-1002", "hk_equity")
        self.assertEqual(f["Tier B brokerage"].value, "0.20% (min HKD 200)")
        self.assertEqual(f["Custody fee (annual)"].value, "0.15%")
        f = facts("C-1003", "bond", amount_usd=800_000)
        self.assertEqual(f["Tier C brokerage"].value, "0.20% of nominal (min USD 100)")
        self.assertIn("less 0.02", f["Amount band"].value)

    def test_fund_fee_bands(self):
        f = facts("C-1001", "fund", amount_usd=2_000_000)
        self.assertIn("0.50%", f["Fund subscription fee"].value)

    def test_overdraft_rates(self):
        f = facts("C-1003", "overdraft", currency="EUR")
        self.assertEqual(f["EUR overdraft rate, Tier C"].value, "1-month EURIBOR + 2.25%")
        f = facts("C-1002", "overdraft", currency="USD")
        self.assertEqual(f["USD overdraft rate, Tier B"].value, "1-month Term SOFR + 1.85%")
        f = facts("C-1002", "overdraft", currency="GBP")
        self.assertEqual(f["Overdraft"].tone, "blocked")

    def test_risk_profile_card(self):
        self.assertEqual(facts("C-1001", "bond")["Risk profile"].tone, "ok")
        self.assertEqual(facts("C-1002", "bond")["Risk profile"].tone, "blocked")
        self.assertNotIn("Risk profile", facts("C-1002", "payment_out"))

    def test_structured_cards(self):
        f = facts("C-1002", "structured", amount_usd=3_000_000)
        self.assertEqual(f["Professional Investor"].tone, "blocked")
        self.assertEqual(f["Approvals"].value, "RM + Desk Head + Head of Private Banking")
        f = facts("C-1001", "structured", amount_usd=1_000_000)
        self.assertEqual(f["Approvals"].value, "RM + Desk Head")
        self.assertEqual(f["Professional Investor"].tone, "ok")

    def test_payment_authentication_levels(self):
        self.assertEqual(facts("C-1004", "payment_out", amount_usd=600_000)["Authentication"].value, "Level 4")
        self.assertIn("Level 3", facts("C-1004", "payment_out", amount_usd=50_000)["Authentication"].value)

    def test_every_card_names_a_real_clause(self):
        for client in CLIENTS.values():
            for product in PRODUCTS:
                for ccy in ("USD", "GBP"):
                    for f in build_facts(CHUNKS, ScenarioInputs(client=client, product=product, currency=ccy, amount_usd=1_000_000, today=TODAY)):
                        for s in f.sources:
                            self.assertIn(s, CHUNKS, f"{product}: {f.title}")
                        self.assertNotIn("Not found", f.value, f"{client.client_id}/{product}/{ccy}: {f.title}")


if __name__ == "__main__":
    unittest.main()
