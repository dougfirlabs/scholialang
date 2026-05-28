"""Tests for scholialang.parser — XML-ish text → AST."""
from __future__ import annotations

import pytest

from scholialang.atoms import (
    Action,
    Alternative,
    Branch,
    Budget,
    Confidence,
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
    Storing,
    Thinking,
    Uncertainty,
)
from scholialang.parser import ScholiaParseError, parse, parse_atom


def test_parses_simple_step():
    text = '<Step id="S_01" name="hello"><Thinking>content</Thinking></Step>'
    steps = parse(text)
    assert len(steps) == 1
    step = steps[0]
    assert step.id == "S_01"
    assert step.name == "hello"
    assert len(step.atoms) == 1
    assert isinstance(step.atoms[0], Thinking)


def test_rejects_unknown_tag():
    text = '<Step id="S"><FooBar/></Step>'
    with pytest.raises(ScholiaParseError) as exc:
        parse(text)
    assert "FooBar" in str(exc.value)


def test_rejects_unknown_top_level_tag():
    with pytest.raises(ScholiaParseError):
        parse("<NotAnAtom/>")


def test_self_closing_storing():
    # Paren-argument form rewritten to attribute form by pre-pass.
    text = '<Step id="S"><Thinking><Storing(main_head="a7173208")/></Thinking></Step>'
    steps = parse(text)
    assert len(steps[0].atoms) == 1
    thinking = steps[0].atoms[0]
    assert len(thinking.children) == 1
    assert isinstance(thinking.children[0], Storing)


def test_self_closing_print():
    text = '<Step id="S"><Thinking><Print(value="Hi there")/></Thinking></Step>'
    steps = parse(text)
    printed = steps[0].atoms[0].children[0]
    assert isinstance(printed, Print)


def test_comments_stripped():
    text = '<Step id="S"><!-- ignore me --><Thinking>x</Thinking></Step>'
    steps = parse(text)
    assert len(steps[0].atoms) == 1
    assert steps[0].atoms[0].content == "x"


def test_inline_operators_extracted():
    text = (
        '<Step id="S"><Thinking>A REFER:Finding_03 IMPLIES:Observation_06</Thinking></Step>'
    )
    steps = parse(text)
    ops = steps[0].atoms[0].operators
    assert "REFER:Finding_03" in ops
    assert "IMPLIES:Observation_06" in ops


def test_inline_bare_operator_extracted():
    text = '<Step id="S"><Thinking>FORALL branch in LIST</Thinking></Step>'
    steps = parse(text)
    ops = steps[0].atoms[0].operators
    assert any(op.startswith("FORALL") for op in ops)


def test_evidence_attributes():
    text = (
        '<Step id="S"><Evidence for="H_01" polarity="supports">ev</Evidence></Step>'
    )
    steps = parse(text)
    ev = steps[0].atoms[0]
    assert isinstance(ev, Evidence)
    assert ev.for_ref == "H_01"
    assert ev.polarity == "supports"


def test_retract_attributes():
    text = (
        '<Step id="S"><Retract target="Finding_02" reason="contradicted"'
        ' replacement="Finding_04">x</Retract></Step>'
    )
    steps = parse(text)
    r = steps[0].atoms[0]
    assert isinstance(r, Retract)
    assert r.target == "Finding_02"
    assert r.reason == "contradicted"
    assert r.replacement == "Finding_04"


def test_deciding_with_options_in_prose():
    text = (
        '<Step id="S"><Deciding>'
        "options = LIST:\n"
        "  - Option A\n"
        "  - Option B\n"
        "  - Option C\n"
        '<Finding>chose A</Finding></Deciding></Step>'
    )
    steps = parse(text)
    d = steps[0].atoms[0]
    assert isinstance(d, Deciding)
    assert "Option A" in d.options
    assert "Option B" in d.options
    assert "Option C" in d.options
    assert any(isinstance(c, Finding) for c in d.children)


def test_nested_atoms():
    text = (
        '<Step id="S">'
        '<Observation><Thinking>nested</Thinking></Observation>'
        '</Step>'
    )
    steps = parse(text)
    outer = steps[0].atoms[0]
    assert isinstance(outer, Observation)
    assert len(outer.children) == 1
    assert isinstance(outer.children[0], Thinking)


def test_non_atom_children_absorbed_as_text():
    # <bash> is not an atom; the parser keeps it as serialized text
    # on the containing Observation's content.
    text = (
        '<Step id="S"><Observation><bash>git status</bash></Observation></Step>'
    )
    steps = parse(text)
    obs = steps[0].atoms[0]
    assert isinstance(obs, Observation)
    assert "git status" in obs.content


