# ARM Copilot

A retrieval-augmented assistant for private-banking frontline staff (relationship-manager assistants and account managers). It answers procedure questions from a knowledge base, **cites the exact clause for every point, and escalates instead of guessing**.

> **All knowledge-base content is fictional.** The bank ("Aurelian Peak Private Bank"), its procedures, times, rates and rules are invented for this prototype and are not based on any real institution.

**Status: October v1 prototype** (project sponsored by SJS's APSS scheme, Oct-Dec 2026).

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
  OPS-AUT-004#4.5  Client Authentication Standards - Telephone and Email v2.1 - Level 4: high-risk instructions
```

Five knowledge areas are covered: cutoff times, pricing tiers, overdraft and loan rates, client authentication, and pre-trade requirements (38 clauses in 5 documents).

If the knowledge base cannot back an answer with a verbatim quote, the assistant does not answer. It escalates to the Desk Head and lists the clauses to read. Questions outside the five areas are refused.

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
- **Retrieval:** clause-level chunks embedded and stored in Supabase (pgvector, cosine similarity).
- **Models:** all model calls, including embeddings, go through OpenRouter. A direct Anthropic mode is also supported.
- **Grounding checks** (`arm_copilot/grounding.py`), wrapped as a Guardrails AI validator:
  1. every point has a citation;
  2. the cited clause was actually retrieved;
  3. the quote appears word for word in that clause;
  4. every time, percentage, basis-point value, amount and duration in the answer appears in the cited clause or in the question.
- **Safety limits:** at most 2 answer attempts, a step cap on the graph, a cap on question length, and capped answer length. A decision trace is returned with every response for audit.

## Project layout

```
knowledge_base/   5 fictional policy documents, clause-level (### N.N headings)
db/schema.sql     Supabase table, vector index, match function, locked-down access
arm_copilot/      agent, retrieval, grounding checks, prompts, model setup, CLI
scripts/          ingest.py (load the KB into Supabase), run_eval.py (run the test set)
eval/             test_set_v1.json: 10 core questions + 1 guardrail case
tests/            automatic tests
GUIDE.md          step-by-step working guide
```

## Setup

1. Create a Supabase project and run `db/schema.sql` in its SQL editor.
2. Copy `.env.example` to `.env` and fill in your keys. **Never commit `.env`.**
3. `python -m venv .venv`, activate it, then `pip install -r requirements.txt`.
4. `python scripts/ingest.py` to load the knowledge base.
5. Ask a question with the CLI (above), or add `--json` for the full trace and sources.

For OpenRouter set `ARM_LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY`, and the two model names (`ARM_ROUTER_MODEL`, `ARM_ANSWER_MODEL`) in `vendor/model` form. See `.env.example` and `GUIDE.md`.

Set spending limits on your provider keys before running evaluations.

## Testing

```
pytest                      # automatic tests
python scripts/run_eval.py  # the 10-question internal test set + guardrail case
```

`run_eval.py` checks that each core question is answered with the expected facts and citations, and that the guardrail question (a topic not in the knowledge base) is refused. It saves `eval/results_latest.json`.

Offline helpers that need no keys: `python scripts/run_eval.py --retrieval-only` and `python -m arm_copilot.cli --retrieve-only "question"`.

### Results so far

| Date | Check | Result |
|---|---|---|
| 2026-10-25 | `pytest` | 61 passed, 1 skipped |
| 2026-10-25 | `run_eval.py` | 10/10 core questions, guardrail case passed |

**Honest note on stability:** earlier runs the same day scored between 7/10 and 9/10 while the setup was being tuned. The misses were escalations, not wrong answers: the strict quote check rejected a quote that did not match the clause word for word, and the routing model occasionally failed on a provider error. Results can vary between runs because model providers differ in behaviour, so repeated runs are the measure of stability. Three consecutive runs on 2026-10-25 after the quote-format prompt fix each scored 10/10 core questions with the guardrail case passing. Results can still vary with model provider behaviour, so the 30-question set in November will test stability more thoroughly.

## Limitations

- Prototype with a small, fictional knowledge base. Not for real client or banking use.
- The grounding check verifies quotes and numbers, but not every reworded claim. A paraphrase that is faithful but not a quote of a number can pass or fail inconsistently.
- Answer quality depends on the chosen models. Switching models means re-running the evaluation.
- The 10-question set is an early check, not a benchmark.

## Roadmap

- **November:** expand to a 30-question set, add automated regression testing, improve answer wording and the quote rules, simple front end.
- **December:** polish, documentation and final demonstration.

## Licence and data

Code: add your chosen licence here. Knowledge base: fictional, created for this project.
