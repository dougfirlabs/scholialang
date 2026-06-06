"""Scholia atom catalog — v0.5 closed set (32 atom kinds).

This module is the canonical set of types for the Scholia notation in
the standalone ``scholialang`` package. It is pure: no I/O, no network,
no non-stdlib dependencies. Atoms are plain ``dataclass`` shells; the
parser/serializer/validator (PRDs 02-04) layer on top.

Closed-set lineage:
- v0.2 froze 27 atoms (the §3 catalog in ``NOTATION_REFERENCE.md``).
- v0.3 added Confidence, EventRef, Budget, Cost (28..31, ratified via
  the operator-driven ratification cycle).
- v0.3.1 added Edge, Effect, Ref, Meta as schema-reserved primitive
  hooks (28..31 — replaced the v0.3 set in the new layout; the v0.5
  catalog inherits the v0.4 result: 31 atoms).
- v0.5 adds **Concluding** (epistemic close), bringing the lock to 32.

Spec source: ``docs/notation/NOTATION_REFERENCE.md`` for the §3 catalog
and ``docs/papers/scholia-v2/concluding-atom-spec-2026-06-04.md`` for
the Concluding definition. Any divergence here is a bug — update the
docs first.
"""
from __future__ import annotations

import hashlib
import json
import re
import warnings
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any, ClassVar, Optional


# ── §4 — logical operators ────────────────────────────────────────────

class Operator(str, Enum):
    """The 11 inline operators from NOTATION_REFERENCE.md §4."""

    AND = "AND"
    OR = "OR"
    XOR = "XOR"
    NOT = "NOT"
    IMPLIES = "IMPLIES"
    REFER = "REFER"
    FORALL = "FORALL"
    EXISTS = "EXISTS"
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    EQUALS = "EQUALS"


OPERATORS: tuple[str, ...] = tuple(op.value for op in Operator)
CANONICAL_OPERATORS: frozenset[str] = frozenset(OPERATORS)


# ── §5 — data primitives (markers) ────────────────────────────────────

PRIMITIVES: tuple[str, ...] = ("LIST", "SET", "MAP", "STRING", "NUMBER", "BOOL")


# ── §3 — the atom catalog ─────────────────────────────────────────────

@dataclass
class Atom:
    """Base Scholia atom — per NOTATION_REFERENCE.md §3.

    v0.6 adds ``canonical_id`` — a content-addressable SHA-256 hash of
    the atom's structural identity ({kind, content, attrs}). The
    parser populates it lazily; ``Atom.__post_init__`` does not.
    """

    id: Optional[str] = None
    content: str = ""
    children: list["Atom"] = field(default_factory=list)
    operators: list[str] = field(default_factory=list)
    canonical_id: Optional[str] = None
    kind: ClassVar[str] = "Atom"


# ── 3a — reasoning atoms ─────────────────────────────────────────────

@dataclass
class Thinking(Atom):
    kind: ClassVar[str] = "Thinking"


@dataclass
class Observation(Atom):
    timestamp: Optional[str] = None
    location: Optional[str] = None
    confidence: Optional[str] = None
    kind: ClassVar[str] = "Observation"


@dataclass
class Action(Atom):
    timestamp: Optional[str] = None
    kind: ClassVar[str] = "Action"


# ── 3b — evidence atoms ──────────────────────────────────────────────

@dataclass
class Hypothesis(Atom):
    kind: ClassVar[str] = "Hypothesis"


@dataclass
class Evidence(Atom):
    """§3b — observation bearing on one or more hypotheses.

    ``for_ref`` is spelled with a trailing underscore to avoid Python's
    reserved ``for``; serializers emit/read the wire attribute as ``for``.
    """

    for_ref: Optional[str] = None
    polarity: Optional[str] = None
    kind: ClassVar[str] = "Evidence"


_FOR_GOAL_DEPRECATION_MSG = (
    "Finding.for_goal is deprecated in Scholia v0.5; use for_hyp instead. "
    "A Finding evaluates a Hypothesis, not a Goal — the rename clarifies "
    "the semantic. for_goal is preserved on read for v0.4 back-compat and "
    "will be removed in v0.6."
)


