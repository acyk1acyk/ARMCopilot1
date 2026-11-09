---
doc_id: OPS-LND-003
title: Lombard Overdraft and Loan Pricing
category: overdraft_rates
version: "1.9"
effective_date: 2026-05-15
owner: Private Banking Credit and Lending (fictional)
status: active
---

# OPS-LND-003 Lombard Overdraft and Loan Pricing

> FICTIONAL DOCUMENT. Written for the ARM Copilot prototype. Aurelian Peak Private Bank does not exist, and nothing here is based on any real bank's procedures, rates or margins.

### 3.1 Scope and base rates by currency

This standard covers securities-backed (Lombard) overdrafts and term loans. Overdrafts are available only in HKD, USD, CNH and EUR. Borrowing in any other currency (GBP, JPY, AUD) must be set up as a term loan; no overdraft is available in those currencies. The interest rate is the base rate for the currency plus a margin. The base rates are: HKD 1-month HIBOR, USD 1-month Term SOFR, CNH 1-month CNH HIBOR and EUR 1-month EURIBOR. The base rate is fixed on the first business day of each month.

### 3.2 Standard overdraft margin by tier

For an overdraft that is within the approved limit and fully covered by lending value, the margin over the base rate is: Tier A 1.50%, Tier B 1.85% and Tier C 2.25%. The same margin applies in every currency. For example, a Tier B client's USD overdraft within limit costs 1-month Term SOFR + 1.85%.

### 3.3 Excess over the approved limit

An overdraft above the approved limit that has been approved on a temporary basis costs an extra 2.00% on the excess amount, on top of the standard margin for the client's tier. A temporary excess can last at most 5 business days. After that, the excess must be referred to Credit. An excess of more than 10% of the approved limit needs the Desk Head's approval before it is allowed.

### 3.4 Unauthorised overdraft and collateral shortfall

An overdraft with no approved limit, or an overdraft that is not covered by lending value because of a collateral shortfall, is charged a penalty rate of the base rate + 6.00% on the amount overdrawn without authorisation. The penalty rate applies regardless of the client's tier. A margin call is made at the same time as the penalty rate starts.

### 3.5 Term loan tenor premium

Term loans pay the standard margin for the client's tier plus a tenor premium, according to the tenor of the loan:

| Tenor of the loan | Tenor premium |
|-------------------|---------------|
| Up to 1 month | +0.00% |
| Over 1 month, up to 3 months | +0.10% |
| Over 3 months, up to 6 months | +0.20% |
| Over 6 months, up to 12 months | +0.35% |

A tenor between two steps takes the premium of the longer step. Term loans are available in HKD, USD, CNH, EUR, GBP, JPY and AUD.

### 3.6 Interest accrual and rate changes

Interest accrues daily, on an Actual/365 basis for HKD and on an Actual/360 basis for USD, CNH and EUR. Interest accrues at the same daily rate over weekends and public holidays. Margins are reviewed once a year, and any change needs 30 days' written notice to the client.

### 3.7 Notifying the client

The client must be told on the same business day whenever an excess over the limit (clause 3.3) or an unauthorised overdraft (clause 3.4) occurs. The notification is made by phone and confirmed by email, and the call must be recorded in the call report.
