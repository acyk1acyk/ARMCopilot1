"""Fact cards for the panel.

Every value is read from the knowledge base text (tables and sentences) with simple rules, not from a model.
Each card names the clause it came from. If a value cannot be found, the card says so instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Optional

from ..kb import Chunk
from .clients import Client, days_left, risk_profile_expiry, risk_profile_valid

CURRENCIES = ["HKD", "USD", "CNH", "EUR", "GBP", "JPY", "AUD"]
VALUE_DATES = ["T", "T+1", "T+2 or later"]
_VALUE_DATE_COLUMN = {"T": "T (same day)", "T+1": "T+1", "T+2 or later": "T+2 or later"}

PRODUCTS: dict[str, str] = {
    "time_deposit": "Time deposit placement or rollover",
    "loan": "Loan drawdown, rollover or repayment",
    "overdraft": "Lombard overdraft",
    "spot_fx": "Spot FX",
    "hk_equity": "Hong Kong listed equity",
    "us_equity": "US listed equity",
    "bond": "Bond (secondary market)",
    "fund": "Investment fund",
    "structured": "Accumulator, decumulator or structured note",
    "payment_out": "Outgoing payment",
    "payment_in": "Incoming payment",
}

CUT = "OPS-CUT-001#"
PRC = "OPS-PRC-002#"
LND = "OPS-LND-003#"
AUT = "OPS-AUT-004#"
PTR = "OPS-PTR-005#"


@dataclass(frozen=True)
class ScenarioInputs:
    client: Client
    product: str
    currency: str = "USD"
    value_date: str = "T"
    amount_usd: Optional[float] = None
    half_day: bool = False
    severe_weather: bool = False
    today: date = date(2026, 11, 2)


@dataclass(frozen=True)
class Fact:
    title: str
    value: str
    detail: str = ""
    sources: tuple[str, ...] = ()
    tone: str = "info"  # info | ok | warning | blocked


# ----------------------------------------------------------------------------- reading the KB


def _content(chunks: Mapping[str, Chunk], chunk_id: str) -> str:
    c = chunks.get(chunk_id)
    return c.content if c else ""


def table_rows(content: str) -> list[dict[str, str]]:
    """Rows of the first markdown table in a clause, as dictionaries keyed by the header cells."""
    lines = [ln.strip() for ln in content.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 3:
        return []
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    rows = []
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) == len(header):
            rows.append(dict(zip(header, cells)))
    return rows


def cutoff_time(chunks: Mapping[str, Chunk], deposit: bool, currency: str, value_date: str) -> Optional[str]:
    rows = table_rows(_content(chunks, CUT + ("1.2" if deposit else "1.3")))
    for r in rows:
        if r.get("Currency") == currency:
            return r.get(_VALUE_DATE_COLUMN[value_date])
    return None


def adjust_cutoff(time_text: str, value_date: str, half_day: bool, severe_weather: bool) -> tuple[Optional[str], list[str]]:
    """Apply clause 1.7: severe weather stops same-day value; half-days pull late cutoffs to 12:00."""
    notes: list[str] = []
    if severe_weather and value_date == "T":
        notes.append("Typhoon Signal No. 8 or above, or a Black Rainstorm Warning, is in force at 09:00: same-day (T) value is not accepted. It is processed as T+1 for the next business day.")
        return None, notes
    if half_day and time_text > "12:00":
        notes.append(f"Half-day trading day: the usual {time_text} cutoff is brought forward to 12:00.")
        return "12:00", notes
    return time_text, notes


# ----------------------------------------------------------------------------- cards


def _cutoff_fact(chunks: Mapping[str, Chunk], i: ScenarioInputs) -> Optional[Fact]:
    if i.product not in ("time_deposit", "loan"):
        return Fact("Cutoff time", "No cutoff table for this product", "The knowledge base only has cutoff tables for time deposits and loans.", (CUT + "1.1",))
    deposit = i.product == "time_deposit"
    base = cutoff_time(chunks, deposit, i.currency, i.value_date)
    src = CUT + ("1.2" if deposit else "1.3")
    if base is None:
        return Fact("Cutoff time", "Not found", f"No {i.currency} cutoff was found in {src}.", (src,), "warning")
    eff, notes = adjust_cutoff(base, i.value_date, i.half_day, i.severe_weather)
    sources = [src] + ([CUT + "1.7"] if notes else [])
    detail_parts = list(notes)
    if eff is not None and i.value_date == "T" and i.currency in ("HKD", "USD"):
        detail_parts.append("After the cutoff the Desk Head may approve a best-effort late acceptance for same-day value (HKD 200 fee, client told in writing by email).")
        sources.append(CUT + "1.5")
    elif eff is not None and i.value_date == "T":
        detail_parts.append("After the cutoff there is no late acceptance for this currency: the instruction rolls to the next available value date.")
        sources.append(CUT + "1.5")
    if eff is None:
        return Fact(f"{i.currency} {i.value_date} cutoff", "Same-day value not accepted", " ".join(detail_parts), tuple(sources), "blocked")
    tone = "warning" if notes else "info"
    return Fact(f"{i.currency} {i.value_date} cutoff", f"{eff} HKT", " ".join(detail_parts), tuple(sources), tone)


def _fx_pricing(chunks: Mapping[str, Chunk], i: ScenarioInputs) -> list[Fact]:
    rows = {r["Tier"]: r for r in table_rows(_content(chunks, PRC + "2.4"))}
    r = rows.get(i.client.tier)
    facts: list[Fact] = []
    if not r:
        return [Fact("FX spread", "Not found", "", (PRC + "2.4",), "warning")]
    facts.append(Fact(f"Tier {i.client.tier} spot FX spread", f"{r['Major pairs']} major / {r['Other pairs']} other",
                      "Major pairs: USD/HKD, EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CNH. Standard schedule for amounts up to USD 5 million equivalent.", (PRC + "2.4",)))
    markup = i.client.additional_markup.get("spot_fx")
    if markup:
        facts.append(Fact("Client-specific additional markup", f"+ {markup}", "Added on top of the standard spread (clause 2.3). Check the CRM profile before quoting.", (PRC + "2.3",), "warning"))
    band = amount_band_pricing(chunks, "Spot FX", i.amount_usd, (250_000, 5_000_000))
    if band:
        facts.append(Fact("Amount band", band, "From the amount you entered (USD equivalent).", (PRC + "2.10",)))
    return facts


def amount_band_pricing(chunks: Mapping[str, Chunk], product: str, amount: Optional[float], limits: tuple[float, float]) -> Optional[str]:
    """Pricing text from clause 2.10 for the band that contains the amount."""
    if not amount:
        return None
    rows = [r for r in table_rows(_content(chunks, PRC + "2.10")) if r["Product"] == product]
    if len(rows) < 3:
        return None
    idx = 0 if amount <= limits[0] else 1 if amount <= limits[1] else 2
    return f"{rows[idx]['Amount band']}: {rows[idx]['Pricing']}"


def _brokerage(chunks: Mapping[str, Chunk], row_name: str, tier: str) -> Optional[str]:
    for r in table_rows(_content(chunks, PRC + "2.5")):
        if r.get("Product") == row_name:
            return r.get(f"Tier {tier}")
    return None


def _custody(chunks: Mapping[str, Chunk], tier: str) -> Optional[str]:
    m = re.search(rf"Tier {tier} (\d\.\d{{2}}%)", _content(chunks, PRC + "2.6"))
    return m.group(1) if m else None


def _tier_margin(chunks: Mapping[str, Chunk], tier: str) -> Optional[str]:
    m = re.search(rf"Tier {tier} (\d\.\d{{2}}%)", _content(chunks, LND + "3.2"))
    return m.group(1) if m else None


def _base_rate(chunks: Mapping[str, Chunk], currency: str) -> Optional[str]:
    m = re.search(rf"{currency} (1-month [A-Za-z ]+?)(?=,| and |\.)", _content(chunks, LND + "3.1"))
    return m.group(1) if m else None


def _pricing_facts(chunks: Mapping[str, Chunk], i: ScenarioInputs) -> list[Fact]:
    tier = i.client.tier
    p = i.product
    if p == "spot_fx":
        return _fx_pricing(chunks, i)
    if p in ("hk_equity", "us_equity", "bond"):
        name = {"hk_equity": "Hong Kong listed equities", "us_equity": "US listed equities", "bond": "Bonds, secondary market"}[p]
        rate = _brokerage(chunks, name, tier)
        facts = [Fact(f"Tier {tier} brokerage", rate or "Not found", "Quote the schedule price; discounts need approval (clause 2.8).", (PRC + "2.5",), "info" if rate else "warning")]
        if p == "bond":
            band = amount_band_pricing(chunks, "Bonds, secondary market", i.amount_usd, (500_000, 5_000_000))
            if band:
                facts.append(Fact("Amount band", band, "From the nominal amount you entered.", (PRC + "2.10",)))
        cust = _custody(chunks, tier)
        if cust:
            facts.append(Fact("Custody fee (annual)", cust, "Charged quarterly on securities held in custody.", (PRC + "2.6",)))
        return facts
    if p == "fund":
        band = amount_band_pricing(chunks, "Investment funds, subscription fee", i.amount_usd, (250_000, 1_000_000))
        return [Fact("Fund subscription fee", band or "1.00% up to USD 250,000; 0.75% up to USD 1 million; 0.50% above",
                     "The same for every tier. Enter an amount to see your band." if not band else "The same for every tier.", (PRC + "2.10",))]
    if p == "structured":
        return [Fact("Pricing", "No separate brokerage", "The dealing margin is in the term sheet and does not change with the tier. Do not quote or estimate it verbally.", (PRC + "2.7",), "warning")]
    if p == "time_deposit":
        return [Fact("Fee", "No fee", "Time deposit placements carry no fee.", (PRC + "2.5",))]
    if p in ("overdraft", "loan"):
        margin = _tier_margin(chunks, tier)
        facts: list[Fact] = []
        if p == "overdraft":
            if i.currency not in ("HKD", "USD", "CNH", "EUR"):
                return [Fact("Overdraft", f"Not available in {i.currency}", "Set it up as a term loan instead.", (LND + "3.1",), "blocked")]
            base = _base_rate(chunks, i.currency)
            facts.append(Fact(f"{i.currency} overdraft rate, Tier {tier}", f"{base} + {margin}" if base and margin else "Not found",
                              "Within the approved limit and covered by lending value.", (LND + "3.1", LND + "3.2"), "info" if base and margin else "warning"))
            facts.append(Fact("Excess over limit", "Extra 2.00% on the excess", "At most 5 business days; an excess over 10% of the limit needs the Desk Head's approval first.", (LND + "3.3",), "warning"))
            facts.append(Fact("Unauthorised or shortfall", "Base rate + 6.00%", "Applies regardless of tier; a margin call is made at the same time.", (LND + "3.4",), "warning"))
        else:
            facts.append(Fact(f"Tier {tier} term loan margin", margin or "Not found", "Plus a tenor premium: up to 1 month +0.00%, 3 months +0.10%, 6 months +0.20%, 12 months +0.35%.", (LND + "3.2", LND + "3.5")))
        return facts
    return []


def _authentication_fact(i: ScenarioInputs) -> Optional[Fact]:
    p = i.product
    if p == "payment_in":
        return Fact("Authentication", "Level 2 to discuss the account", "Balances, positions and transactions need Level 2.", (AUT + "4.3",))
    if p == "payment_out":
        amount = i.amount_usd or 0
        if amount > 500_000:
            return Fact("Authentication", "Level 4", "A payment above USD 500,000 equivalent needs Level 4: call-back on the registered number and Operations sign-off.", (AUT + "4.5",), "warning")
        return Fact("Authentication", "Level 3, or Level 4 for a new third party", "A first payment to a new third-party beneficiary needs Level 4.", (AUT + "4.4", AUT + "4.5"))
    return Fact("Authentication", "Level 3", "Trade, deposit and loan instructions need Level 3 (including the passphrase).", (AUT + "4.4",))


def _risk_profile_fact(i: ScenarioInputs) -> Optional[Fact]:
    if i.product in ("payment_out", "payment_in"):
        return None
    c = i.client
    exp = risk_profile_expiry(c.risk_profile_reviewed)
    if risk_profile_valid(c.risk_profile_reviewed, i.today):
        left = days_left(c.risk_profile_reviewed, i.today)
        return Fact("Risk profile", f"{c.risk_profile}, reviewed {c.risk_profile_reviewed.isoformat()}", f"Valid until {exp.isoformat()} ({left} days left). The product's risk rating must not exceed the profile.", (PTR + "5.5",), "ok")
    return Fact("Risk profile", f"Overdue: reviewed {c.risk_profile_reviewed.isoformat()}", "Older than 12 months. The order cannot be taken until the RM refreshes the profile. The client cannot waive this.", (PTR + "5.5",), "blocked")


def _approval_fact(i: ScenarioInputs) -> Optional[Fact]:
    if i.product == "structured":
        big = (i.amount_usd or 0) > 2_000_000
        detail = "RM and Desk Head approve before execution, recorded in the approval system (email or chat approval is not valid), valid on the day given only."
        if big:
            return Fact("Approvals", "RM + Desk Head + Head of Private Banking", "Notional above USD 2 million equivalent: the Head of Private Banking must also approve. " + detail, (PTR + "5.7",), "warning")
        return Fact("Approvals", "RM + Desk Head", detail + " Above USD 2 million equivalent the Head of Private Banking must also approve.", (PTR + "5.7",), "warning")
    if i.product in ("spot_fx", "hk_equity", "us_equity", "bond", "fund"):
        return Fact("Discount approval", "Up to 20% RM; to 40% Desk Head; above 40% Head of Private Banking", "Staff may not offer a discount on their own; record it in the CRM before quoting.", (PRC + "2.8",))
    return None


def _professional_fact(i: ScenarioInputs) -> Optional[Fact]:
    if i.product != "structured":
        return None
    if i.client.professional_investor:
        return Fact("Professional Investor", "Yes", "Confirm the status in the system before the order.", (PTR + "5.6",), "ok")
    return Fact("Professional Investor", "No", "Professional Investor status is required for accumulators, decumulators and structured notes.", (PTR + "5.6",), "blocked")


def build_facts(chunks: Mapping[str, Chunk], i: ScenarioInputs) -> list[Fact]:
    facts: list[Fact] = []
    if i.product not in ("payment_out", "payment_in"):
        c = _cutoff_fact(chunks, i)
        if c and i.product in ("time_deposit", "loan"):
            facts.append(c)
    facts.extend(_pricing_facts(chunks, i))
    for f in (_authentication_fact(i), _risk_profile_fact(i), _professional_fact(i), _approval_fact(i)):
        if f:
            facts.append(f)
    return facts
