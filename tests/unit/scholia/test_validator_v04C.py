"""Validator acceptance/rejection tests pinning the v0.4-C PRD criteria.

v0.3.1 already wired the closed-set enforcement for ``<Meta>``,
``<Effect>``, and ``<Ref>`` via ``RULE_V031_OPTIONAL_FIELDS``. v0.4-C
adds the rewriter integration that actually populates those slots,
so this module pins the PRD's acceptance criteria as named tests:

* Each closed-set value in :data:`V031_META_CRITICALITIES` /
  :data:`V031_EFFECT_KINDS` / :data:`V031_REF_TYPES` is accepted.
* Each unknown value rejects with ``RULE_V031_OPTIONAL_FIELDS``.
* Absence of every v0.4-C field validates as the v0.3 shape (no
  spurious errors).
* Parser-side rejection mirrors the validator-side rejection for the
  same closed-set contract.
"""
from __future__ import annotations

import pytest

from scholialang.atoms import (
    V031_EFFECT_KINDS,
    V031_META_CRITICALITIES,
    V031_REF_TYPES,
    Effect,
    Finding,
    Goal,
    Meta,
    Observation,
    Ref,
    Step,
)
from scholialang.parser import ScholiaParseError, parse
from scholialang.validator import (
    RULE_V031_OPTIONAL_FIELDS,
    validate,
)


def _step_with(*atoms) -> list[Step]:
    """Wrap atoms in a minimally-valid Step (Goal + Finding) for validation."""
    goal = Goal(id="Goal_01", scope="trace", priority="required")
    finding = Finding(id="Finding_01", for_goal="Goal_01", status="met")
    return [Step(id="step_01", atoms=[goal, *atoms, finding])]


# ── Meta criticality — closed-set acceptance ─────────────────────────


@pytest.mark.parametrize("level", sorted(V031_META_CRITICALITIES))
def test_meta_criticality_accepts_each_closed_set_value(level: str) -> None:
    trace = _step_with(Meta(criticality=level))
    result = validate(trace)
    assert not result.errors_by_rule[RULE_V031_OPTIONAL_FIELDS]


@pytest.mark.parametrize("bad", ["", "important", "high", "Kernel", "KERNEL"])
def test_meta_criticality_rejects_unknown_value(bad: str) -> None:
    trace = _step_with(Meta(criticality=bad))
    result = validate(trace)
    assert result.errors_by_rule[RULE_V031_OPTIONAL_FIELDS], (
        f"expected RULE_V031_OPTIONAL_FIELDS to reject criticality={bad!r}"
    )


def test_meta_absent_validates() -> None:
    """A Step with no Meta is a v0.3 shape — validator must be silent."""
    trace = _step_with(Observation(id="Observation_01", content="x"))
    result = validate(trace)
    assert not result.errors_by_rule[RULE_V031_OPTIONAL_FIELDS]


# ── Effect kind — closed-set acceptance ──────────────────────────────


@pytest.mark.parametrize("kind", sorted(V031_EFFECT_KINDS))
def test_effect_kind_accepts_each_closed_set_value(kind: str) -> None:
    trace = _step_with(Effect(effect_kind=kind))
    result = validate(trace)
    assert not result.errors_by_rule[RULE_V031_OPTIONAL_FIELDS]


@pytest.mark.parametrize("bad", ["", "filesystem", "io_read", "WRITE", "Network"])
def test_effect_kind_rejects_unknown_value(bad: str) -> None:
    trace = _step_with(Effect(effect_kind=bad))
    result = validate(trace)
    assert result.errors_by_rule[RULE_V031_OPTIONAL_FIELDS]


# ── Ref type — closed-set acceptance ─────────────────────────────────


@pytest.mark.parametrize("rtype", sorted(V031_REF_TYPES))
def test_ref_type_accepts_each_closed_set_value(rtype: str) -> None:
    trace = _step_with(Ref(ref_type=rtype, target="tests/test_foo.py"))
    result = validate(trace)
    assert not result.errors_by_rule[RULE_V031_OPTIONAL_FIELDS]


@pytest.mark.parametrize("bad", ["", "test", "owner", "Test_Owner"])
def test_ref_type_rejects_unknown_value(bad: str) -> None:
    trace = _step_with(Ref(ref_type=bad, target="tests/test_foo.py"))
    result = validate(trace)
    assert result.errors_by_rule[RULE_V031_OPTIONAL_FIELDS]


# ── Combined shape — full v0.4-C atom ────────────────────────────────


def test_combined_v04c_atoms_validate() -> None:
    """A Step using Meta + Effect + Ref simultaneously validates cleanly."""
    obs = Observation(
        id="Observation_01",
        content="Exports validate.",
        children=[Effect(effect_kind="pure"), Ref(ref_type="test_owner", target="tests/x.py")],
    )
    trace = _step_with(Meta(criticality="kernel"), obs)
    result = validate(trace)
    assert result.ok, f"unexpected errors: {result.errors}"


# ── Parser parity — wire form rejection mirrors validator ────────────


def test_parser_rejects_unknown_criticality_wire_form() -> None:
    bad = (
        '<Step id="step_01">\n'
        '  <Meta criticality="bogus"/>\n'
        '  <Goal id="Goal_01" scope="trace" priority="required">x</Goal>\n'
        '  <Finding id="Finding_01" for_goal="Goal_01" status="met">y</Finding>\n'
        "</Step>"
    )
    with pytest.raises(ScholiaParseError):
        parse(bad)


def test_parser_rejects_unknown_effect_kind_wire_form() -> None:
    bad = (
        '<Step id="step_01">\n'
        '  <Goal id="Goal_01" scope="trace" priority="required">x</Goal>\n'
        '  <Observation id="Observation_01">y<Effect kind="filesystem"/></Observation>\n'
        '  <Finding id="Finding_01" for_goal="Goal_01" status="met">z</Finding>\n'
        "</Step>"
    )
    with pytest.raises(ScholiaParseError):
        parse(bad)


def test_parser_rejects_unknown_ref_type_wire_form() -> None:
    bad = (
        '<Step id="step_01">\n'
        '  <Goal id="Goal_01" scope="trace" priority="required">x</Goal>\n'
        '  <Observation id="Observation_01">y<Ref type="owner" target="tests/x.py"/></Observation>\n'
        '  <Finding id="Finding_01" for_goal="Goal_01" status="met">z</Finding>\n'
        "</Step>"
    )
    with pytest.raises(ScholiaParseError):
        parse(bad)


def test_parser_accepts_full_v04c_wire_form() -> None:
    good = (
        '<Step id="step_01">\n'
        '  <Meta criticality="kernel"/>\n'
        '  <Goal id="Goal_01" scope="trace" priority="required">x</Goal>\n'
        '  <Observation id="Observation_01">y<Effect kind="pure"/></Observation>\n'
        '  <Observation id="Observation_02">z<Ref type="test_owner" target="tests/test_x.py"/></Observation>\n'
        '  <Finding id="Finding_01" for_goal="Goal_01" status="met">w</Finding>\n'
        "</Step>"
    )
    trace = parse(good)
    result = validate(trace)
    assert result.ok, f"unexpected errors: {result.errors}"