def test_bare_atom_implicit_step_wrap():
    # A bare atom (no <Step> wrapper) is wrapped in an implicit Step
    # so callers always see list[Step].
    text = '<Thinking>bare</Thinking>'
    steps = parse(text)
    assert len(steps) == 1
    assert len(steps[0].atoms) == 1
    assert isinstance(steps[0].atoms[0], Thinking)


def test_parse_atom_single():
    atom = parse_atom("<Hypothesis id='H_01'>x</Hypothesis>")
    assert isinstance(atom, Hypothesis)
    assert atom.id == "H_01"


def test_parse_atom_rejects_multiple():
    with pytest.raises(ScholiaParseError):
        parse_atom("<Thinking>a</Thinking><Finding>b</Finding>")


def test_parses_scholia_root_wrapper():
    text = (
        "<Scholia>"
        '<Step id="S_01"><Thinking>x</Thinking></Step>'
        '<Step id="S_02"><Finding>y</Finding></Step>'
        "</Scholia>"
    )
    steps = parse(text)
    assert [s.id for s in steps] == ["S_01", "S_02"]


def test_rejects_malformed_xml():
    with pytest.raises(ScholiaParseError):
        parse("<Step><Thinking>unclosed")


def test_loop_carries_over_and_as():
    text = (
        '<Step id="S"><Loop over="REFER:branches" as="branch">'
        "<Observation>x</Observation></Loop></Step>"
    )
    steps = parse(text)
    loop = steps[0].atoms[0]
    assert isinstance(loop, Loop)
    assert loop.over == "REFER:branches"
    assert loop.as_var == "branch"


def test_constraint_carries_scope():
    text = '<Step id="S"><Constraint id="C_01" scope="trace">rule</Constraint></Step>'
    steps = parse(text)
    c = steps[0].atoms[0]
    assert isinstance(c, Constraint)
    assert c.scope == "trace"


def test_review_carries_of_and_reviewer():
    text = (
        '<Step id="S"><Review of="Subj:F_01" reviewer="Monitor">'
        "<Finding>grade ok</Finding></Review></Step>"
    )
    steps = parse(text)
    r = steps[0].atoms[0]
    assert isinstance(r, Review)
    assert r.of == "Subj:F_01"
    assert r.reviewer == "Monitor"


def test_goal_parses_fields_from_attributes_and_body_lists():
    text = (
        '<Step id="S"><Goal id="G_01" scope="trace" priority="required">'
        "ship it\n"
        "success_criteria = LIST:\n"
        "  - Tests pass\n"
        "related_constraints = LIST:[REFER:C_01]\n"
        'deadline = "2026-04-21T12:00:00-07:00"\n'
        "failure_modes = LIST:\n"
        "  - Tests fail\n"
        "</Goal></Step>"
    )
    goal = parse(text)[0].atoms[0]
    assert isinstance(goal, Goal)
    assert goal.scope == "trace"
    assert goal.priority == "required"
    assert goal.success_criteria == ["Tests pass"]
    assert goal.related_constraints == ["C_01"]
    assert goal.deadline == "2026-04-21T12:00:00-07:00"
    assert goal.failure_modes == ["Tests fail"]


def test_timestamp_only_on_observation_and_action():
    ts = "2026-04-21T12:00:00-07:00"
    steps = parse(
        f'<Step id="S"><Observation timestamp="{ts}">o</Observation>'
        f'<Action timestamp="{ts}">a<Finding>done</Finding></Action></Step>'
    )
    assert isinstance(steps[0].atoms[0], Observation)
    assert steps[0].atoms[0].timestamp == ts
    assert isinstance(steps[0].atoms[1], Action)
    assert steps[0].atoms[1].timestamp == ts


def test_timestamp_rejects_other_atoms():
    with pytest.raises(ScholiaParseError) as exc:
        parse('<Step id="S"><Thinking timestamp="2026-04-21T12:00:00">x</Thinking></Step>')
    assert "timestamp is only valid" in str(exc.value)


def test_timestamp_rejects_non_iso_value():
    with pytest.raises(ScholiaParseError) as exc:
        parse('<Step id="S"><Observation timestamp="nope">x</Observation></Step>')
    assert "ISO-8601" in str(exc.value)


