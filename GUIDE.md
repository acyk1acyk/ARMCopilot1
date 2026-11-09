# ARM Copilot: working guide (step by step)

Go in order. Each step says how you know it worked. If a step fails, stop and note the exact error text.

All knowledge-base content and client data are fictional ("Aurelian Peak Private Bank").

## 0. What each file is for

| Where | What it is | Do you edit it? |
|---|---|---|
| `knowledge_base/*.md` | The 5 fictional documents the assistant answers from (49 clauses) | Yes: improve wording, keep fictional |
| `db/schema.sql` | Creates the vector table in Supabase | Run once, don't edit |
| `scripts/ingest.py` | Reads the KB, makes embeddings, uploads to Supabase | Re-run after every KB change |
| `arm_copilot/prompts.py` | The instructions given to the models | Rarely; re-run the evaluation after any change |
| `arm_copilot/agent.py` | The LangGraph flow: route, retrieve, answer, validate | Rarely |
| `arm_copilot/grounding.py` | The citation, quote and number checks | Rarely |
| `arm_copilot/retrieval.py` | Clause search (top 8 + up to 2 extra from other areas) | Rarely |
| `arm_copilot/config.py` | Defaults and limits | Rarely; use `.env` instead |
| `app.py` and `arm_copilot/panel/` | The Streamlit panel: fact cards, checklists, mock clients | Yes, for interface changes |
| `eval/test_set_v1.json` | The original 10 questions (October) | No: kept as a record |
| `eval/test_set_v2.json` | The 30 questions + 3 guardrail cases (November) | Yes, add questions |
| `promptfoo/`, `promptfooconfig.yaml` | Promptfoo regression run over the v2 set | Regenerate tests after editing the v2 set |
| `tests/` | Automatic checks (95 tests) | Run them, don't edit at first |
| `.env` | Your secret keys and settings (you create it) | Yes. Never share or upload it |

## 1. Install the tools (one time)

1. Install Python 3.11 or newer (Windows: tick "Add Python to PATH"). A conda environment also works.
2. Install VS Code. Open the project folder with File > Open Folder.
3. Open the built-in terminal. Check: `python --version` shows 3.11 or higher. On Mac/Linux you may need `python3`.
4. For Promptfoo (step 11) install Node.js. Check: `node -v`.

## 2. Create an environment and install packages

```
python -m venv .venv
```
Activate it:
- Mac/Linux: `source .venv/bin/activate`
- Windows PowerShell: `.venv\Scripts\Activate.ps1`

Then: `pip install -r requirements.txt`, and `pip install streamlit` if it is not in requirements.

You know it worked when the terminal line starts with `(.venv)` (or your conda env name) and pip ends without red errors.

## 3. Run the tests

```
pytest
```
Expected: 94 passed, 1 skipped (a fallback test that only runs when guardrails-ai is not installed). If some fail, send the output.

## 4. Create your keys and `.env`

1. Copy `.env.example` to a new file named `.env` (same folder).
2. You fill it in over the next steps. `.env` is private. Never paste keys into chat or commit them. Only `.env.example` goes to GitHub.

## 5. Supabase (the vector database)

1. Make a free project at supabase.com.
2. Left menu > SQL Editor > New query. Paste all of `db/schema.sql` and press Run. You should see "Success".
3. Project Settings > API: copy the Project URL into `SUPABASE_URL`, and the `service_role` key into `SUPABASE_SERVICE_KEY`. That key is powerful, so keep it server-side only.

## 6. Choose how the models are reached

You can go direct to Anthropic, or through OpenRouter. Pick one.

### Option A: Direct Anthropic
Create a key at console.anthropic.com, set a monthly spending limit there, and put it in `ANTHROPIC_API_KEY`. Leave `ARM_LLM_PROVIDER=anthropic`. Embeddings then need `OPENAI_API_KEY` (with a spending limit).

### Option B: OpenRouter (one key, many models; what the November results used)
1. Sign up at openrouter.ai and add a small amount of credit.
2. Go to openrouter.ai/keys and create a key. **An OpenRouter key has its own credit limit, separate from your account balance.** If requests fail with a 402 "can only afford N tokens" error, raise the limit on the key itself (for example to USD 10), not just the account balance.
3. Choose two models from openrouter.ai/models: a cheap fast one for routing and a stronger one for answering. Copy the exact names in `vendor/model` form.
4. In `.env`:
   ```
   ARM_LLM_PROVIDER=openrouter
   OPENROUTER_API_KEY=your-key
   ARM_ROUTER_MODEL=vendor/cheap-model
   ARM_ANSWER_MODEL=vendor/strong-model
   ARM_TOP_K=8
   ARM_MAX_ANSWER_TOKENS=3000
   ```
