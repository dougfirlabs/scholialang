"""Scholia v0.5 validator — Concluding semantics + criticality enforcement.

Six rules layered on top of the structural catalog from
:mod:`scholialang.atoms`:

Hard-fail (severity ``"error"``):
- ``for_goal_resolves`` — every ``<Concluding>.for_goal`` resolves to a
  declared ``<Goal>`` in the same trace.
- ``refer_at_least_one`` — every ``<Concluding>`` body contains at least
  one ``REFER:`` token pointing at a ``<Finding>``, ``<Observation>``,
  or ``<Evidence>`` atom in the same trace.
- ``criticality_non_decreasing`` — a ``<Concluding>``'s effective
  criticality (declared, or max of cited Findings/Observations) must
  be ``>=`` the criticality of the Goal it closes. An explicit
  ``<Retract target="goal_id">`` authorizes a downgrade.

Warning (severity ``"warning"``):
- ``no_action_in_concluding`` — body must not contain modal verbs that
  signal action commitment (``should``, ``will``, ``recommend``,
  ``choose``, ``propose``). Heuristic — false positives possible.
- ``single_active_concluding_per_goal`` — at most one active
  ``<Concluding>`` per ``<Goal>``. A Concluding targeted by ``<Retract>``
  is no longer active.
- ``min_confidence_ceiling`` — declared confidence must not exceed the
  minimum confidence of cited Findings/Evidence atoms.

Backwards compatibility: a trace with **no** ``<Concluding>`` atoms
bypasses all six rules — pre-v0.5 traces validate as if this module
were not loaded.

Report shape::

    {
        "errors":   [{"rule": ..., "atom_id": ..., "message": ..., "severity": "error"}, ...],
        "warnings": [{"rule": ..., "atom_id": ..., "message": ..., "severity": "warning"}, ...],
    }
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from scholialang.atoms import (
    CRITICALITY_RANK,
    Atom,
    Concluding,
    Confidence,
    Evidence,
    Finding,
    Goal,
    Meta,
    Observation,
    Retract,
    Storing,
    Trace,
    Uncertainty,
)


# ── Rule names ───────────────────────────────────────────────────────

RULE_FOR_GOAL_RESOLVES = "for_goal_resolves"
RULE_REFER_AT_LEAST_ONE = "refer_at_least_one"
RULE_CRITICALITY_NON_DECREASING = "criticality_non_decreasing"
RULE_NO_ACTION_IN_CONCLUDING = "no_action_in_concluding"
RULE_SINGLE_ACTIVE_CONCLUDING_PER_GOAL = "single_active_concluding_per_goal"
RULE_MIN_CONFIDENCE_CEILING = "min_confidence_ceiling"

HARD_FAIL_RULES: tuple[str, ...] = (
    RULE_FOR_GOAL_RESOLVES,
    RULE_REFER_AT_LEAST_ONE,
    RULE_CRITICALITY_NON_DECREASING,
)

WARNING_RULES: tuple[str, ...] = (
    RULE_NO_ACTION_IN_CONCLUDING,
    RULE_SINGLE_ACTIVE_CONCLUDING_PER_GOAL,
    RULE_MIN_CONFIDENCE_CEILING,
)

RULE_NAMES: tuple[str, ...] = HARD_FAIL_RULES + WARNING_RULES

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


# ── Report shape ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class Violation:
    """A single rule violation.

    ``severity`` is one of :data:`SEVERITY_ERROR` or :data:`SEVERITY_WARNING`.
    The :meth:`to_dict` form is what the public :func:`validate` entry
    point returns — a frozen dataclass keeps the in-memory shape typed
    while preserving the PRD's dict report contract on the wire.
    """

    rule: str
    atom_id: str
    message: str
    severity: str

    def to_dict(self) -> dict[str, str]:
        return {
            "rule": self.rule,
            "atom_id": self.atom_id,
            "message": self.message,
            "severity": self.severity,
        }


# ── Helpers ──────────────────────────────────────────────────────────


_REFER_RE: re.Pattern[str] = re.compile(
    r"\bREFER\s*:\s*([A-Za-z][A-Za-z0-9_]*)"
)

# Modal verbs that signal action commitment inside a Concluding body.
# ``\b`` boundaries keep ``shouldering`` and ``proposed`` from
# matching when the surface form differs. Case-insensitive so the rule
# fires on ``Should X`` at the start of a sentence too.
_ACTION_MODAL_RE: re.Pattern[str] = re.compile(
    r"\b(should|will|recommend|choose|propose|recommends?|proposes?|chooses?)\s+\w+",
    re.IGNORECASE,
)


def _walk(trace: Trace) -> Iterable[Atom]:
    """Yield every atom in ``trace`` depth-first, descending into children."""
    for step in trace:
        for top in step.atoms:
            yield from _descend(top)


def _descend(atom: Atom) -> Iterable[Atom]:
    yield atom
    for child in atom.children:
        yield from _descend(child)


def _build_id_index(trace: Trace) -> dict[str, Atom]:
    """Map every declared atom id to its atom (depth-first)."""
    index: dict[str, Atom] = {}
    for atom in _walk(trace):
        if atom.id:
            index.setdefault(atom.id, atom)
        if isinstance(atom, Storing) and atom.name:
            index.setdefault(atom.name, atom)
    return index


def _parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _atom_criticality(atom: Atom) -> Optional[str]:
    """Look at the atom's own ``criticality`` field, then child Meta atoms.

    Findings and Observations don't carry ``criticality`` directly in
    the v0.5 catalog; the convention is to attach a ``<Meta criticality=
    ...>`` as a child atom. Goals and Concludings carry it directly.
    """
    direct = getattr(atom, "criticality", None)
    if isinstance(direct, str) and direct:
        return direct
    for child in atom.children:
        if isinstance(child, Meta) and child.criticality:
            return child.criticality
    return None


def _atom_confidence(atom: Atom, all_atoms: list[Atom]) -> Optional[float]:
    """Best-effort confidence read for the cited atom.

    Sources, in order:

    1. ``atom.confidence`` (Observation has this; Finding/Evidence do
       not in the v0.5 catalog).
    2. A sibling ``<Uncertainty on="atom.id" confidence="...">``.
    3. A sibling ``<Confidence on="atom.id" level="...">``.

    Returns ``None`` when nothing parses cleanly — the rule treats
    no-data as vacuous (no warning emitted).
    """
    direct = getattr(atom, "confidence", None)
    parsed = _parse_float(direct)
    if parsed is not None:
        return parsed
    if not atom.id:
        return None
    for other in all_atoms:
        if isinstance(other, Uncertainty) and other.on == atom.id:
            v = _parse_float(other.confidence)
            if v is not None:
                return v
        if isinstance(other, Confidence) and other.on == atom.id:
            v = _parse_float(other.level)
            if v is not None:
                return v
    return None


def _refer_targets(atom: Atom) -> list[str]:
    """Extract REFER: ids declared inline in the atom's content."""
    return _REFER_RE.findall(atom.content or "")