def test_eventref_parses_typed_fields():
    text = (
        '<Step id="S"><Observation id="O">x</Observation>'
        '<EventRef id="ER" instance="ot_A" run_id="run" sequence="7" '
        'for="O" wall_clock="2026-04-21T12:00:00-07:00"/></Step>'
    )
    ref = parse(text)[0].atoms[1]
    assert isinstance(ref, EventRef)
    assert ref.sequence == 7
    assert ref.for_ref == "O"


def test_cost_budget_parse_numeric_fields():
    text = (
        '<Step id="S"><Goal id="G">g</Goal>'
        '<Budget id="B" for="G" tokens="10" actions="2" wall_clock_ms="30"/>'
        '<Action id="A">x<Finding>done</Finding></Action>'
        '<Cost id="C" for="A" tokens="8" wall_clock_ms="25" dollars="0.12"/>'
        "</Step>"
    )
    atoms = parse(text)[0].atoms
    assert isinstance(atoms[1], Budget)
    assert atoms[1].tokens == 10
    assert isinstance(atoms[3], Cost)
    assert atoms[3].dollars == 0.12


def test_alternative_only_inside_deciding():
    text = (
        '<Step id="S"><Deciding id="D">'
        '<Alternative label="defer" rejected_because="blocks goal"/>'
        '<Finding>chose ship</Finding></Deciding></Step>'
    )
    alt = parse(text)[0].atoms[0].children[0]
    assert isinstance(alt, Alternative)
    assert alt.label == "defer"
    with pytest.raises(ScholiaParseError) as exc:
        parse('<Step id="S"><Alternative label="x"/></Step>')
    assert "only valid inside" in str(exc.value)


def test_deciding_short_form_desugars_to_full_ast():
    d = parse_atom(
        '<Deciding id="D" options="A, B" chose="A">because A is cheaper</Deciding>'
    )
    assert isinstance(d, Deciding)
    assert d.options == ["A", "B"]
    assert d.content == ""
    assert [c.label for c in d.children if isinstance(c, Branch)] == ["A", "B"]
    findings = [c for c in d.children if isinstance(c, Finding)]
    assert len(findings) == 1
    assert findings[0].content == "chose A: because A is cheaper"


def test_deciding_short_form_rejects_unknown_choice():
    with pytest.raises(ScholiaParseError) as exc:
        parse_atom('<Deciding options="A, B" chose="C">bad</Deciding>')
    assert "must match" in str(exc.value)


def test_research_mode_pseudo_atom_parses_without_catalog_membership():
    atom = parse_atom("<Meta:research-mode/>")
    assert atom.kind == "Meta:research-mode"
    from scholialang.atoms import ATOM_KINDS

    assert atom.kind not in ATOM_KINDS


# ── Regression — inline ```xml``` in observation content (2026-05-24) ─


def test_inline_xml_fence_marker_in_observation_text_does_not_blank_trace():
    """Observed: the atlas rewriter sometimes emits prose like
    ``parser extracts XML from Markdown ```xml``` blocks`` inside an
    Observation's content. Pre-fix, ``_extract_xml_fences`` saw the
    inline ``\\`\\`\\`xml`` substring, ran its fence-extraction loop,
    found no actual fenced blocks (just an incidental mention), and
    returned an empty string — silently nuking the trace. Parser
    returned 0 steps. The rewriter then retried + fell back to
    prose-only. The fix bypasses fence extraction when the input is
    raw XML (starts with ``<``) and falls back to the original text
    if extraction yields nothing.
    """
    text = (
        '<Step id="step_01">'
        '<Goal id="Goal_01" scope="trace" priority="required">x</Goal>'
        '<Observation id="Observation_01">parser extracts XML from '
        'Markdown ```xml``` blocks.</Observation>'
        '<Finding id="Finding_01" for_goal="Goal_01" status="met">y</Finding>'
        "</Step>"
    )
    trace = parse(text)
    assert len(trace) == 1
    assert len(trace[0].atoms) == 3


def test_text_with_no_actual_fences_falls_back_to_original():
    """A plain paragraph that mentions ``\\`\\`\\`xml`` without any
    real code fences must NOT be blanked. Without the fallback the
    function returned an empty string."""
    text = "This text mentions ```xml``` but has no real fences."
    # _extract_xml_fences is the pre-pass; we call parse to exercise
    # it indirectly. The text isn't valid scholia so parse will reject
    # it — but it must reject because the content isn't XML, not
    # because the pre-pass blanked it.
    from scholialang.parser import _extract_xml_fences
    assert _extract_xml_fences(text) == text
