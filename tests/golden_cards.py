"""Hand-written ideal answers for the 10 test questions.

They prove two things: the test set can be solved from the knowledge base, and the citation
checker accepts a correct, well-quoted answer (so it is not stricter than intended).
"""

from __future__ import annotations

from arm_copilot.schemas import AnswerCard, Citation, KeyValue, Point


def _p(text: str, *cites: tuple[str, str]) -> Point:
    return Point(text=text, citations=[Citation(chunk_id=c, quote=q) for c, q in cites])


GOLDEN: dict[str, AnswerCard] = {
    "Q01": AnswerCard(
        headline="USD time deposit with same-day (T) value: cutoff 12:00 HKT.",
        key_values=[KeyValue(label="USD deposit cutoff (T)", value="12:00 HKT")],
        points=[_p("For a USD time deposit with same-day value the cutoff is 12:00 HKT.", ("OPS-CUT-001#1.2", "| USD | 12:00 | 16:30 | 17:00 |"))],
    ),
    "Q02": AnswerCard(
        headline="GBP loan drawdown, T+1 value: cutoff 16:30 HKT.",
        key_values=[KeyValue(label="GBP loan cutoff (T+1)", value="16:30 HKT")],
        points=[
            _p(
                "Loans use their own table, not the deposit table. For GBP with T+1 value the loan cutoff is 16:30 HKT.",
                ("OPS-CUT-001#1.3", "Loan cutoffs are not the same as deposit cutoffs"),
                ("OPS-CUT-001#1.3", "| GBP | 16:00 | 16:30 | 17:00 |"),
            )
        ],
    ),
    "Q03": AnswerCard(
        headline="HKD deposit, T+1, on a half-day trading day: cutoff 12:00 HKT.",
        key_values=[KeyValue(label="HKD deposit cutoff (T+1), half-day", value="12:00 HKT")],
        points=[
            _p("The usual HKD deposit cutoff for T+1 is 17:00 HKT.", ("OPS-CUT-001#1.2", "| HKD | 15:30 | 17:00 | 17:00 |")),
            _p(
                "On half-day trading days any cutoff later than 12:00 HKT is brought forward to 12:00 HKT.",
                ("OPS-CUT-001#1.7", "any cutoff later than 12:00 HKT is brought forward to 12:00 HKT"),
            ),
        ],
    ),
    "Q04": AnswerCard(
        headline="Tier B, EUR/USD: 8 bps.",
        key_values=[KeyValue(label="Tier B major-pair spread", value="8 bps")],
        points=[
            _p(
                "EUR/USD is a major pair, and the Tier B spread on major pairs is 8 bps for amounts up to USD 5 million equivalent.",
                ("OPS-PRC-002#2.4", "| B | 8 bps | 13 bps |"),
                ("OPS-PRC-002#2.4", "Major pairs are USD/HKD, EUR/USD"),
            )
        ],
        exceptions=["Check first whether the client has a signed Client Pricing Agreement."],
    ),
    "Q05": AnswerCard(
        headline="A 30% discount needs Desk Head approval.",
        points=[
            _p(
                "Discounts of more than 20% and up to 40% need the Desk Head. Staff may not offer a discount on their own.",
                ("OPS-PRC-002#2.8", "more than 20% and up to 40% needs the Desk Head"),
                ("OPS-PRC-002#2.8", "Staff may not offer a discount to the schedule on their own"),
            )
        ],
        requires_signoff=True,
        signoff_by="Desk Head",
    ),
    "Q06": AnswerCard(
        headline="1-month Term SOFR + 1.85%.",
        key_values=[KeyValue(label="Tier B USD overdraft within limit", value="1-month Term SOFR + 1.85%")],
        points=[
            _p(
                "Within the approved limit and fully covered by lending value, the Tier B margin over the base rate is 1.85%.",
                ("OPS-LND-003#3.2", "Tier B 1.85%"),
                ("OPS-LND-003#3.2", "1-month Term SOFR + 1.85%"),
            )
        ],
    ),
    "Q07": AnswerCard(
        headline="No. Overdrafts are not available in JPY; it has to be a term loan.",
        points=[
            _p(
                "Overdrafts are available only in HKD, USD, CNH and EUR. JPY borrowing must be set up as a term loan.",
                ("OPS-LND-003#3.1", "Overdrafts are available only in HKD, USD, CNH and EUR"),
                ("OPS-LND-003#3.1", "must be set up as a term loan"),
            )
        ],
    ),
    "Q08": AnswerCard(
        headline="Level 4 authentication.",
        points=[
            _p(
                "A first payment to a new third-party beneficiary is a Level 4 instruction.",
                ("OPS-AUT-004#4.5", "Level 4 applies to the first payment to a new third-party beneficiary"),
            ),
            _p(
                "Complete Level 3, then call the client back on the registered number held on file.",
                ("OPS-AUT-004#4.5", "must also call the client back on the registered number held on file"),
            ),
            _p(
                "Operations must sign off before the payment is released.",
                ("OPS-AUT-004#4.5", "The instruction cannot be released until Operations gives sign-off"),
            ),
        ],
        requires_signoff=True,
        signoff_by="Operations",
    ),
    "Q09": AnswerCard(
        headline="Bond order: six details to take.",
        points=[
            _p(
                "Take the ISIN, the nominal amount, buy or sell, the price (clean price) or yield, the settlement date and the settlement account.",
                (
                    "OPS-PTR-005#5.3",
                    "the ISIN, the nominal amount, buy or sell, the price (clean price) or yield, the settlement date, and the settlement account",
                ),
            ),
            _p(
                "Also confirm the nominal amount meets the bond's minimum denomination.",
                ("OPS-PTR-005#5.3", "meets the bond's minimum denomination"),
            ),
        ],
    ),
    "Q10": AnswerCard(
        headline="You need approval from the RM, the Desk Head and the Head of Private Banking.",
        points=[
            _p(
                "An accumulator needs approval from the RM and the Desk Head before execution.",
                ("OPS-PTR-005#5.7", "needs approval from the RM and the Desk Head before execution"),
            ),
            _p(
                "Your USD 3 million notional is above USD 2 million equivalent, so the Head of Private Banking must also approve.",
                ("OPS-PTR-005#5.7", "the Head of Private Banking must also approve"),
            ),
            _p(
                "Approvals must be recorded in the approval system; email or chat approval is not valid.",
                ("OPS-PTR-005#5.7", "email or chat approval is not valid"),
            ),
        ],
        requires_signoff=True,
        signoff_by="RM, Desk Head and Head of Private Banking",
    ),
}
