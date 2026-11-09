# ARM Copilot panel (November interface)

A simple panel: choose a client and a product, see fact cards and a checklist, and ask questions in chat.
All clients and knowledge-base content are fictional.

## Run it

```
pip install streamlit
streamlit run app.py
```
It opens in your browser. The chat needs the same `.env` keys as the command line tool. The facts and
checklist work without any keys.

## What you see

- **Sidebar:** client, product, currency, value date, amount, and today's conditions (half-day, typhoon).
- **Fact cards:** cutoff time, prices, rates, authentication level, risk profile status and approvals. Each card names its clause.
  Values are read from the knowledge base by rules, not by a model.
- **Checklist:** the steps for the product, grouped by before / on the call / after. Tick a step to strike it through.
  "Why this step" shows the clause and the quote. Steps that only apply in some cases (for example a notional above USD 2 million) appear automatically.
- **Client background:** the fictional client's background summary and investor profile.
- **Ask a question:** the chat assistant, with citations and escalation. It can include the selected tier, product and currency in your question.

Ticks are not saved and are not a compliance record.

## Where things live

- `app.py`: the screen
- `arm_copilot/panel/facts.py`: fact cards
- `arm_copilot/panel/checklists.py` and `arm_copilot/panel/data/checklists.json`: checklists
- `arm_copilot/panel/data/mock_clients.json`: fictional clients
- `tests/test_panel.py`: checks that every checklist quote is written word for word in its clause
