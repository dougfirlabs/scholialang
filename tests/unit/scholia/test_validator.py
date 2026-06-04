"""Tests for scholialang.validator — the 7 validity rules."""
from __future__ import annotations

from pathlib import Path
import time

from scholialang.atoms import (
    Action,
    Atom,
    Concluding,
    Constraint,
    Deciding,
    Evidence,
    Finding,
    Goal,
    Hypothesis,
    Retract,
    Step,
    Thinking,
    Uncertainty,
)
from scholialang.parser import parse
from scholialang.validator import (
    RULE_ACTION_RECORDED,
    RULE_CONSTRAINT_RESPECTED,
    RULE_DECISION_CLOSED,
    RULE_GOAL_DECLARED,
    RULE_HYPOTHESIS_EVALUATED,
    RULE_REFERENCE_COMPLETE,
    RULE_RETRACT_CONSISTENT,
    RULE_WELL_FORMED,
    check_action_recorded,
    check_constraint_respected,
    check_decision_closed,
    check_goal_declared,
    check_hypothesis_evaluated,
    check_reference_complete,
    check_retract_consistent,
    check_well_formed,
    validate,
)


def _idx(trace):
    from scholialang.validator import _build_id_index  # type: ignore

    return _build_id_index(trace)


# ── Rule 1: well-formedness ──────────────────────────────────────────


def test_well_formed_pass():
    trace = [Step(id="S", atoms=[Thinking(id="T", content="x")])]
    assert check_well_formed(trace, _idx(trace)) == []


def test_well_formed_fail_bad_kind():
    bad = Atom(id="X")  # base Atom — kind is "Atom" (not in catalog)
    trace = [Step(id="S", atoms=[bad])]
    errs = check_well_formed(trace, _idx(trace))
    assert errs and all(e.rule == RULE_WELL_FORMED for e in errs)


# ── Rule 2: reference completeness ───────────────────────────────────


def test_reference_complete_pass():
    t = Thinking(id="T", content="REFER:F_01")
    t.operators = ["REFER:F_01"]
    trace = [Step(id="S", atoms=[t, Finding(id="F_01")])]
    assert check_reference_complete(trace, _idx(trace)) == []


def test_reference_complete_fail_dangling_refer():
    t = Thinking(id="T", content="REFER:MissingAtom")
    t.operators = ["REFER:MissingAtom"]
    trace = [Step(id="S", atoms=[t])]
    errs = check_reference_complete(trace, _idx(trace))
    assert errs and errs[0].rule == RULE_REFERENCE_COMPLETE


def test_reference_complete_resolves_to_step_id():
    t = Thinking(id="T", content="REFER:Step_03")
    t.operators = ["REFER:Step_03"]
    trace = [
        Step(id="Step_03", atoms=[Thinking(id="T2")]),
        Step(id="Step_04", atoms=[t]),
    ]
    assert check_reference_complete(trace, _idx(trace)) == []


# ── Rule 3: decision closure ─────────────────────────────────────────


def test_decision_closed_pass():
    d = Deciding(id="D", children=[Finding(id="F")])
    trace = [Step(id="S", atoms=[d])]
    assert check_decision_closed(trace, _idx(trace)) == []


def test_decision_closed_fail():
    d = Deciding(id="D", children=[Thinking(content="x")])
    trace = [Step(id="S", atoms=[d])]
    errs = check_decision_closed(trace, _idx(trace))
    assert errs and errs[0].rule == RULE_DECISION_CLOSED


# ── Rule 4: action recorded ──────────────────────────────────────────


def test_action_recorded_pass_nested():
    a = Action(id="A", children=[Finding(id="F")])
    trace = [Step(id="S", atoms=[a])]
    assert check_action_recorded(trace, _idx(trace)) == []


def test_action_recorded_pass_sibling():
    a = Action(id="A")
    f = Finding(id="F")
    trace = [Step(id="S", atoms=[a, f])]
    assert check_action_recorded(trace, _idx(trace)) == []


def test_action_recorded_fail():
    a = Action(id="A")
    trace = [Step(id="S", atoms=[a])]
    errs = check_action_recorded(trace, _idx(trace))
    assert errs and errs[0].rule == RULE_ACTION_RECORDED


