"""Unit tests for Scholia v0.4-B validator enforcement (story V04B-02).

Per PRD rsi-scholia-v0.4-code-graph-metadata:

* ``location`` MUST match ``<path>:<start>:<end>``; malformed values
  reject.
* ``<Edge type=>`` MUST be in :data:`V04B_EDGE_TYPES`; out-of-set
  values reject.
* ``<Edge target=>`` MUST be a non-empty string.
* Absence of any new field is still valid — backwards compat with
  v0.3 atoms.
"""
from __future__ import annotations

import pytest

from scholialang.atoms import (
    V04B_EDGE_TYPES,
    Edge,
    Observation,
    Step,
    is_valid_edge_type,
    is_valid_location,
)
from scholialang.parser import ScholiaParseError, parse
from scholialang.validator import (
    RULE_LOCATION_EDGE_SHAPE,
    check_location_edge_shape,
    validate,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _trace_with(obs: Observation) -> list[Step]:
    return [Step(id="step_01", atoms=[obs])]


# ── is_valid_location helper ─────────────────────────────────────────


def test_is_valid_location_accepts_canonical_shape() -> None:
    assert is_valid_location("src/foo.py:1:1")
    assert is_valid_location("src/example/atlas/code_graph/python_ast.py:42:120")
    assert is_valid_location("a.py:1:9999")


def test_is_valid_location_rejects_malformed() -> None:
    assert not is_valid_location("")
    assert not is_valid_location(None)
    assert not is_valid_location("src/foo.py")
    assert not is_valid_location("src/foo.py:42")
    assert not is_valid_location("src/foo.py:42:abc")
    assert not is_valid_location("src/foo.py:42:")
    assert not is_valid_location(":42:56")
    assert not is_valid_location("file:with:colons.py:1:2")


# ── is_valid_edge_type helper ────────────────────────────────────────


def test_is_valid_edge_type_accepts_closed_set() -> None:
    for value in V04B_EDGE_TYPES:
        assert is_valid_edge_type(value), value


def test_is_valid_edge_type_rejects_out_of_set() -> None:
    assert not is_valid_edge_type("calls")  # reserved for v0.4.x
    assert not is_valid_edge_type("foo")
    assert not is_valid_edge_type("")
    assert not is_valid_edge_type(None)


# ── check_location_edge_shape direct unit ────────────────────────────


def test_validator_accepts_well_formed_location() -> None:
    obs = Observation(id="Observation_01", location="src/foo.py:42:56")
    errors = check_location_edge_shape(_trace_with(obs), {})
    assert errors == []


def test_validator_rejects_malformed_location() -> None:
    obs = Observation(id="Observation_01", location="src/foo.py")
    errors = check_location_edge_shape(_trace_with(obs), {})
    assert len(errors) == 1
    assert errors[0].rule == RULE_LOCATION_EDGE_SHAPE
    assert "location" in errors[0].message


def test_validator_accepts_known_edge_type() -> None:
    edge = Edge(edge_type="depends_on", target="example.foo")
    obs = Observation(id="Observation_01", children=[edge])
    errors = check_location_edge_shape(_trace_with(obs), {})
    assert errors == []


def test_validator_rejects_unknown_edge_type() -> None:
    edge = Edge(edge_type="calls", target="example.foo")
    obs = Observation(id="Observation_01", children=[edge])
    errors = check_location_edge_shape(_trace_with(obs), {})
    assert len(errors) == 1
    assert "calls" in errors[0].message


def test_validator_rejects_empty_edge_target() -> None:
    edge = Edge(edge_type="depends_on", target="   ")
    obs = Observation(id="Observation_01", children=[edge])
    errors = check_location_edge_shape(_trace_with(obs), {})
    assert any("target" in e.message for e in errors)


def test_v03_atoms_without_new_fields_still_validate() -> None:
    """Backwards compat — atoms with no location/Edge produce no errors."""
    obs = Observation(id="Observation_01", content="Plain v0.3 observation.")
    errors = check_location_edge_shape(_trace_with(obs), {})
    assert errors == []


# ── End-to-end via parser ────────────────────────────────────────────


def test_parser_accepts_location_attribute() -> None:
    text = """
    <Step id="step_01">
      <Goal id="Goal_01" scope="trace" priority="required">For x.</Goal>
      <Observation id="Observation_01" location="src/foo.py:1:9">Exports foo.</Observation>
      <Finding id="Finding_01" for_goal="Goal_01" status="met">A util.</Finding>
    </Step>
    """.strip()
    trace = parse(text)
    obs = trace[0].atoms[1]
    assert isinstance(obs, Observation)
    assert obs.location == "src/foo.py:1:9"
    result = validate(trace)
    assert result.ok, result.errors


def test_parser_accepts_edge_subelement() -> None:
    text = """
    <Step id="step_01">
      <Goal id="Goal_01" scope="trace" priority="required">For x.</Goal>
      <Observation id="Observation_01">Depends on pathlib.<Edge type="depends_on" target="pathlib"/></Observation>
      <Finding id="Finding_01" for_goal="Goal_01" status="met">A util.</Finding>
    </Step>
    """.strip()
    trace = parse(text)
    obs = trace[0].atoms[1]
    edge = obs.children[0]
    assert isinstance(edge, Edge)
    assert edge.edge_type == "depends_on"
    assert edge.target == "pathlib"
    # Reference-completeness must NOT flag Edge.target (file path).
    result = validate(trace)
    assert result.ok, result.errors


def test_full_validate_rejects_malformed_location_e2e() -> None:
    """v0.3.1's strict-closed-set posture promoted malformed-location
    detection from validator-only to parse-time rejection. Same
    enforcement, earlier in the pipeline.
    """
    text = """
    <Step id="step_01">
      <Goal id="Goal_01" scope="trace" priority="required">For x.</Goal>
      <Observation id="Observation_01" location="src/foo.py">Exports foo.</Observation>
      <Finding id="Finding_01" for_goal="Goal_01" status="met">A util.</Finding>
    </Step>
    """.strip()
    with pytest.raises(ScholiaParseError, match="location"):
        parse(text)


def test_full_validate_rejects_unknown_edge_type_e2e() -> None:
    """v0.3.1's strict-closed-set posture promoted unknown-edge-type
    detection from validator-only to parse-time rejection.
    """
    text = """
    <Step id="step_01">
      <Goal id="Goal_01" scope="trace" priority="required">For x.</Goal>
      <Observation id="Observation_01">Calls something.<Edge type="calls" target="example.foo"/></Observation>
      <Finding id="Finding_01" for_goal="Goal_01" status="met">A util.</Finding>
    </Step>
    """.strip()
    with pytest.raises(ScholiaParseError, match="calls"):
        parse(text)


def test_referenced_by_edge_type_accepted_e2e() -> None:
    """``referenced_by`` is in the closed set so reverse-index output validates."""
    text = """
    <Step id="step_01">
      <Goal id="Goal_01" scope="trace" priority="required">For x.</Goal>
      <Observation id="Observation_01">Imported by foo.<Edge type="referenced_by" target="src/foo.py"/></Observation>
      <Finding id="Finding_01" for_goal="Goal_01" status="met">A util.</Finding>
    </Step>
    """.strip()
    trace = parse(text)
    result = validate(trace)
    assert result.ok, result.errors
