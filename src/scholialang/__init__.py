"""Scholia — structured reasoning notation (grammar 0.7.0 candidate).

See ``docs/notation/NOTATION_REFERENCE.md`` for the canonical spec.

The 0.7.3 candidate adds the three PROPOSED additive semantic kinds —
``Map`` (typed mapping value), ``Event`` (recorded occurrence), and
``Task`` (declarative work obligation) — growing the closed catalog
from 32 to 35 under the distinct grammar revision 0.7.0 (the package
and grammar version on separate axes). Every valid legacy trace keeps
its meaning: the 32-kind projection is preserved as
``LEGACY_ATOM_KINDS`` and ``validate(..., profile="0.6.2")`` rejects
the new kinds with a structured unsupported-version diagnostic instead
of silently rewriting them. Constructing, parsing, validating, hashing,
or serializing a semantic atom NEVER executes work or grants authority.

v0.6 added content-addressable ``canonical_id``s (a SHA-256 over each
atom's structural identity), a DAG-backed :mod:`~scholialang.registry`,
and the lazy canonical :mod:`~scholialang.prelude` — while staying
back-compatible with v0.5 traces.

The package contains the language-level modules:

* :mod:`scholialang.atoms` — 35 atom dataclasses + 11 operators +
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

__version__ = "0.7.3"

from scholialang.atoms import (
    ATOM_KINDS,
    CANONICAL_OPERATORS,
    CRITICALITY_RANK,
    GRAMMAR_PROFILES,
    KNOWN_KINDS,
    LEGACY_ATOM_KINDS,
    LEGACY_GRAMMAR_VERSION,
    LEGACY_KNOWN_KINDS,
    MAP_VALUE_TYPES,
    OPERATORS,
    PRIMITIVES,
    SCHOLIA_GRAMMAR_VERSION,
    SCHOLIA_VALIDATOR_VERSION,
    SEMANTIC_ATOM_KINDS,
    SEMANTIC_KINDS,
    TASK_EVIDENCE_KINDS,
    TASK_STATUSES,
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
    Event,
    Evidence,
    EventRef,
    Finding,
    Goal,
    Handoff,
    Hypothesis,
    Implication,
    Loop,
    Map,
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
    SemanticShapeError,
    Step,
    Storing,
    Task,
    Thinking,
    Uncertainty,
    atom_to_xml,
    compute_canonical_id,
    is_valid_fingerprint,
    normalize_semantic_atom,
)
from scholialang.parser import parse, parse_atom
from scholialang.prelude import (
    CORE_PRELUDE_MODES,
    EXPERIMENTAL_PRELUDE_MODES,
    build_canonical_prelude,
)
from scholialang.registry import CanonicalCollisionError, Registry
from scholialang.validator import (
    RULE_CANONICAL_ID_WELL_FORMED,
    RULE_FINGERPRINT_WELL_FORMED,
    RULE_GRAMMAR_PROFILE_UNSUPPORTED,
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
    "GRAMMAR_PROFILES",
    "KNOWN_KINDS",
    "LEGACY_ATOM_KINDS",
    "LEGACY_GRAMMAR_VERSION",
    "LEGACY_KNOWN_KINDS",
    "MAP_VALUE_TYPES",
    "OPERATORS",
    "PRIMITIVES",
    "SCHOLIA_GRAMMAR_VERSION",
    "SCHOLIA_VALIDATOR_VERSION",
    "SEMANTIC_ATOM_KINDS",
    "SEMANTIC_KINDS",
    "TASK_EVIDENCE_KINDS",
    "TASK_STATUSES",
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
    "Event",
    "Evidence",
    "EventRef",
    "Finding",
    "Goal",
    "Handoff",
    "Hypothesis",
    "Implication",
    "Loop",
    "Map",
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
    "SemanticShapeError",
    "Step",
    "Storing",
    "Task",
    "Thinking",
    "Uncertainty",
    "atom_to_xml",
    "compute_canonical_id",
    "is_valid_fingerprint",
    "normalize_semantic_atom",
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
    "RULE_GRAMMAR_PROFILE_UNSUPPORTED",
    "RULE_NAMES",
    # v0.6 registry + prelude
    "Registry",
    "CanonicalCollisionError",
    "build_canonical_prelude",
    "CORE_PRELUDE_MODES",
    "EXPERIMENTAL_PRELUDE_MODES",
]
