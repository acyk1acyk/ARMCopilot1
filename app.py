"""ARM Copilot panel: pick a client and product, see the facts and the checklist, and ask questions in chat.

Run:  streamlit run app.py

All clients and knowledge-base content are FICTIONAL. Ticking a step is a visual aid only: it is not saved
and it is not a compliance record.
"""

from __future__ import annotations

import html
from datetime import date

import streamlit as st

from arm_copilot.config import Settings
from arm_copilot.kb import load_chunks
from arm_copilot.panel import checklists as cl
from arm_copilot.panel.clients import load_clients, risk_profile_valid
from arm_copilot.panel.facts import CURRENCIES, PRODUCTS, VALUE_DATES, ScenarioInputs, build_facts

st.set_page_config(page_title="ARM Copilot", page_icon="🗂️", layout="wide")

TONE_COLOURS = {
    "info": ("#2a3566", "#c9d6ff"),
    "ok": ("#14532d", "#bbf7d0"),
    "warning": ("#713f12", "#fde68a"),
    "blocked": ("#7f1d1d", "#fecaca"),
}

st.markdown(
    """
<style>
.fact-card {border-radius: 12px; padding: 14px 16px; margin-bottom: 12px; min-height: 108px;}
.fact-title {font-size: 0.8rem; opacity: 0.85; margin-bottom: 4px;}
.fact-value {font-size: 1.25rem; font-weight: 700; line-height: 1.25;}
.fact-detail {font-size: 0.78rem; opacity: 0.85; margin-top: 6px;}
.fact-src {font-size: 0.7rem; opacity: 0.7; margin-top: 4px;}
.banner {border-radius: 10px; padding: 10px 14px; background: #fff7ed; color: #7c2d12; font-size: 0.85rem; margin-bottom: 12px;}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data
def get_chunks():
    return {c.chunk_id: c for c in load_chunks(Settings().kb_dir)}


@st.cache_data
def get_clients():
    return load_clients()


@st.cache_resource
def get_agent():
    from arm_copilot.factory import create_agent  # imported here so the panel opens even if keys are missing

    return create_agent(Settings.from_env())


def fact_card(f) -> str:
    bg, fg = TONE_COLOURS.get(f.tone, TONE_COLOURS["info"])
    srcs = ", ".join(html.escape(s) for s in f.sources)
    detail = f'<div class="fact-detail">{html.escape(f.detail)}</div>' if f.detail else ""
    return (
        f'<div class="fact-card" style="background:{bg};color:{fg}">'
        f'<div class="fact-title">{html.escape(f.title)}</div>'
        f'<div class="fact-value">{html.escape(f.value)}</div>{detail}'
        f'<div class="fact-src">Source: {srcs}</div></div>'
    )


def show_response(resp) -> None:
    """Render an agent response (an AnswerCard, or an escalation message) with its citations."""
    if resp.status != "answered" or resp.card is None:
        label = "Out of scope" if resp.status == "out_of_scope" else "Escalated: please check with your Desk Head"
        st.warning(f"**{label}**  \n{resp.message}")
    else:
        card = resp.card
        if card.confidence == "low" or "low_confidence" in resp.flags:
            st.warning("Low confidence: some detail may be missing from the question. Check the cited clauses or ask your Desk Head.")
        st.markdown(f"**{card.headline}**")
        for kv in card.key_values:
            st.markdown(f"- **{kv.label}:** {kv.value}")
        for p in card.points:
            cites = ", ".join(f"`{c.chunk_id}`" for c in p.citations)
            st.markdown(p.text)
            st.caption(f"Source: {cites}")
        for e in card.exceptions:
            st.markdown(f"⚠️ {e}")
        if card.requires_signoff:
            st.info(f"Sign-off needed: {card.signoff_by or 'see the cited clause'}")
        if resp.message:
            st.caption(resp.message)
    if resp.sources:
        with st.expander("Clauses used" if resp.status == "answered" else "Clauses to read"):
            for s in resp.sources:
                st.markdown(f"`{s.chunk_id}` {s.doc_title} v{s.version} (effective {s.effective_date}): {s.clause_title}")
    if resp.trace:
        with st.expander("Decision trace (audit)"):
            st.code("\n".join(resp.trace))


# ------------------------------------------------------------------------------------------ sidebar

chunks = get_chunks()
clients = {c.client_id: c for c in get_clients()}

with st.sidebar:
    st.header("Select")
    client_id = st.selectbox("Client", list(clients), format_func=lambda k: f"{clients[k].display_name}")
    product = st.selectbox("Product", list(PRODUCTS), format_func=lambda k: PRODUCTS[k], index=8)
    needs_ccy = product in ("time_deposit", "loan", "overdraft")
    currency = st.selectbox("Currency", CURRENCIES, index=1, disabled=not needs_ccy)
    value_date = st.selectbox("Value date", VALUE_DATES, disabled=product not in ("time_deposit", "loan"))
    amount = st.number_input("Amount or notional (USD equivalent)", min_value=0, value=0, step=100_000,
                             help="Used for amount bands, approvals and payment checks. Leave 0 if not known yet.")
    st.caption("Today's conditions")
    half_day = st.checkbox("Half-day trading day", disabled=product not in ("time_deposit", "loan"))
    severe = st.checkbox("Typhoon No. 8 / Black Rainstorm at 09:00 HKT", disabled=product not in ("time_deposit", "loan"))
    st.divider()
    st.caption("Fictional prototype. No real client or bank data. Ticks are not saved and are not a compliance record.")

client = clients[client_id]
inputs = ScenarioInputs(
    client=client, product=product, currency=currency, value_date=value_date,
    amount_usd=float(amount) if amount else None, half_day=half_day, severe_weather=severe, today=date.today(),
)
overdue = not risk_profile_valid(client.risk_profile_reviewed, inputs.today)

# ------------------------------------------------------------------------------------------ main

st.title("ARM Copilot")
st.markdown('<div class="banner">Fictional prototype for testing. Every fact and step below comes from the fictional knowledge base and shows its source clause.</div>', unsafe_allow_html=True)

st.subheader(f"{client.display_name} · Tier {client.tier} · {PRODUCTS[product]}")

tab_facts, tab_client = st.tabs(["Facts and checklist", "Client background"])

with tab_facts:
    facts = build_facts(chunks, inputs)
    cols = st.columns(3)
    for n, f in enumerate(facts):
        with cols[n % 3]:
            st.markdown(fact_card(f), unsafe_allow_html=True)

    phases = cl.checklist_for(product, inputs, overdue)
    total = sum(len(p.steps) for p in phases)
    done = 0
    state_key = lambda step_id: f"chk::{client_id}::{product}::{step_id}"
    for ph in phases:
        for s in ph.steps:
            done += 1 if st.session_state.get(state_key(s.step_id), False) else 0
    st.markdown("### Checklist")
    st.progress(done / total if total else 0.0, text=f"{done} of {total} steps ticked")
    for ph in phases:
        st.markdown(f"**{ph.title}**")
        for s in ph.steps:
            key = state_key(s.step_id)
            ticked = st.session_state.get(key, False)
            box, text = st.columns([0.05, 0.95])
            box.checkbox(f"Done: {s.step_id}", key=key, label_visibility="collapsed")
            text.markdown(f"~~{s.text}~~" if ticked else s.text)
            with text.expander("Why this step", expanded=False):
                for w in s.why:
                    st.markdown(f"`{w.chunk_id}`: “{w.quote}”")

    def clear_ticks(keys):
        for k in keys:
            st.session_state[k] = False

    st.button("Clear ticks for this client and product", on_click=clear_ticks,
              args=([state_key(s.step_id) for ph in phases for s in ph.steps],))

with tab_client:
    c = client
    ok = risk_profile_valid(c.risk_profile_reviewed, inputs.today)
    st.markdown(f"**Tier:** {c.tier}  \n**Risk profile:** {c.risk_profile} (reviewed {c.risk_profile_reviewed.isoformat()}, {'valid' if ok else 'OVERDUE'})  \n"
                f"**Professional Investor:** {'Yes' if c.professional_investor else 'No'}")
    st.markdown("##### Background summary")
    st.markdown(
        f"- **Source of assets:** {c.background.get('source_of_assets', '')}\n"
        f"- **Business or corporate activity:** {c.background.get('business_activity', '')}\n"
        f"- **Family situation:** {c.background.get('family_situation', '')}\n"
        f"- **Notable past transactions:** {c.background.get('notable_transactions', '')}"
    )
    st.markdown("##### Investor profile")
    st.markdown(
        f"- **Knowledge and experience:** {c.investor_profile.get('knowledge_and_experience', '')}\n"
        f"- **Investment objectives:** {c.investor_profile.get('objectives', '')}"
    )
    st.markdown("##### Other")
    st.markdown(
        f"- **Additional markup:** {', '.join(f'{k}: {v}' for k, v in c.additional_markup.items()) or 'None'}\n"
        f"- **Authorised persons:** {', '.join(c.authorised_persons) or 'None'}"
    )
    st.caption("Use client information only to serve the client. Do not discuss it with another client.")

st.divider()
st.subheader("Ask a question")
if True:
    st.caption("Questions are answered from the knowledge base only, with a citation for every point. If it cannot be backed by a quote, you get an escalation, not a guess.")
    include_ctx = st.checkbox("Include the selected client tier, product and currency in my question", value=True)
    if "messages" not in st.session_state:
        st.session_state.messages = []
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            if m["role"] == "user":
                st.markdown(m["content"])
            else:
                show_response(m["response"])
    q = st.chat_input("Ask about cutoff times, pricing, overdraft rates, authentication, payments or pre-trade steps")
    if q:
        st.session_state.messages.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        question = q
        if include_ctx:
            ctx = f"(Client tier {client.tier}; product: {PRODUCTS[product]}"
            ctx += f"; currency {currency})" if needs_ccy else ")"
            question = f"{q} {ctx}"
        with st.chat_message("assistant"):
            try:
                with st.spinner("Checking the knowledge base..."):
                    resp = get_agent().ask(question)
                show_response(resp)
                st.session_state.messages.append({"role": "assistant", "response": resp})
            except Exception as exc:  # show a friendly message, never keys or tracebacks
                st.error("Sorry, the assistant could not answer just now. Check your keys and connection in `.env`, then try again.")
                st.caption(f"Technical note: {type(exc).__name__}")
