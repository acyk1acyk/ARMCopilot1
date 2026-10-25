# ARM Copilot: working guide (step by step)

Go in order. Each step says how you know it worked. If a step fails, stop and send me the exact error text.

## 0. What each file is for

| Where | What it is | Do you edit it? |
|---|---|---|
| `knowledge_base/*.md` | The 5 fictional documents the assistant answers from | Yes: improve wording, keep fictional |
| `db/schema.sql` | Creates the vector table in Supabase | Run once, don't edit |
| `scripts/ingest.py` | Reads the KB, makes embeddings, uploads to Supabase | Re-run after every KB change |
| `arm_copilot/prompts.py` | The instructions given to the models | Yes, later, when tuning |
| `arm_copilot/agent.py` | The LangGraph flow: route, retrieve, answer, validate | Rarely |
| `arm_copilot/grounding.py` | The citation and number checks | Rarely |
| `arm_copilot/config.py` | Defaults and limits | Rarely; use `.env` instead |
| `eval/test_set_v1.json` | The 10 test questions | Yes, add questions in November |
| `tests/` | Automatic checks | Run them, don't edit at first |
| `.env` | Your secret keys and settings (you create it) | Yes. Never share or upload it |

## 1. Install the tools (one time)

1. Install Python 3.11 or newer from python.org (Windows: tick "Add Python to PATH").
2. Install VS Code (code.visualstudio.com). Unzip `arm-copilot.zip`, then in VS Code use File > Open Folder and pick `arm-copilot`.
3. Open the built-in terminal (Terminal > New Terminal). Check: `python --version` shows 3.11 or higher. On Mac/Linux you may need `python3`.

## 2. Create a virtual environment and install packages

```
python -m venv .venv
```
Activate it:
- Mac/Linux: `source .venv/bin/activate`
- Windows PowerShell: `.venv\Scripts\Activate.ps1`

Then: `pip install -r requirements.txt`

You know it worked when the terminal line starts with `(.venv)` and pip ends without red errors.

## 3. Run the tests

```
pytest
```
Before, 62 ran offline with 8 skipped. Now the skipped ones (LangGraph and Guardrails) should run too. If some fail, send me the output. That is expected on a first real run.

## 4. Create your keys and `.env`

1. Copy `.env.example` to a new file named `.env` (same folder).
2. You will fill it in over the next steps. `.env` is private. Never paste keys into chat or commit them.

## 5. Supabase (the vector database)

1. Make a free project at supabase.com.
2. Left menu > SQL Editor > New query. Paste all of `db/schema.sql` and press Run. You should see "Success".
3. Project Settings > API: copy the Project URL into `SUPABASE_URL`, and the `service_role` key into `SUPABASE_SERVICE_KEY`. That key is powerful, so keep it server-side only.

## 6. Choose how the chat models are reached

You can go direct to Anthropic, or through OpenRouter. Pick one.

### Option A: Direct Anthropic
Create a key at console.anthropic.com, set a monthly spending limit there, and put it in `ANTHROPIC_API_KEY`. Leave `ARM_LLM_PROVIDER=anthropic`.

### Option B: OpenRouter (one key, many models)
1. Sign up at openrouter.ai and add a small amount of credit (US$5 is plenty for this project).
2. Go to openrouter.ai/keys and create a key. If there is a credit-limit option, set a low one. Put the key in `OPENROUTER_API_KEY`.
3. Go to openrouter.ai/models and choose two models: a cheap fast one for routing and a stronger one for answering. Copy each model's exact name, which has the form `vendor/model`.
4. In `.env`:
   ```
   ARM_LLM_PROVIDER=openrouter
   OPENROUTER_API_KEY=your-key
   ARM_ROUTER_MODEL=vendor/cheap-model
   ARM_ANSWER_MODEL=vendor/strong-model
   ```
5. To switch models later, change only those two lines. No code changes.

How it works: OpenRouter speaks the same protocol as OpenAI, so the code points the OpenAI client at `https://openrouter.ai/api/v1`. That's the only difference.

Two things to know:
- The answerer must support tool or function calling, because the structured answer card uses it. On each model's OpenRouter page check that "tools" is supported.
- Embeddings (turning text into numbers for search) still use OpenAI directly, so you still need `OPENAI_API_KEY` and a spending limit there. Keep the same embedding model for ingest and search, or the results will be wrong.

## 7. Load the knowledge base

```
python scripts/ingest.py --dry-run
python scripts/ingest.py
```
The first lists the 38 clauses without uploading. The second uploads them. Check in Supabase > Table Editor > `kb_chunks` that there are 38 rows.

## 8. Ask a question

```
python -m arm_copilot.cli "What is the USD same-day cutoff for a time deposit?"
```
You should get a short answer, every point with a clause citation. Then try the trap question about crypto withdrawals: it should escalate and not answer.

## 9. Run the October milestone check

```
python scripts/run_eval.py
```
This runs the 10 questions and the guardrail case and prints pass or fail for each. Target: 10 of 10. Results are saved to `eval/results_latest.json`. Screenshot this for SJS.

## 10. Everyday workflow

1. Edit a KB file.
2. `pytest` (checks the files still parse and the test set still matches).
3. `python scripts/ingest.py` (re-upload).
4. `python scripts/run_eval.py`.
If the answers look wrong, first check the retrieved clauses with `python -m arm_copilot.cli --retrieve-only "question"`. Most problems are retrieval or a missing clause, not the model.

## Troubleshooting

- `ModuleNotFoundError`: the virtual environment isn't active, or step 2 didn't finish.
- `OPENROUTER_API_KEY is not set` / "not an OpenRouter model name": check `.env` (no quotes, no spaces) and the `vendor/model` form.
- 401 or 403 from a provider: the key is wrong or has no credit.
- Answers escalate too often: that's the guardrail working. Look at the decision trace in the output to see why.