def _retracted_ids(all_atoms: list[Atom]) -> set[str]:
    """Set of atom ids that have been retracted by an explicit <Retract>."""
    return {
        a.target
        for a in all_atoms
        if isinstance(a, Retract) and a.target
    }


# ── Hard-fail rule 1 — for_goal_resolves ─────────────────────────────


def check_for_goal_resolves(
    _trace: Trace,
    index: dict[str, Atom],
    concludings: list[Concluding],
) -> list[Violation]:
    violations: list[Violation] = []
    for c in concludings:
        target = c.for_goal
        if not target:
            # Concluding's __post_init__ already raises in this case,
            # but a hand-mutated atom could reach validation with
            # for_goal unset; surface it as a structural error.
            violations.append(
                Violation(
                    rule=RULE_FOR_GOAL_RESOLVES,
                    atom_id=c.id or "",
                    message="Concluding has no for_goal target.",
                    severity=SEVERITY_ERROR,
                )
            )
            continue
        referenced = index.get(target)
        if referenced is None:
            violations.append(
                Violation(
                    rule=RULE_FOR_GOAL_RESOLVES,
                    atom_id=c.id or "",
                    message=(
                        f"Concluding.for_goal='{target}' does not resolve "
                        "to any declared id in this trace."
                    ),
                    severity=SEVERITY_ERROR,
                )
            )
            continue
        if not isinstance(referenced, Goal):
            violations.append(
                Violation(
                    rule=RULE_FOR_GOAL_RESOLVES,
                    atom_id=c.id or "",
                    message=(
                        f"Concluding.for_goal='{target}' resolves to a "
                        f"<{referenced.kind}>, not a <Goal>."
                    ),
                    severity=SEVERITY_ERROR,
                )
            )
    return violations


