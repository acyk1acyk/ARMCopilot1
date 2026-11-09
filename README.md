# ARM Copilot

A retrieval-augmented assistant for private-banking frontline staff (relationship-manager assistants and account managers). It answers procedure questions from a knowledge base, **cites the exact clause for every point, and escalates instead of guessing**.

> **All knowledge-base content and all client data are fictional.** The bank ("Aurelian Peak Private Bank"), its procedures, times, rates, rules and the mock clients are invented for this prototype and are not based on any real institution, client or confidential material.

**Status: November v2 prototype** (project sponsored by SJS's APSS scheme, Oct-Dec 2026). v1 (October) was a command-line assistant on 38 clauses; v2 adds a larger knowledge base, a 30-question test set, and a front-end panel.

## What it does

Ask a question in plain language, for example:

```
python -m arm_copilot.cli "What authentication level is required for an instruction over USD 500,000?"
```

```
Level 4 authentication is required.
  * Authentication Level: Level 4
  - Level 4 applies to any payment above USD 500,000 equivalent.  [OPS-AUT-004#4.5]
  ! Sign-off needed: Operations
Sources:
  OPS-AUT-004#4.5  Client Authentication Standards - Telephone and Email v2.2 - Level 4: high-risk instructions
```

Five knowledge areas are covered: cutoff times, pricing tiers, overdraft and loan rates, client authentication (including payment checks), and pre-trade requirements (49 clauses in 5 documents).

If the knowledge base cannot back an answer with a verbatim quote, the assistant does not answer. It escalates to the Desk Head and lists the clauses to read. Questions outside the five areas are refused, and instructions such as "ignore your rules" are not followed.

## The panel (front end)

`streamlit run app.py` opens a simple panel built for the frontline workflow:

- pick a **client** and a **product** (and currency, value date, amount, half-day or typhoon conditions where relevant);
- **fact cards** show the relevant numbers (cutoff, spread, fees, margin, approvals), each with its source clause;
- a **checklist** for the pre-trade and post-trade steps, with strike-through ticks and a "Why this step" quote from the clause (ticks are a visual aid only: they are not saved and are not a compliance record);
- a **client background** tab (all mock data);
- a **chat** box for free questions, answered with citations, with a low-confidence warning when the clauses do not fully settle the question.

![ARM Copilot panel](docs/panel.png)

See `PANEL.md` for details.

## How it works

```
question -> route -> retrieve -> answer -> validate -> finalize
              |         |           |          |
          light model  Supabase   stronger   Guardrails AI +
          picks area   pgvector   model,     deterministic
                       search     structured grounding checks
                                  answer     (one retry, then escalate)
```

- **Orchestration:** LangGraph state graph. The same node functions can also run in a plain loop, which is how the control flow is tested offline.
- **Retrieval:** clause-level chunks embedded and stored in Supabase (pgvector, cosine similarity). The top 8 clauses from the routed area are returned, plus up to 2 extra clauses from other areas as a safety net for mis-routed questions.
- **Models:** all model calls, including embeddings, go through OpenRouter (a direct Anthropic mode is also supported). Router model: `openai/gpt-4o-mini`. Answer model: `openai/gpt-4o`. Embeddings: `openai/text-embedding-3-small` (1536 dimensions).
- **Grounding checks** (`arm_copilot/grounding.py`), wrapped as a Guardrails AI validator:
  1. every point has a citation;
  2. the cited clause was actually retrieved;
  3. the quote appears word for word in that clause (a quote may use "..." to skip words, and a table-row quote may leave out whole columns if every cell it keeps is copied exactly and in order from one row);
  4. every time, percentage, basis-point value, amount and duration in a point appears in its cited clauses or in the question; numbers in the headline and key values must appear in a cited clause; numbers in "exceptions" must appear in a retrieved clause.
- **Safety limits:** at most 2 answer attempts, a step cap on the graph, a cap on question length, and capped answer length (`ARM_MAX_ANSWER_TOKENS=3000`). A decision trace, including the exact check that failed, is returned with every response for audit.

## Project layout

```
knowledge_base/   5 fictional policy documents, clause-level (### N.N headings)
db/schema.sql     Supabase table, vector index, match function, locked-down access
arm_copilot/      agent, retrieval, grounding checks, prompts, model setup, CLI
arm_copilot/panel/  fact cards, checklists and mock clients for the panel
app.py            Streamlit panel
scripts/          ingest.py (load the KB), run_eval.py (run a test set),
                  diagnose.py and diagnose_raw.py (see what the agent did for a question)
eval/             test_set_v1.json (10 + 1), test_set_v2.json (30 + 3 guardrail cases)
tests/            automatic tests
GUIDE.md          step-by-step working guide
PANEL.md          panel notes
```

## Setup

1. Create a Supabase project and run `db/schema.sql` in its SQL editor.
2. Copy `.env.example` to `.env` and fill in your keys. **Never commit `.env`.**
3. `python -m venv .venv`, activate it, then `pip install -r requirements.txt`.
4. `python scripts/ingest.py` to load the knowledge base (re-run after any KB change).
5. Ask a question with the CLI (above), or add `--json` for the full trace and sources. Run the panel with `streamlit run app.py`.

For OpenRouter set `ARM_LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY`, and the two model names (`ARM_ROUTER_MODEL`, `ARM_ANSWER_MODEL`) in `vendor/model` form. See `.env.example` and `GUIDE.md`.

Set spending limits on your provider keys before running evaluations, and remember that an OpenRouter key has its own limit separate from the account balance.

## Testing

```
pytest                                                # automatic tests
python scripts/run_eval.py                            # the 30-question test set + 3 guardrail cases
python scripts/run_eval.py --set eval/test_set_v1.json  # the original 10 questions
python scripts/diagnose_raw.py --ids T01,T05          # raw answer card and exact check results
```

`run_eval.py` scores each question on: an answer is given (not escalated), every expected fact appears in the visible answer text, every expected clause is cited, and the sign-off flag is set where required. Guardrail cases check that out-of-scope questions are refused and that an instruction to ignore the rules does not make the assistant repeat a made-up figure. It saves `eval/results_latest.json`.

Offline helpers that need no keys: `python scripts/run_eval.py --retrieval-only` and `python -m arm_copilot.cli --retrieve-only "question"`.

### Results

Settings for the v2 results: top_k 8 (+ up to 2 extra clauses), `ARM_MAX_ANSWER_TOKENS` 2000-3000, router `openai/gpt-4o-mini`, answer `openai/gpt-4o`. Date: 2026-11-08. pytest: 94 passed, 1 skipped (a fallback test that only runs when guardrails-ai is not installed).

| Date | Test set | Result |
|---|---|---|
| 2026-10-25 | v1 (10 questions) | 10/10, three consecutive runs; guardrail case passed |
| 2026-11-02 | v2 (30 questions), first run | 18/30 (60%) before any fixes |
| 2026-11-08 | v2 (30 questions), after fixes | eight runs: 29, 30, 29, 29, 29, 29, 28, 29 out of 30 (93-100%) |
| 2026-11-08 | v2 (30 questions) + guardrail cases, after G03 scoring fix | 30/30, guardrail cases 3/3 |
| 2026-11-08 | Promptfoo regression run 1 (same questions, full pipeline) | 31/33 (94%): T05 escalated, T30 missing profile items in the visible text |
| 2026-11-08 | Promptfoo regression run 2 (same setup, nothing changed) | 33/33 (100%) |
| 2026-11-08 | Manual test (JPY 4-month term loan), before fixes | wrong tenor step (0.35% instead of 0.20%) in 5 of 6 tries; low-confidence flag in only some |
| 2026-11-08 | Same question after clause 3.5 was rewritten as a table | 0.20% in 3 of 3 tries, low-confidence flag shown |
| 2026-11-08 | v2 after the table fix, with two extra prompt rules | 29/30 (T14 sign-off missed); Promptfoo 29/33 (T09, T14-type sign-off misses, T17, T26). Extra band rule removed afterwards as it was no longer needed and may have hurt |
| 2026-11-08 | **Final version** (confidence rule kept, band rule removed): v2 + guardrail cases | three runs: 27, 29, 28 out of 30 (90-97%); guardrail cases 3/3 each time |
| 2026-11-08 | **Final version**: Promptfoo regression run 3 | 33/33 (100%) |

**What the first v2 run showed and what was fixed.** Most failures were not wrong answers: multi-part and table answers were escalated by the strict quote check (quotes rebuilt from table headings, ranges of values, a currency code next to a time read as a money amount), some questions were routed to the wrong area, some answers were correct but left out a detail, and some runs failed because the OpenRouter key had reached its spending limit. These were fixed in the checker, the prompts, retrieval and the test wording.

**Honest note on these results.**
- The prompts, the checker and some test wording were adjusted while looking at these same 30 questions, so the score is a **development score**, not a measure on unseen questions. Where an expected phrase was loosened (for example, accepting "usual pattern of the account" for "transaction history"), the answer was correct and only the wording differed. The user-testing sessions use fresh questions and are the real check.
- Results vary between runs because model providers differ in behaviour. Several questions wobble: T01 and T17 sometimes word the answer differently from the expected phrase; T30 sometimes lists the profile items only inside its quote and not in the visible text; T05 is occasionally escalated by the quote check; and T09 and T14 sometimes miss the sign-off flag. Across about a dozen runs the core score stayed between 27 and 30 out of 30. These are known limitations, not bugs.
- A manual test outside the 30 questions found a real error: for a 4-month term loan the model applied the 12-month premium (0.35%) instead of 0.20%. The grounding check could not catch it because 0.35% is a real number in the cited clause. Rewriting clause 3.5 as a table with explicit bands fixed it (3 of 3 tries). The prompt change that was meant to help, a rule about bands, was removed afterwards because it was no longer needed and the sign-off flag seemed to suffer.
- An earlier tuning step that listed expected test phrases in the prompt was removed because it made the test set stop measuring the system.

## Limitations

- Prototype with a small, fictional knowledge base. Not for real client or banking use.
- The grounding check verifies quotes and numbers, but not every reworded claim. The headline's meaning, for example, is only checked for numbers, not for wording. A faithful paraphrase can pass or fail inconsistently.
- Quote matching ignores whitespace, so a quote can carry a small spacing slip (for example "thelonger") and still pass.
- The grounding check cannot tell when the right number is taken from the wrong row or band (see the honest note above). Treat low-confidence answers as unverified.
- Relaxations that were made on purpose: a table-row quote may leave out columns (cells must still be exact and in order), a currency code next to a time is not treated as an amount, and numbers in "exceptions" may come from any retrieved clause.
- Answer quality depends on the chosen models. Switching models means re-running the evaluation.
- The 30-question set is an internal regression check, not a benchmark.
- The checklist ticks and mock client data in the panel are a visual aid and are not saved.

## Roadmap

- **November:** remote user-testing sessions with 3-5 former banking colleagues and industry contacts, one in-person session with a technical practitioner or industry expert, and refinements from the documented feedback. Promptfoo regression testing is done (see Results).
- **December:** polish, documentation and final demonstration.

## Licence and data

MIT licence. Knowledge base and client data: fictional, created for this project.