@dataclass
class Finding(Atom):
    """§3b — a conclusion drawn from available evidence.

    v0.5 migration: ``for_hyp`` is the canonical reference attribute on
    Finding (a Finding evaluates a Hypothesis). ``for_goal`` stays as a
    deprecated alias in v0.5 — both are accepted on read, but setting
    ``for_goal`` emits a ``DeprecationWarning``. Use ``Finding.from_legacy``
    to migrate a v0.4-shaped attribute dict onto a v0.5 Finding.
    """

    for_hyp: Optional[str] = None
    for_goal: Optional[str] = None
    status: Optional[str] = None
    kind: ClassVar[str] = "Finding"

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "for_goal" and value is not None:
            if not object.__getattribute__(self, "__dict__").get(
                "_warned_for_goal", False
            ):
                warnings.warn(
                    _FOR_GOAL_DEPRECATION_MSG,
                    DeprecationWarning,
                    stacklevel=2,
                )
                object.__setattr__(self, "_warned_for_goal", True)
        object.__setattr__(self, name, value)

    @classmethod
    def from_legacy(cls, data: dict[str, Any]) -> "Finding":
        """Build a v0.5 Finding from a v0.4-shaped attribute dict.

        Copies ``data['for_goal']`` into ``for_hyp``. Semantic migration
        (Goal vs Hypothesis disambiguation) is a separate concern; this
        helper is structural only.
        """
        kwargs = {k: v for k, v in data.items() if k != "for_goal"}
        legacy_for_goal = data.get("for_goal")
        if legacy_for_goal is not None and "for_hyp" not in kwargs:
            kwargs["for_hyp"] = legacy_for_goal
        return cls(**kwargs)


@dataclass
class Contradiction(Atom):
    kind: ClassVar[str] = "Contradiction"


@dataclass
class Uncertainty(Atom):
    on: Optional[str] = None
    confidence: Optional[str] = None
    kind: ClassVar[str] = "Uncertainty"


@dataclass
class Retract(Atom):
    target: Optional[str] = None
    reason: Optional[str] = None
    replacement: Optional[str] = None
    kind: ClassVar[str] = "Retract"


# v0.5 — new atom: epistemic close (distinct from Deciding's action commit).

@dataclass
class Concluding(Atom):
    """§3b — chain-level epistemic close.

    A ``<Concluding>`` asserts that a reasoning chain has reached a
    closing point — the agent claims the accumulated ``Finding``,
    ``Observation``, and ``Evidence`` atoms it cites, taken together,
    resolve a stated ``Goal`` into a single closing proposition.

    Distinct from ``<Finding>`` (a granular claim about one hypothesis)
    and distinct from ``<Deciding>`` (a commitment to one action among
    enumerated alternatives). A ``<Concluding>`` makes no choice and
    prescribes no action — it states what the agent now believes is
    the case after weighing prior atoms.

    Spec: ``docs/papers/scholia-v2/concluding-atom-spec-2026-06-04.md``.
    """

    for_goal: Optional[str] = None
    confidence: Optional[float] = None
    criticality: Optional[str] = None
    kind: ClassVar[str] = "Concluding"

    def __post_init__(self) -> None:
        if self.for_goal is None:
            raise ValueError(
                "Concluding requires for_goal — the closing claim must "
                "name the Goal it resolves. See "
                "docs/papers/scholia-v2/concluding-atom-spec-2026-06-04.md §2.2."
            )


# ── 3c — control atoms ───────────────────────────────────────────────

@dataclass
class Deciding(Atom):
    options: list[str] = field(default_factory=list)
    kind: ClassVar[str] = "Deciding"


@dataclass
class Alternative(Atom):
    label: Optional[str] = None
    rejected_because: Optional[str] = None
    kind: ClassVar[str] = "Alternative"


@dataclass
class Branch(Atom):
    of: Optional[str] = None
    label: Optional[str] = None
    kind: ClassVar[str] = "Branch"