# ── Rule 5: hypothesis evaluated ─────────────────────────────────────


def test_hypothesis_evaluated_pass_with_evidence():
    h = Hypothesis(id="H_01")
    e = Evidence(id="E_01", for_ref="H_01", polarity="supports")
    trace = [Step(id="S", atoms=[h, e])]
    assert check_hypothesis_evaluated(trace, _idx(trace)) == []


def test_hypothesis_evaluated_pass_with_uncertainty():
    h = Hypothesis(id="H_01")
    u = Uncertainty(id="U_01", on="H_01", confidence="0.5")
    trace = [Step(id="S", atoms=[h, u])]
    assert check_hypothesis_evaluated(trace, _idx(trace)) == []


def test_hypothesis_evaluated_fail_dangling():
    h = Hypothesis(id="H_02")
    trace = [Step(id="S", atoms=[h])]
    errs = check_hypothesis_evaluated(trace, _idx(trace))
    assert errs and errs[0].rule == RULE_HYPOTHESIS_EVALUATED


# ── Rule 6: retract consistent ───────────────────────────────────────


def test_retract_consistent_pass():
    f = Finding(id="F_01")
    r = Retract(id="R_01", target="F_01", reason="x")
    trace = [Step(id="S", atoms=[f, r])]
    assert check_retract_consistent(trace, _idx(trace)) == []


def test_retract_consistent_fail_no_target():
    r = Retract(id="R_01")  # no target
    trace = [Step(id="S", atoms=[r])]
    errs = check_retract_consistent(trace, _idx(trace))
    assert errs and errs[0].rule == RULE_RETRACT_CONSISTENT


def test_retract_consistent_fail_target_not_finding():
    h = Hypothesis(id="H_01")
    r = Retract(id="R_01", target="H_01", reason="oops")
    trace = [Step(id="S", atoms=[h, r])]
    errs = check_retract_consistent(trace, _idx(trace))
    assert errs and errs[0].rule == RULE_RETRACT_CONSISTENT


def test_retract_consistent_pass_goal_and_concluding_targets():
    g = Goal(id="G_01")
    c = Concluding(id="C_01", for_goal="G_01")
    trace = [
        Step(
            id="S",
            atoms=[
                g,
                c,
                Retract(id="R_01", target="G_01", reason="downgrade"),
                Retract(id="R_02", target="C_01", reason="superseded"),
            ],
        )
    ]
    assert check_retract_consistent(trace, _idx(trace)) == []


def test_retract_consistent_fail_missing_target():
    r = Retract(id="R_01", target="F_nope", reason="x")
    trace = [Step(id="S", atoms=[r])]
    errs = check_retract_consistent(trace, _idx(trace))
    assert errs and errs[0].rule == RULE_RETRACT_CONSISTENT


# ── Rule 7: constraint respected ─────────────────────────────────────


def test_constraint_respected_pass():
    c = Constraint(id="C_01", content="Never push to main.")
    a = Action(id="A_01", content="Create a branch and commit.",
               children=[Finding(id="F_01")])
    trace = [Step(id="S", atoms=[c, a])]
    assert check_constraint_respected(trace, _idx(trace)) == []


def test_constraint_respected_fail():
    c = Constraint(id="C_01", content="Never push to main without review.")
    a = Action(
        id="A_01",
        content="Going to push to main now — fast path.",
        children=[Finding(id="F_01")],
    )
    trace = [Step(id="S", atoms=[c, a])]
    errs = check_constraint_respected(trace, _idx(trace))
    assert errs and errs[0].rule == RULE_CONSTRAINT_RESPECTED


# ── Rule 8: goal declared ────────────────────────────────────────────


def test_goal_declared_pass_with_required_goal_status_finding():
    trace = [
        Step(
            id="S",
            atoms=[
                Goal(id="G_01", priority="required"),
                Finding.from_legacy(
                    {"id": "F_01", "for_goal": "G_01", "status": "met"}
                ),
            ],
        )
    ]
    assert check_goal_declared(trace, _idx(trace)) == []


