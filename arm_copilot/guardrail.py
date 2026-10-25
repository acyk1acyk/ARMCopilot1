"""Guardrails AI integration.

A custom Guardrails AI validator wraps the deterministic checks in ``grounding.py`` so that
the "every answer must carry a verifiable citation" rule is enforced by Guardrails AI, as in
the project proposal. The checking logic itself lives in ``grounding.py`` (plain Python), so
it can be tested without any network or model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .grounding import Violation, check_grounding, format_violations
from .kb import Chunk
from .schemas import AnswerCard

try:
    from guardrails import Guard, OnFailAction
    from guardrails.validator_base import FailResult, PassResult, Validator, register_validator

    GUARDRAILS_AVAILABLE = True
    _IMPORT_ERROR: Exception | None = None
except Exception as exc:  # ImportError, or an API change in a newer Guardrails AI release
    GUARDRAILS_AVAILABLE = False
    _IMPORT_ERROR = exc


if GUARDRAILS_AVAILABLE:

    @register_validator(name="arm-copilot/citation-grounded", data_type="string")
    class CitationGrounded(Validator):
        """Passes only if every statement in the answer card is backed by a quote from a retrieved clause."""

        def __init__(self, on_fail=None, **kwargs):
            super().__init__(on_fail=on_fail, **kwargs)

        def _validate(self, value, metadata):
            metadata = metadata or {}
            card = AnswerCard.model_validate_json(value)
            violations = check_grounding(card, metadata.get("chunks_by_id", {}), metadata.get("question", ""))
            if violations:
                return FailResult(error_message=format_violations(violations))
            return PassResult()


@dataclass
class GuardResult:
    passed: bool
    violations: list[Violation] = field(default_factory=list)
    engine: str = "plain-python"
    error: bool = False  # True if the guard itself failed to run (do not retry the model)


class CitationGuard:
    def __init__(self, require_guardrails: bool = True):
        if require_guardrails and not GUARDRAILS_AVAILABLE:
            raise RuntimeError(
                "Guardrails AI is required but could not be imported "
                f"({_IMPORT_ERROR!r}). Install it with `pip install guardrails-ai`, "
                "or set ARM_ALLOW_NO_GUARDRAILS=1 for offline tests only."
            )
        self._guard = None
        if GUARDRAILS_AVAILABLE:
            self._guard = Guard(name="arm-copilot-citations").use(CitationGrounded, on_fail=OnFailAction.NOOP)

    @property
    def engine(self) -> str:
        return "guardrails-ai" if self._guard is not None else "plain-python"

    def validate(self, card: AnswerCard, chunks_by_id: Mapping[str, Chunk], question: str) -> GuardResult:
        violations = check_grounding(card, chunks_by_id, question)
        if self._guard is None:
            return GuardResult(passed=not violations, violations=violations, engine="plain-python")
        try:
            outcome = self._guard.validate(
                card.model_dump_json(), metadata={"chunks_by_id": dict(chunks_by_id), "question": question}
            )
            guard_passed = bool(getattr(outcome, "validation_passed", False))
        except Exception as exc:  # fail closed, and say why
            return GuardResult(
                passed=False,
                violations=[Violation("guardrails_error", f"{type(exc).__name__}: {exc}")],
                engine="guardrails-ai",
                error=True,
            )
        # Fail closed: both Guardrails AI and the direct check must agree before an answer is released.
        return GuardResult(passed=guard_passed and not violations, violations=violations, engine="guardrails-ai")