@dataclass
class Loop(Atom):
    over: Optional[str] = None
    as_var: Optional[str] = None
    kind: ClassVar[str] = "Loop"


@dataclass
class Parallel(Atom):
    kind: ClassVar[str] = "Parallel"


# ── 3d — reference atoms ─────────────────────────────────────────────

@dataclass
class Storing(Atom):
    name: Optional[str] = None
    value: Optional[str] = None
    kind: ClassVar[str] = "Storing"


@dataclass
class Print(Atom):
    kind: ClassVar[str] = "Print"


@dataclass
class Reference(Atom):
    to: Optional[str] = None
    kind: ClassVar[str] = "Reference"


@dataclass
class Implication(Atom):
    next: Optional[str] = None
    kind: ClassVar[str] = "Implication"


# ── 3e — social atoms ────────────────────────────────────────────────

@dataclass
class Handoff(Atom):
    to: Optional[str] = None
    package: Optional[str] = None
    constraints: list[str] = field(default_factory=list)
    kind: ClassVar[str] = "Handoff"


@dataclass
class Question(Atom):
    to: Optional[str] = None
    scope: Optional[str] = None
    default: Optional[str] = None
    kind: ClassVar[str] = "Question"


@dataclass
class Review(Atom):
    of: Optional[str] = None
    reviewer: Optional[str] = None
    kind: ClassVar[str] = "Review"


# ── 3f — meta atoms ──────────────────────────────────────────────────

@dataclass
class Constraint(Atom):
    scope: Optional[str] = None
    kind: ClassVar[str] = "Constraint"


@dataclass
class Goal(Atom):
    # ``criticality`` is the risk-classification tier this Goal sits on
    # (``incidental`` < ``bridge`` < ``ledger`` < ``verifier`` < ``kernel``).
    # PRD-02 ``criticality_non_decreasing`` compares it against the
    # closing Concluding's criticality. Optional — pre-v0.5 traces
    # parse identically when the attribute is absent.
    scope: Optional[str] = None
    priority: Optional[str] = None
    success_criteria: list[str] = field(default_factory=list)
    related_constraints: list[str] = field(default_factory=list)
    deadline: Optional[str] = None
    failure_modes: list[str] = field(default_factory=list)
    criticality: Optional[str] = None
    kind: ClassVar[str] = "Goal"


@dataclass
class Confidence(Atom):
    on: Optional[str] = None
    level: Optional[str] = None
    basis: Optional[str] = None
    kind: ClassVar[str] = "Confidence"


@dataclass
class EventRef(Atom):
    instance: Optional[str] = None
    run_id: Optional[str] = None
    sequence: Optional[int] = None
    for_ref: Optional[str] = None
    wall_clock: Optional[str] = None
    kind: ClassVar[str] = "EventRef"


@dataclass
class Budget(Atom):
    for_ref: Optional[str] = None
    tokens: Optional[int] = None
    actions: Optional[int] = None
    wall_clock_ms: Optional[int] = None
    kind: ClassVar[str] = "Budget"


@dataclass
class Cost(Atom):
    for_ref: Optional[str] = None
    tokens: Optional[int] = None
    wall_clock_ms: Optional[int] = None
    dollars: Optional[float] = None
    kind: ClassVar[str] = "Cost"


# v0.3.1 schema-reserved primitive hooks (carried forward to v0.5).

@dataclass
class Edge(Atom):
    edge_type: Optional[str] = None
    target: Optional[str] = None
    kind: ClassVar[str] = "Edge"


@dataclass
class Effect(Atom):
    effect_kind: Optional[str] = None
    kind: ClassVar[str] = "Effect"


@dataclass
class Ref(Atom):
    ref_type: Optional[str] = None
    target: Optional[str] = None
    kind: ClassVar[str] = "Ref"


@dataclass
class Meta(Atom):
    criticality: Optional[str] = None
    kind: ClassVar[str] = "Meta"


# ── §6 — Step container ──────────────────────────────────────────────