# ── Hard-fail rule 2 — refer_at_least_one ────────────────────────────


def check_refer_at_least_one(
    _trace: Trace,
    index: dict[str, Atom],
    concludings: list[Concluding],
) -> list[Violation]:
    violations: list[Violation] = []
    for c in concludings:
        targets = _refer_targets(c)
        valid_targets = [
            t for t in targets
            if isinstance(index.get(t), (Finding, Observation, Evidence))
        ]
        if not valid_targets:
            violations.append(
                Violation(
                    rule=RULE_REFER_AT_LEAST_ONE,
                    atom_id=c.id or "",
                    message=(
                        "Concluding body has no REFER: pointing to a "
                        "Finding, Observation, or Evidence atom."
                    ),
                    severity=SEVERITY_ERROR,
                )
            )
    return violations


# ── Hard-fail rule 3 — criticality_non_decreasing ────────────────────


def _effective_concluding_criticality(
    c: Concluding,
    index: dict[str, Atom],
) -> Optional[str]:
    """Concluding's criticality: declared, or max of cited Findings/Observations.

    Returns ``None`` when neither path yields a known criticality tier;
    the rule treats unknown as vacuous (no error).
    """
    declared = _atom_criticality(c)
    if declared and declared in CRITICALITY_RANK:
        return declared

    ranks: list[int] = []
    for target in _refer_targets(c):
        atom = index.get(target)
        if atom is None:
            continue
        if not isinstance(atom, (Finding, Observation)):
            continue
        crit = _atom_criticality(atom)
        if crit and crit in CRITICALITY_RANK:
            ranks.append(CRITICALITY_RANK[crit])

    if not ranks:
        return None
    max_rank = max(ranks)
    for name, rank in CRITICALITY_RANK.items():
        if rank == max_rank:
            return name
    return None


def _has_retract_for(
    target_id: str, all_atoms: list[Atom]
) -> bool:
    """True if any ``<Retract target="target_id">`` exists in the trace.

    The Retract is the only legitimate path to lower criticality below
    a Goal's declared tier. Reason text is informational — its presence
    is the structural signal.
    """
    return any(
        isinstance(a, Retract) and a.target == target_id
        for a in all_atoms
    )


def check_criticality_non_decreasing(
    _trace: Trace,
    index: dict[str, Atom],
    concludings: list[Concluding],
    all_atoms: list[Atom],
) -> list[Violation]:
    violations: list[Violation] = []
    for c in concludings:
        if not c.for_goal:
            continue
        goal = index.get(c.for_goal)
        if not isinstance(goal, Goal):
            # Caught by for_goal_resolves; don't double-fire.
            continue
        goal_crit = _atom_criticality(goal)
        if not goal_crit or goal_crit not in CRITICALITY_RANK:
            continue  # Goal didn't declare — nothing to compare.
        concl_crit = _effective_concluding_criticality(c, index)
        if not concl_crit or concl_crit not in CRITICALITY_RANK:
            continue  # Vacuous: no comparable signal.
        goal_rank = CRITICALITY_RANK[goal_crit]
        concl_rank = CRITICALITY_RANK[concl_crit]
        if concl_rank >= goal_rank:
            continue  # Elevation or match — explicitly allowed.
        if _has_retract_for(c.for_goal, all_atoms):
            continue  # Explicit Retract authorizes the downgrade.
        violations.append(
            Violation(
                rule=RULE_CRITICALITY_NON_DECREASING,
                atom_id=c.id or "",
                message=(
                    f"Concluding criticality '{concl_crit}' (rank "
                    f"{concl_rank}) is lower than Goal '{c.for_goal}' "
                    f"criticality '{goal_crit}' (rank {goal_rank}). "
                    "Authorize the downgrade with a <Retract target='"
                    f"{c.for_goal}'/>."
                ),
                severity=SEVERITY_ERROR,
            )
        )
    return violations


# ── Warning rule 4 — no_action_in_concluding ─────────────────────────


def check_no_action_in_concluding(
    _trace: Trace,
    _index: dict[str, Atom],
    concludings: list[Concluding],
) -> list[Violation]:
    violations: list[Violation] = []
    for c in concludings:
        content = c.content or ""
        match = _ACTION_MODAL_RE.search(content)
        if match:
            violations.append(
                Violation(
                    rule=RULE_NO_ACTION_IN_CONCLUDING,
                    atom_id=c.id or "",
                    message=(
                        f"Concluding body contains action-modal phrase "
                        f"'{match.group(0)}'. Concluding states epistemic "
                        "close; route action commitment through <Deciding>."
                    ),
                    severity=SEVERITY_WARNING,
                )
            )
    return violations


