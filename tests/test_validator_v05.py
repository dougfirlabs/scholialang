"""Scholia v0.5 validator tests — six new rules + back-compat.

Coverage map (PRD ``rsi-scholia-v0.5-02-validator-rules``):

- Hard-fail rules: ``for_goal_resolves``, ``refer_at_least_one``,
  ``criticality_non_decreasing``. Three positive + three negative
  per rule.
- Warning rules: ``no_action_in_concluding``,
  ``single_active_concluding_per_goal``, ``min_confidence_ceiling``.
  Three positive + three negative per rule.
- Mixed-rule fixtures (six XML files under
  ``scholialang/tests/fixtures/validator/``) exercising 2..3+ rules
  in a single trace.
- v04-backcompat fixture asserting pre-v0.5 traces emit zero
  errors/warnings from the new rules.

Acceptance criteria check:

- ``pytest scholialang/tests/test_validator_v05.py`` exits 0.
- All six rules covered with positive + negative cases.
- Backcompat fixture: 0 errors, 0 warnings.
- Mixed fixtures exercise 2-3+ rules in a single trace.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scholialang.atoms import parse_trace
from scholialang.validator import (
    RULE_CRITICALITY_NON_DECREASING,
    RULE_FOR_GOAL_RESOLVES,
    RULE_MIN_CONFIDENCE_CEILING,
    RULE_NO_ACTION_IN_CONCLUDING,
    RULE_REFER_AT_LEAST_ONE,
    RULE_SINGLE_ACTIVE_CONCLUDING_PER_GOAL,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    validate,
)


_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "validator"


def _load(name: str) -> str:
    return (_FIXTURE_DIR / name).read_text()


def _wrap(inner: str) -> str:
    """Wrap inline atoms in a ``<Trace><Step>`` skeleton."""
    return (
        "<Trace><Step id='step_01' name='inline test'>"
        + inner
        + "</Step></Trace>"
    )


def _rule_errors(report: dict, rule: str) -> list[dict]:
    return [e for e in report["errors"] if e["rule"] == rule]


def _rule_warnings(report: dict, rule: str) -> list[dict]:
    return [w for w in report["warnings"] if w["rule"] == rule]


# ── Backwards compatibility ──────────────────────────────────────────


def test_v04_backcompat_fixture_returns_no_violations() -> None:
    trace = parse_trace(_load("v04_backcompat.xml"))
    report = validate(trace)
    assert report == {"errors": [], "warnings": []}


def test_empty_trace_returns_no_violations() -> None:
    report = validate([])
    assert report == {"errors": [], "warnings": []}


def test_trace_without_concluding_returns_no_violations() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>A goal.</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>"
        "Closes a hypothesis.</Finding>"
    )
    report = validate(parse_trace(xml))
    assert report == {"errors": [], "warnings": []}


# ── Rule 1 — for_goal_resolves (HARD-FAIL) ───────────────────────────


def test_for_goal_resolves_positive_valid_goal_target() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>REFER:F_01 closes.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_errors(report, RULE_FOR_GOAL_RESOLVES) == []


def test_for_goal_resolves_positive_multiple_concludings_all_resolve() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g1</Goal>"
        "<Goal id='G_02' priority='optional'>g2</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>REFER:F_01.</Concluding>"
        "<Concluding id='C_02' for_goal='G_02'>REFER:F_01.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_errors(report, RULE_FOR_GOAL_RESOLVES) == []


def test_for_goal_resolves_positive_goal_in_separate_step() -> None:
    xml = (
        "<Trace>"
        "<Step id='s1' name='setup'>"
        "<Goal id='G_99' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "</Step>"
        "<Step id='s2' name='close'>"
        "<Concluding id='C_01' for_goal='G_99'>REFER:F_01.</Concluding>"
        "</Step>"
        "</Trace>"
    )
    report = validate(parse_trace(xml))
    assert _rule_errors(report, RULE_FOR_GOAL_RESOLVES) == []


def test_for_goal_resolves_negative_missing_goal_id() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_missing'>REFER:F_01.</Concluding>"
    )
    report = validate(parse_trace(xml))
    errs = _rule_errors(report, RULE_FOR_GOAL_RESOLVES)
    assert len(errs) == 1
    assert errs[0]["atom_id"] == "C_01"
    assert errs[0]["severity"] == SEVERITY_ERROR
    assert "G_missing" in errs[0]["message"]


def test_for_goal_resolves_negative_target_is_hypothesis_not_goal() -> None:
    xml = _wrap(
        "<Hypothesis id='H_01'>not a goal</Hypothesis>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='H_01'>REFER:F_01.</Concluding>"
    )
    report = validate(parse_trace(xml))
    errs = _rule_errors(report, RULE_FOR_GOAL_RESOLVES)
    assert len(errs) == 1
    assert "Hypothesis" in errs[0]["message"]


def test_for_goal_resolves_negative_mixed_resolved_and_dangling() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>REFER:F_01.</Concluding>"
        "<Concluding id='C_02' for_goal='G_dangling'>REFER:F_01.</Concluding>"
    )
    report = validate(parse_trace(xml))
    errs = _rule_errors(report, RULE_FOR_GOAL_RESOLVES)
    assert len(errs) == 1
    assert errs[0]["atom_id"] == "C_02"


# ── Rule 2 — refer_at_least_one (HARD-FAIL) ──────────────────────────


def test_refer_at_least_one_positive_finding_cited() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>REFER:F_01 closes.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_errors(report, RULE_REFER_AT_LEAST_ONE) == []


def test_refer_at_least_one_positive_observation_cited() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Observation id='O_01'>An observation.</Observation>"
        "<Concluding id='C_01' for_goal='G_01'>REFER:O_01 closes.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_errors(report, RULE_REFER_AT_LEAST_ONE) == []


def test_refer_at_least_one_positive_evidence_cited() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Hypothesis id='H_01'>h</Hypothesis>"
        "<Evidence id='E_01' for='H_01' polarity='supports'>e</Evidence>"
        "<Concluding id='C_01' for_goal='G_01'>"
        "REFER:E_01 — evidence backs the close.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_errors(report, RULE_REFER_AT_LEAST_ONE) == []


def test_refer_at_least_one_negative_no_refer_at_all() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Concluding id='C_01' for_goal='G_01'>"
        "Pure prose with no REFER token whatsoever.</Concluding>"
    )
    report = validate(parse_trace(xml))
    errs = _rule_errors(report, RULE_REFER_AT_LEAST_ONE)
    assert len(errs) == 1
    assert errs[0]["atom_id"] == "C_01"
    assert errs[0]["severity"] == SEVERITY_ERROR


def test_refer_at_least_one_negative_refer_only_to_hypothesis() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Hypothesis id='H_01'>h</Hypothesis>"
        "<Concluding id='C_01' for_goal='G_01'>"
        "REFER:H_01 — only points at a Hypothesis, no Finding/Obs/Ev.</Concluding>"
    )
    report = validate(parse_trace(xml))
    errs = _rule_errors(report, RULE_REFER_AT_LEAST_ONE)
    assert len(errs) == 1


def test_refer_at_least_one_negative_refer_to_unresolvable_id() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Concluding id='C_01' for_goal='G_01'>"
        "REFER:F_does_not_exist — dangling reference, no valid citation.</Concluding>"
    )
    report = validate(parse_trace(xml))
    errs = _rule_errors(report, RULE_REFER_AT_LEAST_ONE)
    assert len(errs) == 1


# ── Rule 3 — criticality_non_decreasing (HARD-FAIL) ──────────────────


def test_criticality_non_decreasing_positive_matching_tier() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required' criticality='kernel'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01' criticality='kernel'>"
        "REFER:F_01 closes the kernel chain.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_errors(report, RULE_CRITICALITY_NON_DECREASING) == []


def test_criticality_non_decreasing_positive_elevation_above_chain_max() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required' criticality='bridge'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01' criticality='kernel'>"
        "REFER:F_01 — elevation to kernel after a systemic concern surfaced.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_errors(report, RULE_CRITICALITY_NON_DECREASING) == []


def test_criticality_non_decreasing_positive_retract_authorizes_downgrade() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required' criticality='kernel'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Retract id='R_01' target='G_01' reason='criticality reclassified'>"
        "Downgrade authorized.</Retract>"
        "<Concluding id='C_01' for_goal='G_01' criticality='bridge'>"
        "REFER:F_01 — bridge-class close after reclassification.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_errors(report, RULE_CRITICALITY_NON_DECREASING) == []


def test_criticality_non_decreasing_positive_goal_without_criticality_is_vacuous() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01' criticality='incidental'>"
        "REFER:F_01 closes.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_errors(report, RULE_CRITICALITY_NON_DECREASING) == []


def test_criticality_non_decreasing_negative_silent_downgrade_kernel_to_bridge() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required' criticality='kernel'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01' criticality='bridge'>"
        "REFER:F_01 — silent downgrade without Retract.</Concluding>"
    )
    report = validate(parse_trace(xml))
    errs = _rule_errors(report, RULE_CRITICALITY_NON_DECREASING)
    assert len(errs) == 1
    assert errs[0]["severity"] == SEVERITY_ERROR
    assert "bridge" in errs[0]["message"] and "kernel" in errs[0]["message"]


def test_criticality_non_decreasing_negative_verifier_to_incidental_drop() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required' criticality='verifier'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01' criticality='incidental'>"
        "REFER:F_01 — large multi-tier drop.</Concluding>"
    )
    report = validate(parse_trace(xml))
    errs = _rule_errors(report, RULE_CRITICALITY_NON_DECREASING)
    assert len(errs) == 1


def test_criticality_non_decreasing_negative_effective_from_chain_too_low() -> None:
    """Concluding has no declared criticality; effective = max of cited atoms.

    Cited Finding carries criticality='bridge' via attached Meta atom;
    Goal is at 'kernel'. Effective bridge < kernel → error.
    """
    xml = _wrap(
        "<Goal id='G_01' priority='required' criticality='kernel'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>"
        "f<Meta criticality='bridge'>Bridge-class finding.</Meta>"
        "</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>"
        "REFER:F_01 — Concluding inherits bridge from the cited chain.</Concluding>"
    )
    report = validate(parse_trace(xml))
    errs = _rule_errors(report, RULE_CRITICALITY_NON_DECREASING)
    assert len(errs) == 1


# ── Rule 4 — no_action_in_concluding (WARNING) ───────────────────────


def test_no_action_in_concluding_positive_pure_epistemic_prose() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>"
        "REFER:F_01 — the chain closes; the goal is met.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_warnings(report, RULE_NO_ACTION_IN_CONCLUDING) == []


def test_no_action_in_concluding_positive_states_observation_only() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>"
        "REFER:F_01 confirms the hypothesis; closure is established.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_warnings(report, RULE_NO_ACTION_IN_CONCLUDING) == []


def test_no_action_in_concluding_positive_declarative_close() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>"
        "Given REFER:F_01, the system is in a known-good state.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_warnings(report, RULE_NO_ACTION_IN_CONCLUDING) == []


def test_no_action_in_concluding_negative_should_modal() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>"
        "REFER:F_01 — we should ship this immediately.</Concluding>"
    )
    report = validate(parse_trace(xml))
    warns = _rule_warnings(report, RULE_NO_ACTION_IN_CONCLUDING)
    assert len(warns) == 1
    assert warns[0]["severity"] == SEVERITY_WARNING


def test_no_action_in_concluding_negative_will_modal() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>"
        "REFER:F_01 — I will refactor the module next.</Concluding>"
    )
    report = validate(parse_trace(xml))
    warns = _rule_warnings(report, RULE_NO_ACTION_IN_CONCLUDING)
    assert len(warns) == 1


def test_no_action_in_concluding_negative_recommend_modal() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>"
        "REFER:F_01 — recommend rolling forward.</Concluding>"
    )
    report = validate(parse_trace(xml))
    warns = _rule_warnings(report, RULE_NO_ACTION_IN_CONCLUDING)
    assert len(warns) == 1


# ── Rule 5 — single_active_concluding_per_goal (WARNING) ─────────────


def test_single_active_concluding_positive_one_per_goal() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>REFER:F_01.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_warnings(report, RULE_SINGLE_ACTIVE_CONCLUDING_PER_GOAL) == []


def test_single_active_concluding_positive_retract_retires_duplicate() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>"
        "REFER:F_01 — first attempt.</Concluding>"
        "<Retract id='R_01' target='C_01' reason='superseded'>"
        "Retract the first close.</Retract>"
        "<Concluding id='C_02' for_goal='G_01'>"
        "REFER:F_01 — revised close.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_warnings(report, RULE_SINGLE_ACTIVE_CONCLUDING_PER_GOAL) == []


def test_single_active_concluding_positive_one_each_across_goals() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g1</Goal>"
        "<Goal id='G_02' priority='optional'>g2</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>REFER:F_01.</Concluding>"
        "<Concluding id='C_02' for_goal='G_02'>REFER:F_01.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_warnings(report, RULE_SINGLE_ACTIVE_CONCLUDING_PER_GOAL) == []


def test_single_active_concluding_negative_two_active_for_same_goal() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>REFER:F_01 first.</Concluding>"
        "<Concluding id='C_02' for_goal='G_01'>REFER:F_01 second.</Concluding>"
    )
    report = validate(parse_trace(xml))
    warns = _rule_warnings(report, RULE_SINGLE_ACTIVE_CONCLUDING_PER_GOAL)
    # Both Concludings flagged so the operator can see which to retract.
    assert len(warns) == 2
    assert {w["atom_id"] for w in warns} == {"C_01", "C_02"}


def test_single_active_concluding_negative_three_active_for_same_goal() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>REFER:F_01.</Concluding>"
        "<Concluding id='C_02' for_goal='G_01'>REFER:F_01.</Concluding>"
        "<Concluding id='C_03' for_goal='G_01'>REFER:F_01.</Concluding>"
    )
    report = validate(parse_trace(xml))
    warns = _rule_warnings(report, RULE_SINGLE_ACTIVE_CONCLUDING_PER_GOAL)
    assert len(warns) == 3


def test_single_active_concluding_negative_only_one_goal_offending() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g1</Goal>"
        "<Goal id='G_02' priority='optional'>g2</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01'>REFER:F_01.</Concluding>"
        "<Concluding id='C_02' for_goal='G_02'>REFER:F_01.</Concluding>"
        "<Concluding id='C_03' for_goal='G_02'>REFER:F_01.</Concluding>"
    )
    report = validate(parse_trace(xml))
    warns = _rule_warnings(report, RULE_SINGLE_ACTIVE_CONCLUDING_PER_GOAL)
    assert len(warns) == 2
    assert {w["atom_id"] for w in warns} == {"C_02", "C_03"}


# ── Rule 6 — min_confidence_ceiling (WARNING) ────────────────────────


def test_min_confidence_ceiling_positive_concluding_below_min_via_uncertainty() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Uncertainty id='U_01' on='F_01' confidence='0.9'>partial.</Uncertainty>"
        "<Concluding id='C_01' for_goal='G_01' confidence='0.7'>"
        "REFER:F_01 — confidence stays under the cited 0.9 ceiling.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_warnings(report, RULE_MIN_CONFIDENCE_CEILING) == []


def test_min_confidence_ceiling_positive_concluding_at_exact_min() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Uncertainty id='U_01' on='F_01' confidence='0.8'>partial.</Uncertainty>"
        "<Concluding id='C_01' for_goal='G_01' confidence='0.8'>"
        "REFER:F_01 — confidence equals ceiling, allowed.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_warnings(report, RULE_MIN_CONFIDENCE_CEILING) == []


def test_min_confidence_ceiling_positive_no_cited_confidences_is_vacuous() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Concluding id='C_01' for_goal='G_01' confidence='0.99'>"
        "REFER:F_01 — no confidence data on cited atoms, vacuous.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert _rule_warnings(report, RULE_MIN_CONFIDENCE_CEILING) == []


def test_min_confidence_ceiling_negative_concluding_above_min_via_uncertainty() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f</Finding>"
        "<Uncertainty id='U_01' on='F_01' confidence='0.6'>partial.</Uncertainty>"
        "<Concluding id='C_01' for_goal='G_01' confidence='0.95'>"
        "REFER:F_01 — confidence overreaches the 0.6 cited ceiling.</Concluding>"
    )
    report = validate(parse_trace(xml))
    warns = _rule_warnings(report, RULE_MIN_CONFIDENCE_CEILING)
    assert len(warns) == 1
    assert warns[0]["atom_id"] == "C_01"
    assert warns[0]["severity"] == SEVERITY_WARNING


def test_min_confidence_ceiling_negative_min_across_multiple_findings() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Finding id='F_01' for_hyp='H_01' status='met'>f1</Finding>"
        "<Finding id='F_02' for_hyp='H_01' status='met'>f2</Finding>"
        "<Finding id='F_03' for_hyp='H_01' status='met'>f3</Finding>"
        "<Uncertainty id='U_01' on='F_01' confidence='0.9'>partial.</Uncertainty>"
        "<Uncertainty id='U_02' on='F_02' confidence='0.7'>partial.</Uncertainty>"
        "<Uncertainty id='U_03' on='F_03' confidence='0.8'>partial.</Uncertainty>"
        "<Concluding id='C_01' for_goal='G_01' confidence='0.85'>"
        "REFER:F_01 REFER:F_02 REFER:F_03 — exceeds min 0.7.</Concluding>"
    )
    report = validate(parse_trace(xml))
    warns = _rule_warnings(report, RULE_MIN_CONFIDENCE_CEILING)
    assert len(warns) == 1


def test_min_confidence_ceiling_negative_via_confidence_atom() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Hypothesis id='H_01'>h</Hypothesis>"
        "<Evidence id='E_01' for='H_01' polarity='supports'>e</Evidence>"
        "<Confidence id='Cf_01' on='E_01' level='0.5'>weak signal.</Confidence>"
        "<Concluding id='C_01' for_goal='G_01' confidence='0.9'>"
        "REFER:E_01 — overreaches the Evidence's 0.5 confidence.</Concluding>"
    )
    report = validate(parse_trace(xml))
    warns = _rule_warnings(report, RULE_MIN_CONFIDENCE_CEILING)
    assert len(warns) == 1


# ── Mixed-rule fixture tests ─────────────────────────────────────────


@pytest.mark.parametrize(
    "fixture,expected_error_rules,expected_warning_rules",
    [
        # Mixed 1 — two hard-fails: one for_goal dangling, one no-REFER.
        (
            "mixed_two_hard_fails.xml",
            {RULE_FOR_GOAL_RESOLVES, RULE_REFER_AT_LEAST_ONE},
            set(),
        ),
        # Mixed 2 — criticality downgrade (error) + action-modal (warning).
        (
            "mixed_criticality_and_action.xml",
            {RULE_CRITICALITY_NON_DECREASING},
            {RULE_NO_ACTION_IN_CONCLUDING},
        ),
        # Mixed 3 — three warnings interacting on one Goal.
        (
            "mixed_three_warnings.xml",
            set(),
            {
                RULE_SINGLE_ACTIVE_CONCLUDING_PER_GOAL,
                RULE_NO_ACTION_IN_CONCLUDING,
                RULE_MIN_CONFIDENCE_CEILING,
            },
        ),
        # Mixed 4 — Retract bypass clears criticality + retires duplicate.
        ("mixed_retract_bypass.xml", set(), set()),
        # Mixed 5 — all three hard-fails on one Concluding.
        (
            "mixed_all_hard_fails.xml",
            {
                RULE_FOR_GOAL_RESOLVES,
                RULE_REFER_AT_LEAST_ONE,
                RULE_CRITICALITY_NON_DECREASING,
            },
            set(),
        ),
        # Mixed 6 — complex trace, multiple Goals, elevation, all clean.
        ("mixed_clean_complex.xml", set(), set()),
    ],
)
def test_mixed_rule_fixtures(
    fixture: str,
    expected_error_rules: set[str],
    expected_warning_rules: set[str],
) -> None:
    trace = parse_trace(_load(fixture))
    report = validate(trace)
    actual_error_rules = {e["rule"] for e in report["errors"]}
    actual_warning_rules = {w["rule"] for w in report["warnings"]}
    assert actual_error_rules == expected_error_rules, (
        f"{fixture}: errors={report['errors']}"
    )
    assert actual_warning_rules == expected_warning_rules, (
        f"{fixture}: warnings={report['warnings']}"
    )


# ── Report shape ─────────────────────────────────────────────────────


def test_report_shape_has_errors_and_warnings_keys() -> None:
    report = validate([])
    assert set(report.keys()) == {"errors", "warnings"}
    assert isinstance(report["errors"], list)
    assert isinstance(report["warnings"], list)


def test_violation_dict_has_required_fields() -> None:
    xml = _wrap(
        "<Goal id='G_01' priority='required'>g</Goal>"
        "<Concluding id='C_01' for_goal='G_missing'>"
        "REFER:F_01 — dangling for_goal.</Concluding>"
    )
    report = validate(parse_trace(xml))
    assert len(report["errors"]) >= 1
    err = report["errors"][0]
    assert set(err.keys()) == {"rule", "atom_id", "message", "severity"}
    assert err["severity"] == SEVERITY_ERROR