def test_goal_declared_ignores_optional_goal():
    trace = [Step(id="S", atoms=[Goal(id="G_01", priority="optional")])]
    assert check_goal_declared(trace, _idx(trace)) == []


def test_goal_declared_backcompat_no_goals_passes():
    trace = [Step(id="S", atoms=[Finding(id="F_01")])]
    assert check_goal_declared(trace, _idx(trace)) == []


def test_goal_declared_fail_missing_status_finding():
    trace = [Step(id="S", atoms=[Goal(id="G_01", priority="required")])]
    errs = check_goal_declared(trace, _idx(trace))
    assert errs and errs[0].rule == RULE_GOAL_DECLARED


def test_goal_declared_fail_status_finding_missing_status():
    trace = [
        Step(
            id="S",
            atoms=[
                Goal(id="G_01", priority="required"),
                Finding.from_legacy({"id": "F_01", "for_goal": "G_01"}),
            ],
        )
    ]
    errs = check_goal_declared(trace, _idx(trace))
    assert errs and errs[0].rule == RULE_GOAL_DECLARED


def test_goal_declared_research_mode_exempts_trace():
    trace = parse(
        '<Step id="S"><Meta:research-mode/>'
        '<Goal id="G_01" priority="required"/></Step>'
    )
    assert check_goal_declared(trace, _idx(trace)) == []


def test_goal_declared_partially_met_status_passes():
    trace = [
        Step(
            id="S",
            atoms=[
                Goal(id="G_01", priority="required"),
                Finding(
                    id="F_01",
                    for_hyp="G_01",
                    status="partially_met",
                    content="one criterion remains",
                ),
            ],
        )
    ]
    assert check_goal_declared(trace, _idx(trace)) == []


def test_goal_declared_required_goal_without_id_fails():
    trace = [Step(id="S", atoms=[Goal(priority="required")])]
    errs = check_goal_declared(trace, _idx(trace))
    assert errs and "id" in errs[0].message


def test_goal_reference_integrity_checks_for_goal_and_related_constraints():
    trace = [
        Step(
            id="S",
            atoms=[
                Goal(id="G_01", related_constraints=["C_missing"]),
                Finding.from_legacy(
                    {"id": "F_01", "for_goal": "G_missing", "status": "met"}
                ),
            ],
        )
    ]
    errs = check_reference_complete(trace, _idx(trace))
    assert len(errs) == 2


def test_v02_reference_integrity_checks_eventref_budget_cost():
    trace = parse(
        '<Step id="S"><EventRef for="Missing" sequence="1" '
        'wall_clock="2026-04-21T12:00:00-07:00"/>'
        '<Budget for="AlsoMissing" tokens="1"/>'
        '<Cost for="Nope" tokens="1"/></Step>'
    )
    errs = check_reference_complete(trace, _idx(trace))
    assert len(errs) == 3


def test_research_mode_pseudo_atom_is_well_formed():
    trace = parse("<Step id='S'><Meta:research-mode/></Step>")
    assert check_well_formed(trace, _idx(trace)) == []


def test_committed_fixture_parses_and_validates():
    repo_root = Path(__file__).resolve().parents[3]
    path = repo_root / "tests/fixtures/scholia/v03_known_corpus/simple_goal_finding.xml"
    trace = parse(path.read_text())
    result = validate(trace)
    assert result.ok, result.errors


# ── Full validate() orchestration ────────────────────────────────────


def test_validate_happy_path_returns_ok():
    text = (
        '<Step id="S">'
        '<Hypothesis id="H_01">hyp</Hypothesis>'
        '<Evidence for="H_01" polarity="supports">ev</Evidence>'
        '<Finding id="F_01">concl</Finding>'
        "</Step>"
    )
    trace = parse(text)
    result = validate(trace)
    assert result.ok, result.errors


def test_validate_groups_errors_by_rule():
    h = Hypothesis(id="H_bare")  # violates hypothesis_evaluated
    d = Deciding(id="D_bare")  # violates decision_closed
    trace = [Step(id="S", atoms=[h, d])]
    result = validate(trace)
    assert not result.ok
    assert result.errors_by_rule[RULE_HYPOTHESIS_EVALUATED]
    assert result.errors_by_rule[RULE_DECISION_CLOSED]
    assert result.errors_by_rule[RULE_WELL_FORMED] == []


