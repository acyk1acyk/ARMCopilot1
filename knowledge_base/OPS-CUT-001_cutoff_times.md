---
doc_id: OPS-CUT-001
title: Transaction Cutoff Times - Deposits and Loans
category: cutoff_times
version: "3.2"
effective_date: 2026-07-01
owner: Private Banking Operations (fictional)
status: active
---

# OPS-CUT-001 Transaction Cutoff Times - Deposits and Loans

> FICTIONAL DOCUMENT. Written for the ARM Copilot prototype. Aurelian Peak Private Bank does not exist, and nothing here is based on any real bank's procedures, rates or times.

### 1.1 Scope and how to read the cutoff tables

This standard applies to instructions received by the Client Account desk for time deposit placements, time deposit rollovers, loan drawdowns, loan rollovers and loan repayments. All times are Hong Kong Time (HKT) and refer to the time the instruction is received and recorded by the desk, not the time the client sent it. Cutoffs depend on the currency and on the value date. "T" means same-day value, "T+1" means value on the next business day, and "T+2" means value two or more business days after the instruction date.

### 1.2 Deposit cutoff times by currency

Cutoff times for time deposit placements and rollovers (HKT):

| Currency | T (same day) | T+1 | T+2 or later |
|----------|--------------|-------|--------------|
| HKD | 15:30 | 17:00 | 17:00 |
| USD | 12:00 | 16:30 | 17:00 |
| CNH | 11:00 | 16:00 | 17:00 |
| EUR | 15:00 | 16:30 | 17:00 |
| GBP | 16:30 | 17:00 | 17:00 |
| JPY | 11:30 | 16:00 | 17:00 |
| AUD | 12:30 | 16:30 | 17:00 |

### 1.3 Loan cutoff times by currency

Cutoff times for loan drawdowns, loan rollovers and loan repayments (HKT). Loan cutoffs are not the same as deposit cutoffs; always use this table for loans:

| Currency | T (same day) | T+1 | T+2 or later |
|----------|--------------|-------|--------------|
| HKD | 15:00 | 16:30 | 17:00 |
| USD | 11:30 | 16:00 | 17:00 |
| CNH | 10:30 | 15:30 | 17:00 |
| EUR | 14:30 | 16:00 | 17:00 |
| GBP | 16:00 | 16:30 | 17:00 |
| JPY | 11:00 | 15:30 | 17:00 |
| AUD | 12:00 | 16:00 | 17:00 |

### 1.4 Rollover instructions and standing auto-rollover

A one-off rollover instruction must be received before the cutoff for the maturity date in the table that applies to the product (deposit or loan). A standing auto-rollover instruction, for example for weekly rollovers, must be registered with Operations at least 2 business days before the first rollover date. Until Operations confirms that the standing instruction is active, the Client Account desk must roll over each maturity manually. A rollover instruction received after the cutoff is processed on the next business day at the prevailing rate, and the client must be told this before the cutoff has passed whenever possible.

### 1.5 Instructions received after the cutoff

An instruction received after the cutoff is not guaranteed for the requested value date. For HKD and USD only, the Desk Head may approve a best-effort late acceptance for same-day (T) value. A late acceptance fee of HKD 200 applies, and the client must be informed in writing by email of the final value date. For all other currencies there is no late acceptance, and the instruction rolls to the next available value date.

### 1.6 Public holidays and non-business days

If the requested value date is not a business day for the currency's settlement centre, the value date moves to the next business day. The cutoff is then read from the table for the number of business days between the instruction date and the adjusted value date: 0 business days is T, 1 is T+1, and 2 or more is T+2 or later. Operations publishes the holiday calendar for each settlement centre every December.

### 1.7 Half-day trading days and severe weather

On half-day trading days, any cutoff later than 12:00 HKT is brought forward to 12:00 HKT. Cutoffs that are already earlier than 12:00 HKT do not change. If Typhoon Signal No. 8 or above, or a Black Rainstorm Warning, is in force at 09:00 HKT, same-day (T) value instructions are not accepted in any currency, and instructions are processed as T+1 instructions for the next business day.
