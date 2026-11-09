"""Fictional mock clients for the panel. No real client data is ever stored here."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent / "data"


@dataclass(frozen=True)
class Client:
    client_id: str
    display_name: str
    tier: str
    risk_profile: str
    risk_profile_reviewed: date
    professional_investor: bool
    additional_markup: dict[str, str] = field(default_factory=dict)
    authorised_persons: tuple[str, ...] = ()
    background: dict[str, str] = field(default_factory=dict)
    investor_profile: dict[str, str] = field(default_factory=dict)


def load_clients(path: Path | None = None) -> list[Client]:
    raw: dict[str, Any] = json.loads(Path(path or DATA_DIR / "mock_clients.json").read_text(encoding="utf-8"))
    out = []
    for c in raw["clients"]:
        out.append(
            Client(
                client_id=c["client_id"],
                display_name=c["display_name"],
                tier=c["tier"],
                risk_profile=c["risk_profile"],
                risk_profile_reviewed=date.fromisoformat(c["risk_profile_reviewed"]),
                professional_investor=bool(c["professional_investor"]),
                additional_markup=dict(c.get("additional_markup", {})),
                authorised_persons=tuple(c.get("authorised_persons", [])),
                background=dict(c.get("background", {})),
                investor_profile=dict(c.get("investor_profile", {})),
            )
        )
    return out


def risk_profile_expiry(reviewed: date) -> date:
    """The last day on which a review still counts as 'within the last 12 months'."""
    try:
        return reviewed.replace(year=reviewed.year + 1)
    except ValueError:  # 29 February
        return reviewed.replace(year=reviewed.year + 1, day=28)


def risk_profile_valid(reviewed: date, today: date) -> bool:
    return today <= risk_profile_expiry(reviewed)


def days_left(reviewed: date, today: date) -> int:
    return (risk_profile_expiry(reviewed) - today).days
