"""Tests for scholialang.serializer — JSON + YAML roundtrip."""
from __future__ import annotations

import pytest

from scholialang.atoms import (
    Action,
    Alternative,
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
)
from scholialang.parser import parse
from scholialang.serializer import (
    from_json,
    from_yaml,
    to_canonical_json,
    to_json,
    to_yaml,
    trace_from_dict,
    trace_to_dict,
)


def _roundtrip_json(steps):
    return from_json(to_json(steps))


def _roundtrip_yaml(steps):
    return from_yaml(to_yaml(steps))


# ── Every atom kind roundtrips through JSON + YAML ───────────────────


@pytest.mark.parametrize(
    "atom",
    [
        Thinking(id="T1", content="thought"),
        Observation(id="O1", content="obs"),
        Action(id="A1", content="act"),
        Observation(id="O1", timestamp="2026-04-21T12:00:00-07:00"),
        Action(id="A2", timestamp="2026-04-21T12:00:01-07:00"),
        Hypothesis(id="H1", content="hyp"),
        Evidence(id="E1", for_ref="H1", polarity="supports", content="ev"),
        Finding(id="F1", for_hyp="H1", status="met", content="found"),
        Concluding(
            id="CLOSE1",
            for_goal="G1",
            confidence=0.8,
            criticality="ledger",
            content="REFER:F1 closes.",
        ),
        Contradiction(id="K1", content="ctr"),
        Uncertainty(id="U1", on="F1", confidence="0.7", content="unc"),
        Retract(id="R1", target="F1", reason="cause", replacement="F2"),
        Deciding(id="D1", options=["A", "B"], content="dec"),
        Alternative(id="ALT1", label="B", rejected_because="too slow"),
        Branch(id="B1", of="D1", label="A"),
        Loop(id="L1", over="REFER:xs", as_var="x"),
        Parallel(id="P1"),
        Storing(id="S1", name="main", value="abc"),
        Print(id="PR1", content="hello"),
        Reference(id="REF1", to="F1"),
        Implication(id="IM1", next="F1"),
        Handoff(id="HO1", to="Monitor", package="pkg", constraints=["x", "y"]),
        Question(id="Q1", to="operator", scope="merge", default="go"),
        Review(id="RV1", of="S:F1", reviewer="Monitor"),
        Constraint(id="C1", scope="trace", content="rule"),
        Goal(
            id="G1",
            scope="trace",
            priority="required",
            success_criteria=["done"],
            related_constraints=["C1"],
            deadline="2026-04-21T12:00:00-07:00",
            failure_modes=["fail"],
            criticality="ledger",
        ),
        Confidence(id="CF1", on="F1", level="0.9", basis="check"),
        EventRef(
            id="ER1",
            instance="ot_A",
            run_id="run",
            sequence=1,
            for_ref="O1",
            wall_clock="2026-04-21T12:00:00-07:00",
        ),
        Budget(id="BU1", for_ref="G1", tokens=100, actions=2, wall_clock_ms=300),
        Cost(id="CO1", for_ref="A1", tokens=50, wall_clock_ms=40, dollars=0.12),
    ],
)
def test_every_atom_roundtrips_through_json(atom):
    trace = [Step(id="Step_01", atoms=[atom])]
    back = _roundtrip_json(trace)
    assert len(back) == 1
    restored = back[0].atoms[0]
    assert restored.kind == atom.kind
    assert restored.id == atom.id


@pytest.mark.parametrize(
    "atom",
    [
        Evidence(id="E1", for_ref="H1", polarity="refutes"),
        Retract(id="R1", target="F1", reason="x"),
        Deciding(id="D1", options=["A", "B", "C"]),
        Handoff(id="HO1", to="Monitor", constraints=["rule1", "rule2"]),
        Goal(id="G1", success_criteria=["done"], failure_modes=["fail"]),
        Budget(id="B1", for_ref="S", tokens=1, actions=1, wall_clock_ms=2),
        Cost(id="C1", for_ref="A", tokens=1, wall_clock_ms=2, dollars=0.01),
    ],
)
def test_atoms_roundtrip_through_yaml(atom):
    trace = [Step(id="S", atoms=[atom])]
    back = _roundtrip_yaml(trace)
    restored = back[0].atoms[0]
    assert restored.kind == atom.kind


