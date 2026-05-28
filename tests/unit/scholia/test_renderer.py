"""Tests for scholialang.renderer — AST → Markdown / XML."""
from __future__ import annotations

from scholialang.atoms import (
    Cost,
    Deciding,
    EventRef,
    Evidence,
    Finding,
    Goal,
    Hypothesis,
    Observation,
    Step,
    Thinking,
)
from scholialang.parser import parse
from scholialang.renderer import render_atom, render_markdown, render_xml
from scholialang.serializer import to_canonical_json


def test_render_atom_basic():
    t = Thinking(id="T_01", content="hello")
    out = render_atom(t)
    assert "<Thinking" in out
    assert 'id="T_01"' in out
    assert "hello" in out
    assert "</Thinking>" in out


def test_render_markdown_produces_headings():
    trace = [Step(id="S_01", name="hello", atoms=[Thinking(content="x")])]
    md = render_markdown(trace)
    assert "## hello" in md
    assert "```xml" in md
    assert "```" in md


def test_render_markdown_with_title():
    trace = [Step(id="S", atoms=[Thinking(content="y")])]
    md = render_markdown(trace, title="My Trace")
    assert md.startswith("# My Trace")


def test_render_xml_has_no_markdown_chrome():
    trace = [Step(id="S_01", name="t", atoms=[Thinking(content="z")])]
    xml = render_xml(trace)
    assert "```" not in xml
    assert "<Step" in xml


def test_roundtrip_render_parse_preserves_structure():
    original_text = (
        '<Step id="S_01" name="t">'
        '<Hypothesis id="H_01">content</Hypothesis>'
        '<Finding id="F_01">conclusion</Finding>'
        "</Step>"
    )
    steps_a = parse(original_text)
    rendered = render_xml(steps_a)
    steps_b = parse(rendered)
    # Canonical JSON equality is the most robust structural check
    # without worrying about whitespace normalisation.
    assert to_canonical_json(steps_a) == to_canonical_json(steps_b)


def test_render_nested_atoms():
    d = Deciding(
        id="D_01",
        options=["A", "B"],
        children=[Finding(id="F_01", content="chose A")],
    )
    trace = [Step(id="S", atoms=[d])]
    md = render_markdown(trace)
    assert "<Deciding" in md
    assert "options = LIST:" in md
    assert '- "A"' in md
    assert '- "B"' in md
    assert "<Finding" in md


def test_evidence_wire_name_for_appears():
    ev = Evidence(id="E", for_ref="H_01", polarity="supports")
    out = render_atom(ev)
    assert 'for="H_01"' in out
    assert "for_ref" not in out


def test_renderer_escapes_xml_special_chars():
    t = Thinking(id="T", content="<notAnAtom> & < > should escape")
    out = render_atom(t)
    assert "&amp;" in out
    assert "&lt;" in out
    assert "&gt;" in out


def test_empty_trace_renders_cleanly():
    md = render_markdown([])
    assert md.strip() == ""


def test_renderer_emits_v02_attrs_and_self_closing_atoms():
    trace = [
        Step(
            id="S",
            atoms=[
                Observation(id="O", timestamp="2026-04-21T12:00:00-07:00"),
                EventRef(
                    id="ER",
                    instance="ot_A",
                    run_id="run",
                    sequence=2,
                    for_ref="O",
                    wall_clock="2026-04-21T12:00:00-07:00",
                ),
                Cost(for_ref="O", tokens=1, wall_clock_ms=2, dollars=0.01),
            ],
        )
    ]
    xml = render_xml(trace)
    assert 'timestamp="2026-04-21T12:00:00-07:00"' in xml
    assert '<EventRef id="ER"' in xml
    assert 'sequence="2"' in xml
    assert '<Cost for="O" tokens="1" wall_clock_ms="2" dollars="0.01"/>' in xml


def test_renderer_emits_goal_lists():
    out = render_atom(
        Goal(
            id="G",
            priority="required",
            success_criteria=["done"],
            failure_modes=["fail"],
        )
    )
    assert "success_criteria = LIST:" in out
    assert "failure_modes = LIST:" in out