# ── Warning rule 5 — single_active_concluding_per_goal ───────────────


def check_single_active_concluding_per_goal(
    _trace: Trace,
    _index: dict[str, Atom],
    concludings: list[Concluding],
    all_atoms: list[Atom],
) -> list[Violation]:
    retracted = _retracted_ids(all_atoms)
    active_by_goal: dict[str, list[Concluding]] = {}
    for c in concludings:
        if not c.for_goal:
            continue
        if c.id and c.id in retracted:
            continue
        active_by_goal.setdefault(c.for_goal, []).append(c)

    violations: list[Violation] = []
    for goal_id, group in active_by_goal.items():
        if len(group) <= 1:
            continue
        for c in group:
            violations.append(
                Violation(
                    rule=RULE_SINGLE_ACTIVE_CONCLUDING_PER_GOAL,
                    atom_id=c.id or "",
                    message=(
                        f"Goal '{goal_id}' has {len(group)} active "
                        "Concludings; expected at most one. Retract the "
                        "superseded Concluding(s) to keep the close set "
                        "single-valued."
                    ),
                    severity=SEVERITY_WARNING,
                )
            )
    return violations


# ── Warning rule 6 — min_confidence_ceiling ──────────────────────────


def check_min_confidence_ceiling(
    _trace: Trace,
    index: dict[str, Atom],
    concludings: list[Concluding],
    all_atoms: list[Atom],
) -> list[Violation]:
    violations: list[Violation] = []
    for c in concludings:
        if c.confidence is None:
            continue  # No declared ceiling to compare.
        cited_confs: list[float] = []
        for target in _refer_targets(c):
            atom = index.get(target)
            if atom is None:
                continue
            if not isinstance(atom, (Finding, Evidence)):
                continue
            conf = _atom_confidence(atom, all_atoms)
            if conf is not None:
                cited_confs.append(conf)
        if not cited_confs:
            continue  # Nothing to ceiling against.
        min_conf = min(cited_confs)
        if c.confidence > min_conf:
            violations.append(
                Violation(
                    rule=RULE_MIN_CONFIDENCE_CEILING,
                    atom_id=c.id or "",
                    message=(
                        f"Concluding.confidence={c.confidence} exceeds "
                        f"the minimum confidence of cited Findings/"
                        f"Evidence ({min_conf}); declared confidence is "
                        "epistemically overreaching the supporting chain."
                    ),
                    severity=SEVERITY_WARNING,
                )
            )
    return violations


# ── Orchestration ────────────────────────────────────────────────────


def validate(trace: Trace) -> dict[str, list[dict[str, str]]]:
    """Run the six v0.5 rules and return the PRD-shaped report.

    Returns a dict with two keys::

        {"errors": [...], "warnings": [...]}

    Each entry is a dict ``{"rule", "atom_id", "message", "severity"}``.

    Backwards compatibility: a trace with no ``<Concluding>`` atoms
    short-circuits to ``{"errors": [], "warnings": []}`` — every new
    rule is gated on the presence of Concluding atoms.
    """
    all_atoms = list(_walk(trace))
    concludings = [a for a in all_atoms if isinstance(a, Concluding)]
    if not concludings:
        return {"errors": [], "warnings": []}

    index = _build_id_index(trace)

    violations: list[Violation] = []
    violations.extend(check_for_goal_resolves(trace, index, concludings))
    violations.extend(check_refer_at_least_one(trace, index, concludings))
    violations.extend(
        check_criticality_non_decreasing(trace, index, concludings, all_atoms)
    )
    violations.extend(check_no_action_in_concluding(trace, index, concludings))
    violations.extend(
        check_single_active_concluding_per_goal(
            trace, index, concludings, all_atoms
        )
    )
    violations.extend(
        check_min_confidence_ceiling(trace, index, concludings, all_atoms)
    )

    errors = [v.to_dict() for v in violations if v.severity == SEVERITY_ERROR]
    warnings = [v.to_dict() for v in violations if v.severity == SEVERITY_WARNING]
    return {"errors": errors, "warnings": warnings}
