"""v0.4-D — confidence-attribute acceptance tests.

PRD ``rsi-scholia-v0.4-confidence-scoring`` story V04D-01 names a
specific set of values that must validate / reject. The underlying
validator rule was reserved in v0.3.1 (``RULE_V031_OPTIONAL_FIELDS``
covers the parser-mirrored range check); this file pins the v0.4-D
acceptance criteria directly so the PRD's contract is independently
checkable from the v0.3.1 test surface.

The hard-constraints stated:

* Float in ``[0.0, 1.0]`` inclusive — accept.
* Out-of-range (``> 1.0`` or ``< 0.0``) — reject.
* Unparseable (non-numeric) — reject.
* Absence — accept (semantic default of ``1.0``).
* No part of the validator GATES on confidence — it's a hint, not a
  guard. We assert the closed-set range check is the *only*
  confidence-related rejection.
"""
from __future__ import annotations

import pytest

from scholialang.atoms import (
    Finding,
    Goal,
    Observation,
    Step,
)
from scholialang.parser import ScholiaParseError, parse
from scholialang.validator import (
    RULE_V031_OPTIONAL_FIELDS,
    check_v031_optional_fields,
    validate,
)


def _wrap(*atoms) -> list[Step]:
    return [Step(id="Step_01", name="t", atoms=list(atoms))]


def _idx(trace):
    from scholialang.validator import _build_id_index  # type: ignore

    return _build_id_index(trace)


def _full_trace(*observations: Observation) -> list[Step]:
    """Build a complete, otherwise-valid trace around given Observations.

    The Goal+Finding closure means the validator's other rules pass,
    so any rejection MUST come from the confidence check itself —
    isolating the v0.4-D contract from incidental rule failures.
    """
    goal = Goal(id="Goal_01", scope="trace", priority="required",
                content="Acceptance scaffold.")
    finding = Finding(id="Finding_01", for_goal="Goal_01", status="met",
                      content="Closed.")
    return [Step(
        id="Step_01",
        name="t",
        atoms=[goal, *observations, finding],
    )]


# ── Boundary + interior accept ────────────────────────────────────────


@pytest.mark.parametrize("value", ["0.0", "0.5", "1.0"])
def test_confidence_within_range_validates(value: str) -> None:
    """V04D-01 criteria: 0.0, 0.5, 1.0 are valid."""
    obs = Observation(id="Obs_01", confidence=value)
    trace = _full_trace(obs)
    result = validate(trace)
    assert result.ok, result.summary()


# ── Out-of-range reject ───────────────────────────────────────────────


@pytest.mark.parametrize("value", ["1.5", "-0.1", "2.0", "100"])
def test_confidence_out_of_range_rejected(value: str) -> None:
    """V04D-01 criteria: > 1.0 or < 0.0 must reject."""
    obs = Observation(id="Obs_01", confidence=value)
    errs = check_v031_optional_fields(_wrap(obs), _idx(_wrap(obs)))
    assert errs, "out-of-range confidence must produce a validation error"
    assert errs[0].rule == RULE_V031_OPTIONAL_FIELDS
    assert "confidence" in errs[0].message


# ── Unparseable reject ───────────────────────────────────────────────


@pytest.mark.parametrize("value", ["abc", "high", "yes", "none", ""])
def test_confidence_unparseable_rejected(value: str) -> None:
    """V04D-01 criteria: non-numeric strings must reject."""
    obs = Observation(id="Obs_01", confidence=value)
    errs = check_v031_optional_fields(_wrap(obs), _idx(_wrap(obs)))
    assert errs, f"unparseable confidence {value!r} must produce an error"
    assert errs[0].rule == RULE_V031_OPTIONAL_FIELDS


# ── Absence accepted (semantic default 1.0) ───────────────────────────


def test_confidence_absent_validates() -> None:
    """V04D-01 criteria: no confidence attribute is accepted.

    Per spec, absence is semantically equivalent to ``confidence="1.0"``
    — the validator MUST NOT require the attribute on Observation
    atoms, preserving v0.3 backwards compatibility.
    """
    obs = Observation(id="Obs_01", content="No confidence attr at all.")
    trace = _full_trace(obs)
    result = validate(trace)
    assert result.ok, result.summary()


# ── Advisory-only: no other rule keys off confidence ──────────────────


def test_confidence_does_not_gate_downstream_rules() -> None:
    """Hard constraint: confidence is ADVISORY — no other rule reads it.

    A trace where every Observation carries ``confidence="0.0"`` (the
    most-uncertain value the validator accepts) must still pass every
    other rule. Confidence is a hint for downstream tools, not a
    guard inside the validator.
    """
    low_obs = Observation(
        id="Obs_01",
        content="Speculative claim.",
        confidence="0.0",
    )
    trace = _full_trace(low_obs)
    result = validate(trace)
    assert result.ok, result.summary()
    # And every per-rule bucket is empty for the confidence-related
    # rule when the range check passes.
    assert result.errors_by_rule[RULE_V031_OPTIONAL_FIELDS] == []


# ── Parser mirror — wire-level rejection ──────────────────────────────


def test_parser_rejects_confidence_out_of_range() -> None:
    """Parser-side mirror: out-of-range confidence fails before validator.

    The parser enforces the same closed-set range so a malformed
    Scholia codeblock from the rewriter never reaches the AST in a
    half-valid state.
    """
    bad = (
        '<Step id="S">'
        '<Observation id="O" confidence="-0.5">x</Observation>'
        "</Step>"
    )
    with pytest.raises(ScholiaParseError, match="confidence"):
        parse(bad)


def test_parser_accepts_confidence_in_range() -> None:
    """Parser accepts valid confidence values end-to-end."""
    good = (
        '<Step id="S">'
        '<Goal id="G" scope="trace" priority="required">g</Goal>'
        '<Observation id="O" confidence="0.85">x</Observation>'
        '<Finding id="F" for_goal="G" status="met">f</Finding>'
        "</Step>"
    )
    trace = parse(good)
    assert trace, "valid trace must parse"
    # The wire confidence string is round-tripped onto the atom verbatim.
    obs = trace[0].atoms[1]
    assert getattr(obs, "confidence", None) == "0.85"