@dataclass
class Step:
    """§6 — top-level container for one coherent atomic advance.

    A trace is ``list[Step]``. Each Step has a unique-within-trace
    ``id``, a human-readable ``name``, and 1..N child atoms.
    """

    id: Optional[str] = None
    name: Optional[str] = None
    atoms: list[Atom] = field(default_factory=list)
    kind: ClassVar[str] = "Step"


Trace = list[Step]


# ── v0.6 content-addressable canonical IDs ──────────────────────────


class CanonicalIdMismatch(ValueError):
    """Raised when a claimed canonical_id does not match the recomputed hash.

    Carries ``atom_id`` (the local id, may be ``None``), ``claimed`` (the
    canonical_id on the wire), and ``computed`` (the hash recomputed from
    the parsed atom's structural content). The validator's
    ``canonical_id_well_formed`` rule surfaces this as a structured
    violation; strict-mode parsers may re-raise directly.
    """

    def __init__(
        self,
        atom_id: Optional[str],
        claimed: str,
        computed: str,
    ) -> None:
        self.atom_id = atom_id
        self.claimed = claimed
        self.computed = computed
        super().__init__(
            f"canonical_id mismatch on atom id={atom_id!r}: "
            f"claimed={claimed!r} computed={computed!r}"
        )


# Provenance / non-identity fields excluded from the canonical_id hash.
# Reason: timestamp / wall_clock / run_id / sequence / instance carry
# session-level metadata; two emits of the same structural atom from
# different sessions must produce the same canonical_id.
_PROVENANCE_FIELDS: frozenset[str] = frozenset({
    "timestamp",
    "wall_clock",
    "run_id",
    "sequence",
    "instance",
})

# Base-Atom bookkeeping fields — never part of the content hash.
# ``id`` is local-scope; ``canonical_id`` is the output we're computing;
# ``children`` are hashed independently (v0.7 Merkle-DAG extension would
# fold them in); ``operators`` are derived from content text.
_NON_HASH_FIELDS: frozenset[str] = frozenset({
    "id",
    "canonical_id",
    "content",
    "children",
    "operators",
    "kind",
})


