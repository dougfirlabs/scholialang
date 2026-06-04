"""Scholia v0.5 validator coverage."""
from __future__ import annotations

import warnings

import pytest

from scholialang.parser import ScholiaParseError, parse
from scholialang.validator import (
    RULE_CRITICALITY_NON_DECREASING,
    RULE_FOR_GOAL_RESOLVES,
    RULE_MIN_CONFIDENCE_CEILING,
    RULE_NO_ACTION_IN_CONCLUDING,
    RULE_REFER_AT_LEAST_ONE,
    RULE_SINGLE_ACTIVE_CONCLUDING_PER_GOAL,
    validate,
)


def _wrap(body: str) -> str:
    return f'<Step id="S_01" name="v0.5">{body}</Step>'


def _supporting_chain() -> str:
    return (
        '<Hypothesis id="H_01">The migration is complete.</Hypothesis>'
        '<Evidence id="E_01" for="H_01" polarity="supports">Observed.</Evidence>'
        '<Finding id="F_01" for_hyp="H_01" status="met">Satisfied.</Finding>'
    )


def test_v04_goal_finding_trace_stays_valid_without_new_warnings():
    xml = _wrap(
        '<Goal id="G_01" priority="required">Legacy close.</Goal>'
        '<Finding id="F_01" for_goal="G_01" status="met">Done.</Finding>'
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = validate(parse(xml))
    assert caught == []
    assert result.ok
    assert result.errors == []
    assert result.warnings == []


def test_valid_concluding_closes_required_goal():
    xml = _wrap(
        '<Goal id="G_01" priority="required" criticality="ledger">g</Goal>'
        + _supporting_chain()
        + '<Concluding id="C_01" for_goal="G_01" criticality="ledger" '
        + 'confidence="0.8">REFER:F_01 closes.</Concluding>'
    )
    result = validate(parse(xml))
    assert result.ok
    assert result.errors == []
    assert result.warnings == []


def test_parser_rejects_concluding_without_for_goal():
    with pytest.raises(ScholiaParseError, match="for_goal"):
        parse(_wrap('<Concluding id="C_01">REFER:F_01 closes.</Concluding>'))


def test_for_goal_resolves_requires_goal_target():
    xml = _wrap(
        '<Goal id="G_01" priority="required">g</Goal>'
        + _supporting_chain()
        + '<Concluding id="C_01" for_goal="H_01">REFER:F_01 closes.</Concluding>'
    )
    result = validate(parse(xml))
    errors = result.errors_by_rule[RULE_FOR_GOAL_RESOLVES]
    assert len(errors) == 1
    assert "Hypothesis" in errors[0].message


def test_refer_at_least_one_requires_valid_citation():
    xml = _wrap(
        '<Goal id="G_01" priority="required">g</Goal>'
        '<Concluding id="C_01" for_goal="G_01">Pure prose.</Concluding>'
    )
    result = validate(parse(xml))
    errors = result.errors_by_rule[RULE_REFER_AT_LEAST_ONE]
    assert len(errors) == 1
    assert errors[0].atom_id == "C_01"


def test_criticality_non_decreasing_rejects_silent_downgrade():
    xml = _wrap(
        '<Goal id="G_01" priority="required" criticality="kernel">g</Goal>'
        + _supporting_chain()
        + '<Concluding id="C_01" for_goal="G_01" criticality="bridge">'
        + "REFER:F_01 closes.</Concluding>"
    )
    result = validate(parse(xml))
    errors = result.errors_by_rule[RULE_CRITICALITY_NON_DECREASING]
    assert len(errors) == 1
    assert "kernel" in errors[0].message


def test_retract_authorizes_criticality_downgrade():
    xml = _wrap(
        '<Goal id="G_01" priority="required" criticality="kernel">g</Goal>'
        + _supporting_chain()
        + '<Retract id="R_01" target="G_01" reason="downgrade approved">ok</Retract>'
        + '<Concluding id="C_01" for_goal="G_01" criticality="bridge">'
        + "REFER:F_01 closes.</Concluding>"
    )
    result = validate(parse(xml))
    assert result.errors_by_rule[RULE_CRITICALITY_NON_DECREASING] == []


def test_no_action_in_concluding_is_warning_only():
    xml = _wrap(
        '<Goal id="G_01" priority="required">g</Goal>'
        + _supporting_chain()
        + '<Concluding id="C_01" for_goal="G_01">'
        + "REFER:F_01 says we should ship.</Concluding>"
    )
    result = validate(parse(xml))
    warnings_for_rule = result.warnings_by_rule[RULE_NO_ACTION_IN_CONCLUDING]
    assert result.ok
    assert len(warnings_for_rule) == 1
    assert warnings_for_rule[0].atom_id == "C_01"


def test_single_active_concluding_per_goal_warns_on_duplicates():
    xml = _wrap(
        '<Goal id="G_01" priority="required">g</Goal>'
        + _supporting_chain()
        + '<Concluding id="C_01" for_goal="G_01">REFER:F_01 first.</Concluding>'
        + '<Concluding id="C_02" for_goal="G_01">REFER:F_01 second.</Concluding>'
    )
    result = validate(parse(xml))
    warnings_for_rule = result.warnings_by_rule[
        RULE_SINGLE_ACTIVE_CONCLUDING_PER_GOAL
    ]
    assert result.ok
    assert {warning.atom_id for warning in warnings_for_rule} == {"C_01", "C_02"}


def test_min_confidence_ceiling_warns_on_overreach():
    xml = _wrap(
        '<Goal id="G_01" priority="required">g</Goal>'
        + _supporting_chain()
        + '<Uncertainty id="U_01" on="F_01" confidence="0.6">weak</Uncertainty>'
        + '<Concluding id="C_01" for_goal="G_01" confidence="0.95">'
        + "REFER:F_01 closes.</Concluding>"
    )
    result = validate(parse(xml))
    warnings_for_rule = result.warnings_by_rule[RULE_MIN_CONFIDENCE_CEILING]
    assert result.ok
    assert len(warnings_for_rule) == 1
    assert "0.6" in warnings_for_rule[0].message
