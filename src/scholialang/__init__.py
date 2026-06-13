"""Scholia — structured reasoning notation (v0.6).

See ``docs/notation/NOTATION_REFERENCE.md`` for the canonical spec.

v0.6 adds content-addressable ``canonical_id``s (a SHA-256 over each
atom's structural identity), a DAG-backed :mod:`~scholialang.registry`,
and the lazy canonical :mod:`~scholialang.prelude` — while staying
back-compatible with v0.5 traces. The atom catalog is unchanged (32
kinds); only the base ``Atom`` grows a ``canonical_id`` and the validator
grows the ``canonical_id_well_formed`` rule.

The package contains the language-level modules:

* :mod:`scholialang.atoms` — 32 atom dataclasses + 11 operators +
  6 primitive type aliases + the v0.6 ``compute_canonical_id`` hasher.
* :mod:`scholialang.parser` — XML-ish text → AST (stamps canonical_ids).
* :mod:`scholialang.serializer` — AST ↔ JSON ↔ YAML roundtrip.
* :mod:`scholialang.validator` — validity rules from §9 + v0.6 rules.
* :mod:`scholialang.registry` — DAG-backed canonical_id-keyed store.
* :mod:`scholialang.prelude` — v0.6 canonical-prelude renderer with the 3
  core modes (``hash_only`` / ``hash_list`` (default) / ``inline``); two
  experimental recovery arms are opt-in only (not v0.6 core).
* :mod:`scholialang.renderer` — AST → Markdown for humans.
* :mod:`scholialang.stable_ids` — deterministic atom IDs.
* :mod:`scholialang.criticality` — criticality metadata helpers.
* :mod:`scholialang.effects` — effect metadata helpers.
* :mod:`scholialang.test_ownership` — test-ownership metadata helpers.
"""
from __future__ import annotations

__version__ = "0.6.1"

from scholialang.atoms import (
    ATOM_KINDS,
    CANONICAL_OPERATORS,
    CRITICALITY_RANK,
    KNOWN_KINDS,
    OPERATORS,
    PRIMITIVES,
    SCHOLIA_VALIDATOR_VERSION,
    Action,
    Alternative,
    Atom,
    Branch,
    Budget,
    CanonicalIdMismatch,
    Confidence,
    Concluding,
    Constraint,
    Contradiction,
    Cost,
    Deciding,
    Edge,
    Effect,
    Evidence,
    EventRef,
    Finding,
    Goal,
    Handoff,
    Hypothesis,
    Implication,
    Loop,
    Meta,
    Observation,
    Operator,
    Parallel,
    Print,
    Question,
    Ref,
    Reference,
    Retract,
    Review,
    Step,
    Storing,
    Thinking,
    Uncertainty,
    atom_to_xml,
    compute_canonical_id,
)
from scholialang.parser import parse, parse_atom
from scholialang.prelude import (
    CORE_PRELUDE_MODES,
    EXPERIMENTAL_PRELUDE_MODES,
    build_canonical_prelude,
)
from scholialang.registry import Registry
from scholialang.validator import (
    RULE_CANONICAL_ID_WELL_FORMED,
    RULE_NAMES,
    ValidationError,
    ValidationResult,
    ValidationWarning,
    resolve_refer,
    validate,
)

__all__ = [
    "__version__",
    "ATOM_KINDS",
    "CANONICAL_OPERATORS",
    "CRITICALITY_RANK",
    "KNOWN_KINDS",
    "OPERATORS",
    "PRIMITIVES",
    "SCHOLIA_VALIDATOR_VERSION",
    "Action",
    "Alternative",
    "Atom",
    "Branch",
    "Budget",
    "CanonicalIdMismatch",
    "Confidence",
    "Concluding",
    "Constraint",
    "Contradiction",
    "Cost",
    "Deciding",
    "Edge",
    "Effect",
    "Evidence",
    "EventRef",
    "Finding",
    "Goal",
    "Handoff",
    "Hypothesis",
    "Implication",
    "Loop",
    "Meta",
    "Observation",
    "Operator",
    "Parallel",
    "Print",
    "Question",
    "Ref",
    "Reference",
    "Retract",
    "Review",
    "Step",
    "Storing",
    "Thinking",
    "Uncertainty",
    "atom_to_xml",
    "compute_canonical_id",
    # parser
    "parse",
    "parse_atom",
    # validator
    "validate",
    "resolve_refer",
    "ValidationError",
    "ValidationWarning",
    "ValidationResult",
    "RULE_CANONICAL_ID_WELL_FORMED",
    "RULE_NAMES",
    # v0.6 registry + prelude
    "Registry",
    "build_canonical_prelude",
    "CORE_PRELUDE_MODES",
    "EXPERIMENTAL_PRELUDE_MODES",
]
