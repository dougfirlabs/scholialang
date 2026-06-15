"""v0.6.1 — optional ``status`` attribute on ``<Concluding>``.

Covers the v0.6.1 contract: a ``<Concluding>`` may carry an OPTIONAL
``status`` enum (``met|unmet|partially_met``). The parser accepts it, the
serializer round-trips it, the validator flags out-of-enum values, a
status-less Concluding stays valid (back-compat), and ``goal_declared``
reads the status when present.
"""
from __future__ import annotations

import pytest

from scholialang.atoms import (
    KIND_SPECIFIC_FIELDS,
    Concluding,
    atom_to_xml,
)
from scholialang.parser import parse, parse_atom
from scholialang.validator import (
    RULE_GOAL_DECLARED,
    RULE_V031_OPTIONAL_FIELDS,
    validate,
)


def _wrap(body: str) -> str:
    return f'<Step id="S_01" name="v0.6.1">{body}</Step>'


def _supporting_chain() -> str:
    """A Hypothesis/Evidence/Finding chain a Concluding can cite."""
    return (
        '<Hypothesis id="H_01">The migration is complete.</Hypothesis>'
        '<Evidence id="E_01" for="H_01" polarity="supports">Observed.</Evidence>'
        '<Finding id="F_01" for_hyp="H_01" status="met">Satisfied.</Finding>'
    )


# ── Story impl-status-field — dataclass + KIND_SPECIFIC_FIELDS ───────


def test_concluding_status_defaults_to_none():
    atom = Concluding(for_goal="G_01")
    assert atom.status is None


def test_kind_specific_fields_includes_status():
    assert "status" in KIND_SPECIFIC_FIELDS["Concluding"]


def test_parse_concluding_with_status():
    atom = parse_atom(
        '<Concluding id="C_01" for_goal="G_01" status="met">'
        "REFER:F_01 closes.</Concluding>"
    )
    assert isinstance(atom, Concluding)
    assert atom.status == "met"
    assert atom.for_goal == "G_01"


def test_parse_status_less_concluding_still_parses():
    atom = parse_atom(
        '<Concluding id="C_01" for_goal="G_01">REFER:F_01 closes.</Concluding>'
    )
    assert isinstance(atom, Concluding)
    assert atom.status is None


def test_serializer_round_trips_status():
    atom = Concluding(id="C_01", for_goal="G_01", status="partially_met")
    xml = atom_to_xml(atom)
    assert 'status="partially_met"' in xml
    reparsed = parse_atom(xml)
    assert isinstance(reparsed, Concluding)
    assert reparsed.status == "partially_met"


# ── Story impl-enum-and-validator — enum + goal_declared ─────────────


@pytest.mark.parametrize("status", ["met", "unmet", "partially_met"])
def test_status_bearing_concluding_validates_ok(status):
    """The v0.6.1 golden — a status-bearing Concluding validates ok=True."""
    xml = _wrap(
        '<Goal id="G_01" priority="required">Ship the migration.</Goal>'
        + _supporting_chain()
        + f'<Concluding id="C_01" for_goal="G_01" status="{status}">'
        + "REFER:F_01 closes.</Concluding>"
    )
    result = validate(parse(xml))
    assert result.ok, result.errors
    assert result.errors == []


def test_invalid_status_is_flagged():
    xml = _wrap(
        '<Goal id="G_01" priority="required">g</Goal>'
        + _supporting_chain()
        + '<Concluding id="C_01" for_goal="G_01" status="bogus">'
        + "REFER:F_01 closes.</Concluding>"
    )
    result = validate(parse(xml))
    errors = result.errors_by_rule[RULE_V031_OPTIONAL_FIELDS]
    assert len(errors) == 1
    assert errors[0].atom_id == "C_01"
    assert "status" in errors[0].message


def test_absent_status_is_valid_backcompat():
    """A status-less Concluding validates exactly as in v0.5/v0.6.0."""
    xml = _wrap(
        '<Goal id="G_01" priority="required">g</Goal>'
        + _supporting_chain()
        + '<Concluding id="C_01" for_goal="G_01">REFER:F_01 closes.</Concluding>'
    )
    result = validate(parse(xml))
    assert result.ok, result.errors


def test_goal_declared_reads_concluding_status():
    """A required Goal is closed by a status-bearing Concluding alone.

    No Finding closes G_01 (the supporting Finding is keyed to H_01), so the
    only thing that can satisfy goal_declared is the Concluding — and it
    carries an in-enum status, which the rule must read and accept.
    """
    xml = _wrap(
        '<Goal id="G_01" priority="required">Ship it.</Goal>'
        + _supporting_chain()
        + '<Concluding id="C_01" for_goal="G_01" status="met">'
        + "REFER:F_01 closes.</Concluding>"
    )
    result = validate(parse(xml))
    assert result.errors_by_rule[RULE_GOAL_DECLARED] == []
    assert result.ok, result.errors