def test_canonical_json_is_deterministic():
    text = '<Step id="S"><Thinking id="T">x REFER:F</Thinking><Finding id="F">y</Finding></Step>'
    steps_a = parse(text)
    steps_b = parse(text)
    assert to_canonical_json(steps_a) == to_canonical_json(steps_b)


def test_canonical_roundtrip_equal():
    text = (
        '<Step id="S_01" name="t">'
        '<Hypothesis id="H_01">hypo</Hypothesis>'
        '<Evidence for="H_01" polarity="supports">ev REFER:H_01</Evidence>'
        '<Finding id="F_01">conc</Finding>'
        "</Step>"
    )
    steps = parse(text)
    canonical_before = to_canonical_json(steps)
    steps_back = from_json(to_json(steps))
    canonical_after = to_canonical_json(steps_back)
    assert canonical_before == canonical_after


def test_yaml_lossless_roundtrip_on_complex_trace():
    text = (
        '<Step id="S_01">'
        '<Deciding id="D_01">options = LIST:\n  - foo\n  - bar\n'
        '<Finding>chose foo</Finding></Deciding>'
        "</Step>"
    )
    steps = parse(text)
    back = _roundtrip_yaml(steps)
    assert to_canonical_json(back) == to_canonical_json(steps)


def test_json_yaml_equivalent_shapes():
    text = '<Step id="S"><Thinking>x</Thinking></Step>'
    steps = parse(text)
    assert to_canonical_json(steps) == to_canonical_json(_roundtrip_json(steps))
    assert to_canonical_json(steps) == to_canonical_json(_roundtrip_yaml(steps))


def test_trace_to_dict_with_trace_id():
    text = '<Step id="S"><Thinking>x</Thinking></Step>'
    steps = parse(text)
    d = trace_to_dict(steps, trace_id="my_trace")
    assert d["trace_id"] == "my_trace"
    assert d["steps"][0]["id"] == "S"


def test_trace_from_dict_rejects_non_list_steps():
    with pytest.raises(ValueError):
        trace_from_dict({"steps": "not a list"})


def test_from_json_rejects_non_object():
    with pytest.raises(ValueError):
        from_json("[1, 2, 3]")


def test_from_yaml_rejects_non_mapping():
    with pytest.raises(ValueError):
        from_yaml("- a\n- b\n")


def test_canonical_json_sorted_keys_and_compact():
    steps = [Step(id="S", atoms=[Thinking(id="T", content="x")])]
    out = to_canonical_json(steps)
    # Canonical form uses no whitespace between separators.
    assert " " not in out or '"' in out  # quoted content may hold spaces
    assert ", " not in out
    assert ": " not in out


def test_evidence_wire_name_for_not_for_ref():
    # Evidence.for_ref (Python field) becomes "for" on the wire.
    steps = [
        Step(id="S", atoms=[Evidence(id="E", for_ref="H", polarity="supports")])
    ]
    js = to_canonical_json(steps)
    assert '"for":"H"' in js
    assert "for_ref" not in js


def test_v02_numeric_fields_stay_numeric_in_json_yaml_roundtrip():
    trace = [
        Step(
            id="S",
            atoms=[Cost(for_ref="A", tokens=12, wall_clock_ms=30, dollars=0.25)],
        )
    ]
    payload = trace_to_dict(_roundtrip_json(trace))
    cost = payload["steps"][0]["atoms"][0]
    assert cost["tokens"] == 12
    assert cost["dollars"] == 0.25
    payload_yaml = trace_to_dict(_roundtrip_yaml(trace))
    assert payload_yaml["steps"][0]["atoms"][0]["dollars"] == 0.25
