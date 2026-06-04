"""Tests for scholialang.atoms — the shared contract."""
from __future__ import annotations

import warnings

from scholialang.atoms import (
    ATOM_KINDS,
    CRITICALITY_RANK,
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
    atom_class_for_kind,
    field_name,
    wire_name,
)


# v0.5 locks the closed set at 32 atoms: the v0.4 catalog plus the
# chain-level ``Concluding`` close atom.
def test_atom_catalog_has_v0_5_count():
    assert len(ATOM_KINDS) == 32
    assert "Concluding" in ATOM_KINDS


# Spec requires exactly 11 operators.
def test_operator_catalog_has_11_ops():
    assert len(OPERATORS) == 11
    assert set(OPERATORS) == {
        "AND", "OR", "XOR", "NOT", "IMPLIES", "REFER",
        "FORALL", "EXISTS", "BEFORE", "AFTER", "EQUALS",
    }


# Spec requires exactly 6 primitives.
def test_primitive_catalog_has_6_primitives():
    assert len(PRIMITIVES) == 6
    assert set(PRIMITIVES) == {"LIST", "SET", "MAP", "STRING", "NUMBER", "BOOL"}


ALL_ATOMS = [
    Thinking, Observation, Action,
    Hypothesis, Evidence, Finding, Contradiction, Uncertainty, Retract,
    Concluding,
    Deciding, Alternative, Branch, Loop, Parallel,
    Storing, Print, Reference, Implication,
    Handoff, Question, Review,
    Constraint, Goal, Confidence, EventRef, Budget, Cost,
]


def test_every_atom_kind_instantiates():
    for cls in ALL_ATOMS:
        if cls is Concluding:
            instance = cls(for_goal="G_01")
        else:
            instance = cls()
        assert isinstance(instance, Atom)
        assert cls.kind in ATOM_KINDS
        assert instance.kind == cls.kind


def test_step_has_id_name_atoms():
    step = Step(id="s", name="label")
    assert step.id == "s"
    assert step.name == "label"
    assert step.atoms == []


def test_evidence_carries_for_ref_and_polarity():
    ev = Evidence(for_ref="H_01", polarity="supports", content="x")
    assert ev.for_ref == "H_01"
    assert ev.polarity == "supports"


def test_finding_uses_for_hyp_canonical_reference():
    f = Finding(id="F_01", for_hyp="H_01", status="met")
    assert f.for_hyp == "H_01"
    assert f.for_goal is None


def test_finding_for_goal_emits_deprecation_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Finding(id="F_01", for_goal="G_01", status="met")
    deprecations = [
        warning
        for warning in caught
        if issubclass(warning.category, DeprecationWarning)
    ]
    assert len(deprecations) == 1
    assert "for_hyp" in str(deprecations[0].message)


def test_finding_from_legacy_maps_for_goal_without_alias():
    f = Finding.from_legacy(
        {"id": "F_01", "for_goal": "G_01", "status": "met"}
    )
    assert f.for_hyp == "G_01"
    assert f.for_goal is None


def test_concluding_requires_goal_reference():
    c = Concluding(id="C_01", for_goal="G_01", confidence=0.8)
    assert c.for_goal == "G_01"
    assert c.confidence == 0.8


def test_criticality_rank_ordering_is_locked():
    assert CRITICALITY_RANK == {
        "incidental": 0,
        "bridge": 1,
        "ledger": 2,
        "verifier": 3,
        "kernel": 4,
    }


def test_confidence_carries_level_and_basis():
    c = Confidence(on="F_01", level="0.95", basis="merge-tree output")
    assert c.on == "F_01"
    assert c.level == "0.95"
    assert c.basis == "merge-tree output"


def test_goal_carries_v02_fields():
    g = Goal(
        id="G_01",
        scope="trace",
        priority="required",
        success_criteria=["tests pass"],
        related_constraints=["C_01"],
        deadline="2026-04-21T12:00:00-07:00",
        failure_modes=["tests fail"],
    )
    assert g.scope == "trace"
    assert g.priority == "required"
    assert g.success_criteria == ["tests pass"]
    assert g.related_constraints == ["C_01"]
    assert g.failure_modes == ["tests fail"]


def test_temporal_and_accounting_atoms_carry_typed_fields():
    ref = EventRef(
        instance="ot_A",
        run_id="run",
        sequence=3,
        for_ref="Obs_01",
        wall_clock="2026-04-21T12:00:00-07:00",
    )
    budget = Budget(for_ref="G_01", tokens=100, actions=2, wall_clock_ms=3000)
    cost = Cost(for_ref="A_01", tokens=42, wall_clock_ms=20, dollars=0.01)
    assert ref.sequence == 3
    assert budget.tokens == 100
    assert cost.dollars == 0.01


def test_alternative_carries_rejection_fields():
    alt = Alternative(label="defer", rejected_because="blocks goal")
    assert alt.label == "defer"
    assert alt.rejected_because == "blocks goal"


def test_retract_carries_target_reason_replacement():
    r = Retract(target="F_02", reason="contradicted", replacement="F_04")
    assert r.target == "F_02"
    assert r.reason == "contradicted"
    assert r.replacement == "F_04"


def test_wire_aliases_map_for_and_as():
    assert wire_name("for_ref") == "for"
    assert wire_name("as_var") == "as"
    assert field_name("for") == "for_ref"
    assert field_name("as") == "as_var"
    # Non-aliased names pass through unchanged.
    assert wire_name("content") == "content"
    assert field_name("content") == "content"


def test_atom_class_for_kind_unknown_returns_none():
    assert atom_class_for_kind("DefinitelyNotAnAtom") is None


def test_atom_class_for_kind_round_trip():
    for kind in ATOM_KINDS:
        cls = atom_class_for_kind(kind)
        assert cls is not None
        assert cls.kind == kind


def test_children_default_is_independent_list():
    # Regression — shared mutable defaults across instances.
    a = Thinking()
    b = Thinking()
    a.children.append(Finding(id="F1"))
    assert b.children == []


def test_atoms_importable_by_canonical_name():
    # The PRD acceptance criterion: `from scholialang.atoms
    # import Thinking, Observation, Finding, ...` works. The imports
    # at the top of this file prove it at import time.
    assert Thinking.__name__ == "Thinking"
    assert Observation.__name__ == "Observation"
    assert Finding.__name__ == "Finding"
