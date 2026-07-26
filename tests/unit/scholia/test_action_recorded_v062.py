"""v0.6.2 conformance tests for recursive ``action_recorded`` closure."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from scholialang.atoms import (
    Action,
    Concluding,
    Evidence,
    Finding,
    Goal,
    Observation,
    Step,
    Thinking,
)
from scholialang.parser import parse
from scholialang.validator import (
    RULE_ACTION_RECORDED,
    check_action_recorded,
    validate,
)


def _idx(trace: list[Step]):
    from scholialang.validator import _build_id_index  # type: ignore

    return _build_id_index(trace)


def _result(result_kind):
    if result_kind is Concluding:
        return Concluding(id="Result_01", for_goal="G_01")
    return result_kind(id="Result_01")


@pytest.mark.parametrize("result_kind", [Finding, Concluding])
def test_nested_descendant_conclusion_records_action(result_kind):
    result = _result(result_kind)
    action = Action(
        id="Act_01",
        children=[Thinking(id="Think_01", children=[result])],
    )
    trace = [Step(id="S_01", atoms=[action])]

    assert check_action_recorded(trace, _idx(trace)) == []


@pytest.mark.parametrize("result_kind", [Finding, Concluding])
def test_immediate_conclusion_sibling_remains_backward_compatible(result_kind):
    trace = [
        Step(
            id="S_01",
            atoms=[Action(id="Act_01"), _result(result_kind)],
        )
    ]

    assert check_action_recorded(trace, _idx(trace)) == []


def test_later_cross_step_finding_directly_refers_to_action():
    trace = parse(
        """
        <Step id="S_01"><Action id="Act_01">apply patch</Action></Step>
        <Step id="S_02">
          <Observation id="Obs_01">tests ran</Observation>
        </Step>
        <Step id="S_03">
          <Finding id="F_01">tests passed REFER:Act_01</Finding>
        </Step>
        """
    )

    assert check_action_recorded(trace, _idx(trace)) == []


def test_adjacent_cross_step_finding_still_requires_explicit_link():
    trace = [
        Step(id="S_01", atoms=[Action(id="Act_01")]),
        Step(id="S_02", atoms=[Finding(id="F_01", content="order only")]),
    ]

    errors = check_action_recorded(trace, _idx(trace))

    assert len(errors) == 1
    assert errors[0].atom_id == "Act_01"


@pytest.mark.parametrize("source_kind", [Observation, Evidence])
def test_later_finding_accepts_one_hop_result_source(source_kind):
    source = source_kind(id="Source_01", content="output REFER:Act_01")
    finding = Finding(id="F_01", content="recorded REFER:Source_01")
    trace = [
        Step(id="S_01", atoms=[Action(id="Act_01")]),
        Step(id="S_02", atoms=[source]),
        Step(id="S_03", atoms=[finding]),
    ]

    assert check_action_recorded(trace, _idx(trace)) == []


def test_later_goal_closing_concluding_directly_refers_to_action():
    trace = [
        Step(
            id="S_01",
            atoms=[Goal(id="G_01"), Action(id="Act_01")],
        ),
        Step(id="S_02", atoms=[Observation(id="Obs_01")]),
        Step(
            id="S_03",
            atoms=[
                Concluding(
                    id="C_01",
                    for_goal="G_01",
                    content="goal met REFER:Act_01",
                )
            ],
        ),
    ]

    assert check_action_recorded(trace, _idx(trace)) == []


@dataclass
class _FixtureGraph:
    edges: tuple[tuple[str, str, str], ...]

    def has_edge(
        self,
        *,
        edge_type: str,
        source_id: str | None = None,
        target_id: str | None = None,
    ) -> bool:
        return any(
            relation == edge_type
            and (source_id is None or source == source_id)
            and (target_id is None or target == target_id)
            for source, target, relation in self.edges
        )


def test_records_result_graph_edge_records_action():
    trace = [
        Step(id="S_01", atoms=[Action(id="Act_01")]),
        Step(id="S_02", atoms=[Observation(id="Obs_01")]),
    ]
    graph = _FixtureGraph((("F_01", "Act_01", "records_result"),))

    assert check_action_recorded(trace, _idx(trace), graph) == []
    assert validate(trace).errors_by_rule[RULE_ACTION_RECORDED]
    assert validate(trace, graph=graph).errors_by_rule[RULE_ACTION_RECORDED] == []


def _concluding_without_goal() -> Concluding:
    concluding = Concluding(
        id="C_01",
        for_goal="G_placeholder",
        content="done REFER:Act_01",
    )
    concluding.for_goal = None
    return concluding


@pytest.mark.parametrize(
    ("later_atoms", "reason"),
    [
        (
            [
                Observation(id="Obs_01"),
                Finding(id="F_01", content="unrelated REFER:OtherAct"),
            ],
            "wrong Action target",
        ),
        (
            [Observation(id="Obs_01"), Finding(id="F_01", content="order only")],
            "chronological order alone",
        ),
        (
            [
                Observation(id="Obs_01"),
                Finding(id="F_01", content="REFER:Obs_01"),
            ],
            "source does not link to Action",
        ),
        (
            [
                Observation(id="Obs_01"),
                _concluding_without_goal(),
            ],
            "Concluding does not close a Goal",
        ),
        (
            [
                Observation(id="Obs_01", content="REFER:Act_01"),
                Concluding(
                    id="C_01",
                    for_goal="G_01",
                    content="done REFER:Obs_01",
                ),
            ],
            "Concluding only links indirectly",
        ),
    ],
)
def test_later_unqualified_result_does_not_record_action(later_atoms, reason):
    trace = [
        Step(id="S_01", atoms=[Action(id="Act_01")]),
        Step(id="S_02", atoms=later_atoms),
    ]

    errors = check_action_recorded(trace, _idx(trace))

    assert errors, reason
    assert errors[0].rule == RULE_ACTION_RECORDED
    assert errors[0].atom_id == "Act_01"


def test_result_before_action_does_not_record_action():
    trace = [
        Step(id="S_01", atoms=[Finding(id="F_01", content="REFER:Act_01")]),
        Step(id="S_02", atoms=[Action(id="Act_01")]),
    ]

    errors = check_action_recorded(trace, _idx(trace))

    assert len(errors) == 1
    assert errors[0].atom_id == "Act_01"


def test_linked_result_closes_only_its_target_action():
    trace = [
        Step(id="S_01", atoms=[Action(id="Act_01")]),
        Step(id="S_02", atoms=[Action(id="Act_02")]),
        Step(id="S_03", atoms=[Observation(id="Obs_01")]),
        Step(id="S_04", atoms=[Finding(id="F_01", content="REFER:Act_01")]),
    ]

    errors = check_action_recorded(trace, _idx(trace))

    assert [error.atom_id for error in errors] == ["Act_02"]


def test_action_without_id_cannot_be_closed_by_later_refer():
    trace = [
        Step(id="S_01", atoms=[Action()]),
        Step(id="S_02", atoms=[Observation(id="Obs_01")]),
        Step(id="S_03", atoms=[Finding(id="F_01", content="REFER:Act_01")]),
    ]

    errors = check_action_recorded(trace, _idx(trace))

    assert len(errors) == 1
    assert errors[0].atom_id == ""
