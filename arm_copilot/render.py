"""Plain-text rendering of an agent response (used by the command line tool)."""

from __future__ import annotations

from .schemas import FinalResponse


def render_response(resp: FinalResponse) -> str:
    lines: list[str] = []
    if resp.status != "answered" or resp.card is None:
        lines.append(f"[{resp.status.upper()}] {resp.message}")
    else:
        card = resp.card
        lines.append(card.headline or "(no headline)")
        for kv in card.key_values:
            lines.append(f"  * {kv.label}: {kv.value}")
        for p in card.points:
            cites = ", ".join(c.chunk_id for c in p.citations)
            lines.append(f"  - {p.text}  [{cites}]")
        for e in card.exceptions:
            lines.append(f"  ! {e}")
        if card.requires_signoff:
            lines.append(f"  ! Manager sign-off needed: {card.signoff_by or 'see the cited clause'}")
        if resp.message:
            lines.append(f"  ? {resp.message}")
    if resp.sources:
        lines.append("Sources:" if resp.status == "answered" else "Clauses to read:")
        for s in resp.sources:
            lines.append(f"  {s.chunk_id}  {s.doc_title} v{s.version} (effective {s.effective_date}) - {s.clause_title}")
    return "\n".join(lines)