def test_validate_100_step_trace_under_50ms():
    # Performance check — PRD says < 50ms for 100 steps.
    steps = []
    for i in range(100):
        steps.append(
            Step(
                id=f"S_{i:03d}",
                atoms=[
                    Hypothesis(id=f"H_{i:03d}"),
                    Evidence(
                        id=f"E_{i:03d}",
                        for_ref=f"H_{i:03d}",
                        polarity="supports",
                    ),
                    Finding(id=f"F_{i:03d}", content="conc"),
                ],
            )
        )
    start = time.perf_counter()
    result = validate(steps)
    elapsed = time.perf_counter() - start
    assert result.ok, result.errors[:3]
    # Allow generous 200ms margin — the spec target is 50ms on a
    # typical developer machine; CI runners vary.
    assert elapsed < 0.2, f"validate took {elapsed*1000:.1f}ms"


def test_validation_summary_present_on_failure():
    h = Hypothesis(id="H")
    trace = [Step(id="S", atoms=[h])]
    result = validate(trace)
    assert "violation" in result.summary()


# ── Rule 8 (v0.3): operator-known / closed-set check ─────────────────


def _import_rule_unknown_operator():
    from scholialang.validator import (  # type: ignore
        RULE_UNKNOWN_OPERATOR,
        check_unknown_operator,
    )

    return RULE_UNKNOWN_OPERATOR, check_unknown_operator


def test_unknown_operator_rejects_maybe():
    RULE_UNKNOWN_OPERATOR, check_unknown_operator = _import_rule_unknown_operator()
    t = Thinking(id="T", content="MAYBE:Obs_22 was wrong")
    trace = [Step(id="S", atoms=[t])]
    errs = check_unknown_operator(trace, _idx(trace))
    assert errs and errs[0].rule == RULE_UNKNOWN_OPERATOR
    assert "MAYBE" in errs[0].message
    assert "REFER" in errs[0].message  # canonical set named in message


def test_unknown_operator_accepts_canonical_trio():
    _, check_unknown_operator = _import_rule_unknown_operator()
    t1 = Thinking(id="T1", content="REFER:F_01 then IMPLIES:F_02")
    t2 = Finding(id="F_01", content="NOT:F_02 — refuted")
    f2 = Finding(id="F_02", content="prior")
    trace = [Step(id="S", atoms=[t1, t2, f2])]
    assert check_unknown_operator(trace, _idx(trace)) == []


def test_unknown_operator_dedupes_per_atom_per_op():
    _, check_unknown_operator = _import_rule_unknown_operator()
    t = Thinking(
        id="T",
        content="MAYBE:Obs_01 then MAYBE:Obs_02 also MAYBE:Obs_03",
    )
    trace = [Step(id="S", atoms=[t])]
    errs = check_unknown_operator(trace, _idx(trace))
    # One error per (atom, op) pair regardless of repetitions.
    assert len(errs) == 1


# ── NOT operator faithfulness extension ──────────────────────────────


def test_not_operator_faithfulness_pass():
    f = Finding(id="F_01", content="NOT:H_01 — refuted")
    f.operators = ["NOT:H_01"]
    h = Hypothesis(id="H_01")
    trace = [Step(id="S", atoms=[h, f])]
    assert check_reference_complete(trace, _idx(trace)) == []


def test_not_operator_faithfulness_fail_dangling():
    f = Finding(id="F_01", content="NOT:H_999 — bogus target")
    f.operators = ["NOT:H_999"]
    trace = [Step(id="S", atoms=[f])]
    errs = check_reference_complete(trace, _idx(trace))
    assert errs and errs[0].rule == RULE_REFERENCE_COMPLETE
    assert "NOT:H_999" in errs[0].message


def test_validate_groups_unknown_operator_errors():
    from scholialang.validator import RULE_UNKNOWN_OPERATOR  # type: ignore

    t = Thinking(id="T", content="MAYBE:Obs_22 emerged")
    trace = [Step(id="S", atoms=[t])]
    result = validate(trace)
    assert not result.ok
    assert result.errors_by_rule[RULE_UNKNOWN_OPERATOR]
