"""Scholia — structured reasoning notation (v0.5).

See ``docs/notation/NOTATION_REFERENCE.md`` for the canonical spec.

The package contains the language-level modules:

* :mod:`scholialang.atoms` — 32 atom dataclasses + 11 operators +
  6 primitive type aliases matching the reference doc.
* :mod:`scholialang.parser` — XML-ish text → AST.
* :mod:`scholialang.serializer` — AST ↔ JSON ↔ YAML roundtrip.
* :mod:`scholialang.validator` — validity rules from §9.
* :mod:`scholialang.renderer` — AST → Markdown for humans.
* :mod:`scholialang.stable_ids` — deterministic atom IDs.
* :mod:`scholialang.criticality` — criticality metadata helpers.
* :mod:`scholialang.effects` — effect metadata helpers.
* :mod:`scholialang.test_ownership` — test-ownership metadata helpers.
"""
from __future__ import annotations

from scholialang.atoms import (
    ATOM_KINDS,
    OPERATORS,
    PRIMITIVES,
    Action,
    Alternative,
    Atom,
    Branch,
    Budget,
    Confidence,
    Concluding,
    Constraint,
    Contradiction,
    Cost,
    Deciding,
    Evidence,
    EventRef,
    Finding,
    Goal,
    Handoff,
    Hypothesis,
    Implication,
    Loop,
    Observation,
    Operator,
    Parallel,
    Print,
    Question,
    Reference,
    Retract,
    Review,
    Step,
    Storing,
    Thinking,
    Uncertainty,
)

__all__ = [
    "ATOM_KINDS",
    "OPERATORS",
    "PRIMITIVES",
    "Action",
    "Alternative",
    "Atom",
    "Branch",
    "Budget",
    "Confidence",
    "Concluding",
    "Constraint",
    "Contradiction",
    "Cost",
    "Deciding",
    "Evidence",
    "EventRef",
    "Finding",
    "Goal",
    "Handoff",
    "Hypothesis",
    "Implication",
    "Loop",
    "Observation",
    "Operator",
    "Parallel",
    "Print",
    "Question",
    "Reference",
    "Retract",
    "Review",
    "Step",
    "Storing",
    "Thinking",
    "Uncertainty",
]