5. To switch models later, change only the two model lines, then re-run the evaluation.

Embeddings also go through OpenRouter in this mode (`openai/text-embedding-3-small`, 1536 dimensions), so no separate `OPENAI_API_KEY` is needed. Keep the same embedding model for ingest and search, or results will be wrong.

The answer model must support tool or function calling, because the structured answer card uses it (check "tools" on the model's OpenRouter page).

## 7. Load the knowledge base

```
python scripts/ingest.py --dry-run
python scripts/ingest.py
```
The first lists the 49 clauses without uploading. The second uploads them. Check in Supabase > Table Editor > `kb_chunks` that there are 49 rows. Re-run `ingest.py` after any KB change.

## 8. Ask a question

```
python -m arm_copilot.cli "What is the USD same-day cutoff for a time deposit?"
```
You should get a short answer, every point with a clause citation. Then try an out-of-scope question (for example about crypto withdrawals): it should be refused or escalated, not answered. Add `--json` to see the full trace.

## 9. Run the evaluation

```
python scripts/run_eval.py                              # the 30-question v2 set + 3 guardrail cases
python scripts/run_eval.py --set eval/test_set_v1.json  # the original 10 questions
```
Each question prints PASS or FAIL with the reason. Results are saved to `eval/results_latest.json`.

The November target is over 90% (27 of 30) on the v2 set. Results vary a little between runs (for example T05, T17 and T30 occasionally fail), so judge from several runs and record them in the README results table. Remember that the v2 score is a development score, because the prompts and checks were tuned on these same questions.

To see exactly what happened for one question:
```
python scripts/diagnose_raw.py --ids T01,T05
```
Use commas with no spaces. It prints the route, the clauses retrieved, the raw answer card and the exact grounding check results.

## 10. Run the panel

```
streamlit run app.py
```
It opens in your browser. Choose a client (the tier comes from the client) and a product. The fact cards and checklist work without keys; the chat needs `.env`. Cutoff facts for currency, value date, half-day and typhoon only apply to the time deposit and loan products. See `PANEL.md`. Ticks are not saved and are not a compliance record.

## 11. Run Promptfoo (regression run)

```
python scripts/make_promptfoo_tests.py      # only needed after editing eval/test_set_v2.json
PROMPTFOO_PYTHON=$(which python) npx promptfoo@latest eval --no-cache -j 2
npx promptfoo@latest view
```
This runs the same 33 cases through the real pipeline and scores them with the same rules as `run_eval.py`. It costs about the same as one evaluation run. Export a run with `npx promptfoo@latest export eval <eval-id> -o eval/promptfoo_results_<date>.json`.

## 12. Everyday workflow

1. Edit a KB file.
2. `pytest` (checks the files still parse and the test sets still match).
3. `python scripts/ingest.py` (re-upload).
4. `python scripts/run_eval.py`.
If the answers look wrong, first check the retrieved clauses with `python -m arm_copilot.cli --retrieve-only "question"`. Most problems are retrieval or a missing clause, not the model.

Before committing: run `git status` and make sure `.env` is not listed.

## Troubleshooting

- `ModuleNotFoundError`: the environment isn't active, or step 2 didn't finish.
- `OPENROUTER_API_KEY is not set` / "not an OpenRouter model name": check `.env` (no quotes, no spaces) and the `vendor/model` form.
- 401 or 403 from a provider: the key is wrong or has no credit.
- 402 "can only afford N tokens": the OpenRouter key's own limit is too low (step 6).
- Answers escalate too often: that's the guardrail working. Look at the decision trace for the exact check that failed.
- `diagnose_raw.py` shows nothing for a long time: use comma-separated ids (`--ids T01,T05`), and check the key limit.
- `streamlit run app.py` says the file does not exist: you are in the wrong folder, or the panel files were not copied into the project root.
- `pytest` fails in `test_eval_set_v2.py` for G03: `arm_copilot/evaluation.py` is the old version (it must contain `must_not_say`), or the file was saved outside the `arm_copilot/` folder.