def _hash_value(value: Any) -> Any:
    """Coerce a field value to a JSON-serializable shape for hashing."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_hash_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _hash_value(v) for k, v in value.items()}
    return value


def compute_canonical_id(atom: Atom) -> str:
    """Compute the content-addressable canonical_id for ``atom``.

    Hash input is the canonical-JSON serialization of
    ``{"kind", "content", "attrs"}`` where:

    - ``content`` is the body text with leading/trailing whitespace
      stripped.
    - ``attrs`` is a sorted dict of the atom's kind-specific fields,
      excluding provenance (``timestamp``, ``run_id``, ``wall_clock``,
      ``sequence``, ``instance``) and the base bookkeeping fields
      (``id``, ``canonical_id``, ``children``, ``operators``).
    - Empty / ``None`` attrs are dropped so absence and explicit-None
      hash identically.

    Output: ``"sha256:" + first 12 hex chars`` of the SHA-256 digest
    of the canonical JSON. Multihash-compatible prefix.
    """
    attrs: dict[str, Any] = {}
    for f in fields(atom):
        if f.name in _NON_HASH_FIELDS or f.name in _PROVENANCE_FIELDS:
            continue
        value = getattr(atom, f.name, None)
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        attrs[f.name] = _hash_value(value)

    payload = {
        "kind": atom.kind,
        "content": (atom.content or "").strip(),
        "attrs": attrs,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:12]}"


# ── Closed-set registry — 32 kinds locked at v0.5 ────────────────────

# Alphabetical ordering by atom kind. Concluding inserted between
# Confidence and Constraint per alphabetical position.
_ATOM_CLASSES: dict[str, type[Atom]] = {
    "Action": Action,
    "Alternative": Alternative,
    "Branch": Branch,
    "Budget": Budget,
    "Concluding": Concluding,
    "Confidence": Confidence,
    "Constraint": Constraint,
    "Contradiction": Contradiction,
    "Cost": Cost,
    "Deciding": Deciding,
    "Edge": Edge,
    "Effect": Effect,
    "EventRef": EventRef,
    "Evidence": Evidence,
    "Finding": Finding,
    "Goal": Goal,
    "Handoff": Handoff,
    "Hypothesis": Hypothesis,
    "Implication": Implication,
    "Loop": Loop,
    "Meta": Meta,
    "Observation": Observation,
    "Parallel": Parallel,
    "Print": Print,
    "Question": Question,
    "Ref": Ref,
    "Reference": Reference,
    "Retract": Retract,
    "Review": Review,
    "Storing": Storing,
    "Thinking": Thinking,
    "Uncertainty": Uncertainty,
}

ATOM_KINDS: tuple[str, ...] = tuple(_ATOM_CLASSES.keys())
KNOWN_KINDS: frozenset[str] = frozenset(_ATOM_CLASSES.keys())


# ── Criticality ordering (consumed by PRD-02 validator) ──────────────
#
# The risk classification ladder for Goal / Concluding criticality:
# kernel-class risks must never silently downgrade to bridge or
# incidental claims. The integer ranks feed the
# ``criticality_non_decreasing`` validator rule from PRD-02 — given a
# chain of atoms where a Goal declares ``criticality="kernel"``, the
# closing Concluding's criticality (or status downgrade via Finding)
# must satisfy ``CRITICALITY_RANK[closing] >= CRITICALITY_RANK[opening]``
# unless an explicit ``<Retract>`` documents the downgrade.
CRITICALITY_RANK: dict[str, int] = {
    "incidental": 0,
    "bridge": 1,
    "ledger": 2,
    "verifier": 3,
    "kernel": 4,
}


# ── Field / wire attribute helpers ───────────────────────────────────

# Kind-specific field names — serializer uses this so each atom emits
# its distinctive fields. Keeping the map next to the atoms means
# adding a new atom is a single-file change.
KIND_SPECIFIC_FIELDS: dict[str, tuple[str, ...]] = {
    "Observation": ("timestamp", "location", "confidence"),
    "Action": ("timestamp",),
    "Evidence": ("for_ref", "polarity"),
    "Finding": ("for_hyp", "for_goal", "status"),
    "Concluding": ("for_goal", "confidence", "criticality"),
    "Uncertainty": ("on", "confidence"),
    "Retract": ("target", "reason", "replacement"),
    "Deciding": ("options",),
    "Alternative": ("label", "rejected_because"),
    "Branch": ("of", "label"),
    "Loop": ("over", "as_var"),
    "Storing": ("name", "value"),
    "Reference": ("to",),
    "Implication": ("next",),
    "Handoff": ("to", "package", "constraints"),
    "Question": ("to", "scope", "default"),
    "Review": ("of", "reviewer"),
    "Constraint": ("scope",),
    "Goal": (
        "scope",
        "priority",
        "success_criteria",
        "related_constraints",
        "deadline",
        "failure_modes",
        "criticality",
    ),
    "Confidence": ("on", "level", "basis"),
    "EventRef": ("instance", "run_id", "sequence", "for_ref", "wall_clock"),
    "Budget": ("for_ref", "tokens", "actions", "wall_clock_ms"),
    "Cost": ("for_ref", "tokens", "wall_clock_ms", "dollars"),
    "Edge": ("edge_type", "target"),
    "Effect": ("effect_kind",),
    "Ref": ("ref_type", "target"),
    "Meta": ("criticality",),
}

# Wire attribute aliases — ``for`` / ``as`` / ``type`` / ``kind`` are
# Python reserved or collide with the ClassVar discriminator. Keep the
# field name internal; emit the spec-conformant attribute on the wire.
_WIRE_ATTR_ALIASES_GLOBAL: dict[str, str] = {
    "for_ref": "for",
    "as_var": "as",
}

# Per-kind wire→field aliases for v0.3.1 hook atoms.
_KIND_FIELD_ALIASES: dict[str, dict[str, str]] = {
    "Effect": {"kind": "effect_kind"},
    "Edge": {"type": "edge_type"},
    "Ref": {"type": "ref_type"},
}


def atom_class_for_kind(kind: str) -> Optional[type[Atom]]:
    """Return the dataclass for ``kind``; ``None`` when unknown."""
    return _ATOM_CLASSES.get(kind)


def _wire_to_field(kind: str, wire_attr: str) -> str:
    kind_aliases = _KIND_FIELD_ALIASES.get(kind, {})
    if wire_attr in kind_aliases:
        return kind_aliases[wire_attr]
    for field_name, wire in _WIRE_ATTR_ALIASES_GLOBAL.items():
        if wire == wire_attr:
            return field_name
    return wire_attr


def _field_to_wire(kind: str, field_name: str) -> str:
    kind_aliases = _KIND_FIELD_ALIASES.get(kind, {})
    for wire, py in kind_aliases.items():
        if py == field_name:
            return wire
    return _WIRE_ATTR_ALIASES_GLOBAL.get(field_name, field_name)


# ── Minimal XML round-trip (parse + serialize) ───────────────────────
#
# The parser / serializer here is intentionally minimal — v0.5 PRD-01
# is structural-only on the atom catalog. A richer parser with full
# operator-extraction + validation lives in PRD-02 (validator) and
# PRD-04 (canonical prompt + runner). This helper exists so the
# round-trip and fixture tests can exercise the new ``Concluding`` and
# the migrated ``Finding`` without depending on a downstream PRD.

_OPERATOR_TARGET_RE: re.Pattern[str] = re.compile(
    r"\b([A-Z][A-Z_]{1,})\s*:\s*([A-Za-z][A-Za-z0-9_]*)"
)


def _parse_int(value: str | None) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_float(value: str | None) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_INT_FIELDS: frozenset[str] = frozenset({
    "sequence",
    "tokens",
    "actions",
    "wall_clock_ms",
})
_FLOAT_FIELDS: frozenset[str] = frozenset({"dollars"})


def parse_atom(elem: ET.Element, *, strict: bool = False) -> Atom:
    """Parse a single ``<Atom>`` element into the dataclass for its kind.

    Unknown kinds raise ``ValueError``. The minimal parser populates the
    closed-set fields declared on the atom; unrecognized attributes are
    rejected to keep the closed-set contract honest at parse time.

    v0.6: after construction, the parser computes ``canonical_id`` and
    sets it on the atom. If the source XML already carried a
    ``canonical_id`` attribute, the parser verifies the claimed value
    matches the recomputed hash. In ``strict=True`` mode a mismatch
    raises :class:`CanonicalIdMismatch`; in the default lazy mode the
    parser preserves the claimed value so the validator's
    ``canonical_id_well_formed`` rule can surface the tamper as a
    structured violation.
    """
    kind = elem.tag
    atom_cls = _ATOM_CLASSES.get(kind)
    if atom_cls is None:
        raise ValueError(f"Unknown atom kind: {kind!r}")

    allowed_fields = {f.name for f in fields(atom_cls)}
    init_kwargs: dict[str, Any] = {}

    for wire_attr, value in elem.attrib.items():
        py_field = _wire_to_field(kind, wire_attr)
        if py_field not in allowed_fields:
            raise ValueError(
                f"Unknown wire attribute {wire_attr!r} on <{kind}>"
            )
        if py_field == "confidence" and kind == "Concluding":
            init_kwargs[py_field] = _parse_float(value)
        elif py_field in _INT_FIELDS:
            init_kwargs[py_field] = _parse_int(value)
        elif py_field in _FLOAT_FIELDS:
            init_kwargs[py_field] = _parse_float(value)
        else:
            init_kwargs[py_field] = value

    content_text = (elem.text or "").strip()
    child_atoms: list[Atom] = []
    for child in list(elem):
        child_atoms.append(parse_atom(child, strict=strict))
    if child_atoms:
        init_kwargs["children"] = child_atoms
    if content_text:
        init_kwargs["content"] = content_text

    operators = [
        m.group(1) for m in _OPERATOR_TARGET_RE.finditer(content_text)
    ]
    if operators:
        init_kwargs["operators"] = operators

    claimed_canonical_id = init_kwargs.pop("canonical_id", None)

    # v0.4 back-compat: a Finding with for_goal but no for_hyp is a
    # legacy trace. Route through from_legacy so the parser does NOT
    # trigger the DeprecationWarning for archival traces — only fresh
    # v0.5 code paths that programmatically construct Finding(for_goal=...)
    # should pay the deprecation cost.
    if (
        kind == "Finding"
        and "for_goal" in init_kwargs
        and "for_hyp" not in init_kwargs
    ):
        atom = Finding.from_legacy(init_kwargs)
    else:
        atom = atom_cls(**init_kwargs)

    computed = compute_canonical_id(atom)
    if claimed_canonical_id is not None and claimed_canonical_id != computed:
        if strict:
            raise CanonicalIdMismatch(
                atom_id=atom.id,
                claimed=claimed_canonical_id,
                computed=computed,
            )
        # Lazy mode: preserve the claimed (tampered) value so the
        # validator's canonical_id_well_formed rule can surface it.
        atom.canonical_id = claimed_canonical_id
    else:
        atom.canonical_id = computed

    return atom


def parse_trace(xml_string: str, *, strict: bool = False) -> Trace:
    """Parse a ``<Trace>...</Trace>`` XML string into a list of Steps.

    Top-level shape:

        <Trace>
          <Step id="step_01" name="...">
            <Goal .../>
            <Finding .../>
          </Step>
        </Trace>

    A single Step at the root (no ``<Trace>`` wrapper) is also accepted
    so callers can hand-write minimal fixtures.

    v0.6: ``strict=True`` causes a tampered ``canonical_id`` (claimed
    value does not match the recomputed hash) to raise
    :class:`CanonicalIdMismatch` at parse time. Default ``strict=False``
    preserves the claimed value so the validator can surface the
    mismatch as a structured violation.
    """
    root = ET.fromstring(xml_string)
    if root.tag == "Step":
        return [_parse_step(root, strict=strict)]
    if root.tag != "Trace":
        raise ValueError(
            f"Expected <Trace> or <Step> root, got <{root.tag}>"
        )
    return [_parse_step(step_el, strict=strict) for step_el in root.findall("Step")]


def _parse_step(elem: ET.Element, *, strict: bool = False) -> Step:
    step = Step(
        id=elem.attrib.get("id"),
        name=elem.attrib.get("name"),
        atoms=[parse_atom(child, strict=strict) for child in list(elem)],
    )
    return step


def atom_to_xml(atom: Atom) -> str:
    """Serialize a single atom to its XML representation."""
    elem = _atom_to_element(atom)
    return ET.tostring(elem, encoding="unicode")


def _atom_to_element(atom: Atom) -> ET.Element:
    elem = ET.Element(atom.kind)
    if atom.id is not None:
        elem.set("id", atom.id)
    if atom.canonical_id is not None:
        elem.set("canonical_id", atom.canonical_id)
    for fname in KIND_SPECIFIC_FIELDS.get(atom.kind, ()):
        value = getattr(atom, fname, None)
        if value is None:
            continue
        if isinstance(value, list):
            if not value:
                continue
            elem.set(_field_to_wire(atom.kind, fname), ",".join(value))
        else:
            elem.set(_field_to_wire(atom.kind, fname), str(value))
    if atom.content:
        elem.text = atom.content
    for child in atom.children:
        elem.append(_atom_to_element(child))
    return elem


def trace_to_xml(trace: Trace) -> str:
    """Serialize a Trace (list[Step]) to a ``<Trace>...</Trace>`` string."""
    root = ET.Element("Trace")
    for step in trace:
        step_el = ET.SubElement(root, "Step")
        if step.id is not None:
            step_el.set("id", step.id)
        if step.name is not None:
            step_el.set("name", step.name)
        for atom in step.atoms:
            step_el.append(_atom_to_element(atom))
    return ET.tostring(root, encoding="unicode")
