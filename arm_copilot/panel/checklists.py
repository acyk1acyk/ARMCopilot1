"""Checklists per product, loaded from data/checklists.json.

Each step cites a clause and a quote. tests/test_panel.py verifies the quotes against the knowledge base,
so a step can never point at text that is not there.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .facts import ScenarioInputs

DATA_DIR = Path(__file__).parent / "data"
CONDITIONS = {"always", "notional_gt_2m", "notional_gt_500k", "notional_gt_100k", "risk_profile_overdue"}


@dataclass(frozen=True)
class Why:
    chunk_id: str
    quote: str


@dataclass(frozen=True)
class Step:
    step_id: str
    text: str
    when: str
    why: tuple[Why, ...]


@dataclass(frozen=True)
class Phase:
    phase_id: str
    title: str
    steps: tuple[Step, ...]


def _step(d: dict[str, Any]) -> Step:
    return Step(d["id"], d["text"], d.get("when", "always"), tuple(Why(w["chunk_id"], w["quote"]) for w in d["why"]))


def load_raw(path: Path | None = None) -> dict[str, Any]:
    return json.loads(Path(path or DATA_DIR / "checklists.json").read_text(encoding="utf-8"))


def all_phases(product: str, raw: dict[str, Any] | None = None) -> list[Phase]:
    """Every phase and step for a product, with shared blocks expanded (conditions not applied)."""
    raw = raw or load_raw()
    shared = {k: [_step(s) for s in v] for k, v in raw["shared"].items()}
    phases = []
    for ph in raw["products"][product]["phases"]:
        steps: list[Step] = []
        for item in ph["steps"]:
            if "include" in item:
                steps.extend(shared[item["include"]])
            else:
                steps.append(_step(item))
        phases.append(Phase(ph["id"], ph["title"], tuple(steps)))
    return phases


def condition_met(when: str, inputs: ScenarioInputs, risk_profile_overdue: bool) -> bool:
    amount = inputs.amount_usd or 0
    return {
        "always": True,
        "notional_gt_2m": amount > 2_000_000,
        "notional_gt_500k": amount > 500_000,
        "notional_gt_100k": amount >= 100_000,
        "risk_profile_overdue": risk_profile_overdue,
    }[when]


def checklist_for(product: str, inputs: ScenarioInputs, risk_profile_overdue: bool, raw: dict[str, Any] | None = None) -> list[Phase]:
    """The phases and steps that apply to this scenario. Steps whose condition is not met are left out."""
    out = []
    for ph in all_phases(product, raw):
        steps = tuple(s for s in ph.steps if condition_met(s.when, inputs, risk_profile_overdue))
        if steps:
            out.append(Phase(ph.phase_id, ph.title, steps))
    return out
