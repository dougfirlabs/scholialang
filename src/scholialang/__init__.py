"""Scholia — Python reference implementation, package release 0.7.2.

Implements the stable Scholia v0.6.2 grammar plus the approved additive
``fingerprint=`` contract. Package and validator versions move together;
the grammar and registry-format versions are separate compatibility axes.
The canonical spec lives at https://github.com/dougfirlabs/scholialang-spec;
``scholialang-spec-ref.txt`` pins the exact conformance revision.

The language supports content-addressable ``canonical_id``s (a SHA-256 over each
atom's structural identity), a DAG-backed :mod:`~scholialang.registry`,
and the lazy canonical :mod:`~scholialang.prelude`. The atom catalog retains
32 kinds. Optional ``Concluding.status`` records goal outcomes; explicitly
linked Action results can close across Steps. ``Observation.fingerprint``
adds a source-span hash whose structure, but not source content, is validated.
Release 0.7.2 hardens forbidden-action matching in ``constraint_respected``.

The package contains the language-level modules:

* :mod:`scholialang.atoms` — 32 atom dataclasses + 11 operators +
  6 primitive type aliases + the v0.6 ``compute_canonical_id`` hasher.
* :mod:`scholialang.parser` — XML-ish text → AST (stamps canonical_ids).
* :mod:`scholialang.serializer` — AST ↔ JSON ↔ YAML roundtrip.
* :mod:`scholialang.validator` — grammar, reference, closure, constraint,
  canonical-id, and fingerprint validation.
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

__version__ = "0.7.2"

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
    is_valid_fingerprint,
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
    RULE_FINGERPRINT_WELL_FORMED,
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
    "is_valid_fingerprint",
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
    "RULE_FINGERPRINT_WELL_FORMED",
    "RULE_NAMES",
    # v0.6 registry + prelude
    "Registry",
    "build_canonical_prelude",
    "CORE_PRELUDE_MODES",
    "EXPERIMENTAL_PRELUDE_MODES",
]
