"""v0.6 validator source-level audit — canonical-id integrity + reference resolution.

This is the source test file the golden-records compatibility manifest flagged
as ABSENT for the ``validator-scholialang`` record ("v0.6 validator pycache but
not the source test file → needs a fresh source-level audit"). Its presence and
passing status closes that record from ``unknown`` → ``pass``.

It asserts the v0.6 validator union contract:

* ``RULE_NAMES`` carries ``canonical_id_well_formed`` + ``reference_complete``
  alongside the 6 v0.5 Concluding rules.
* ``canonical_id_well_formed`` is a universal recompute-and-compare rule: a
  tampered canonical_id yields exactly one hard-fail; a clean / canonical-id-less
  trace is vacuously valid.
* ``reference_complete`` is the 4-path REFER resolver surface — a dangling REFER
  is named as a violation; a canonical_id-form attribute reference resolves; the
  ``resolve_refer`` primitive walks local id → in-trace canonical_id → registry.
"""
from __future__ import annotations

import os
import tempfile

from scholialang.atoms import compute_canonical_id
from scholialang.parser import parse, parse_atom
from scholialang.registry import Registry
from scholialang.validator import (
    RULE_CANONICAL_ID_WELL_FORMED,
    RULE_CRITICALITY_NON_DECREASING,
    RULE_FOR_GOAL_RESOLVES,
    RULE_MIN_CONFIDENCE_CEILING,
    RULE_NAMES,
    RULE_NO_ACTION_IN_CONCLUDING,
    RULE_REFER_AT_LEAST_ONE,
    RULE_REFERENCE_COMPLETE,
    RULE_SINGLE_ACTIVE_CONCLUDING_PER_GOAL,
    resolve_refer,
    validate,
)


# ── RULE_NAMES union — canonical-id rules + the 6 Concluding rules ────


_CONCLUDING_RULES = (
    RULE_FOR_GOAL_RESOLVES,
    RULE_REFER_AT_LEAST_ONE,
    RULE_CRITICALITY_NON_DECREASING,
    RULE_NO_ACTION_IN_CONCLUDING,
    RULE_SINGLE_ACTIVE_CONCLUDING_PER_GOAL,
    RULE_MIN_CONFIDENCE_CEILING,
)


def test_rule_names_include_canonical_id_rules_and_concluding_set():
    assert RULE_CANONICAL_ID_WELL_FORMED in RULE_NAMES
    assert RULE_REFERENCE_COMPLETE in RULE_NAMES
    for rule in _CONCLUDING_RULES:
        assert rule in RULE_NAMES, f"missing Concluding rule {rule!r}"


# ── canonical_id_well_formed — recompute-and-compare, universal ───────


def test_clean_trace_has_no_canonical_id_violation():
    trace = parse('<Step id="s1" name="x"><Goal id="g1">Ship it</Goal></Step>')
    result = validate(trace)
    assert not result.errors_by_rule.get(RULE_CANONICAL_ID_WELL_FORMED)


def test_canonical_id_less_atom_is_vacuously_well_formed():
    """A v0.5 atom carrying no canonical_id never trips the rule (back-compat)."""
    trace = parse('<Step id="s1" name="x"><Goal id="g1">Ship it</Goal></Step>')
    trace[0].atoms[0].canonical_id = None
    result = validate(trace)
    assert not result.errors_by_rule.get(RULE_CANONICAL_ID_WELL_FORMED)


def test_tampered_canonical_id_yields_exactly_one_hard_fail():
    trace = parse('<Step id="s1" name="x"><Goal id="g1">Ship it</Goal></Step>')
    # mutate content after the canonical_id was stamped at parse time
    trace[0].atoms[0].content = "Ship something else"
    result = validate(trace)
    errs = result.errors_by_rule[RULE_CANONICAL_ID_WELL_FORMED]
    assert len(errs) == 1
    assert errs[0].rule == RULE_CANONICAL_ID_WELL_FORMED
    assert "canonical_id mismatch" in errs[0].message
    # canonical-id failures are hard fails — the trace is not ok
    assert not result.ok


def test_parser_preserves_tampered_claimed_id_for_validator():
    a = parse_atom('<Goal canonical_id="sha256:deadbeef0000">x</Goal>')
    assert a.canonical_id == "sha256:deadbeef0000"
    assert a.canonical_id != compute_canonical_id(a)


# ── reference_complete — dangling REFER detection + canonical-id refs ─


def test_dangling_refer_is_named_by_reference_complete():
    trace = parse(
        '<Step id="s1" name="x">'
        '<Finding id="f1">REFER:Ghost_99 has no target</Finding>'
        "</Step>"
    )
    result = validate(trace)
    errs = result.errors_by_rule[RULE_REFERENCE_COMPLETE]
    assert errs, "dangling REFER must produce a reference_complete violation"
    assert any("Ghost_99" in e.message for e in errs)
    assert not result.ok


def test_reference_complete_resolves_local_id():
    trace = parse(
        '<Step id="s1" name="x">'
        '<Hypothesis id="h1">cache leaks</Hypothesis>'
        '<Finding id="f1">REFER:h1 confirms it</Finding>'
        "</Step>"
    )
    result = validate(trace)
    assert not result.errors_by_rule.get(RULE_REFERENCE_COMPLETE)


# ── resolve_refer — 4-path resolver primitive ────────────────────────


def test_resolve_refer_local_then_canonical_then_registry():
    trace = parse(
        '<Step id="s1" name="x"><Hypothesis id="h1">it works</Hypothesis></Step>'
    )
    h = trace[0].atoms[0]
    # path 1: local id
    assert resolve_refer(trace, "h1") is h
    # path 2: in-trace canonical_id
    assert resolve_refer(trace, h.canonical_id) is h
    # path 4: unresolved
    assert resolve_refer(trace, "sha256:000000000000") is None

    # path 3: registry lookup by canonical_id
    f = parse_atom('<Finding id="f9" status="confirmed">repro</Finding>')
    with tempfile.TemporaryDirectory() as d:
        reg = Registry(os.path.join(d, "reg.json"))
        reg.put(f)
        empty_trace = parse('<Step id="s2" name="y"><Goal id="g2">x</Goal></Step>')
        resolved = resolve_refer(empty_trace, f.canonical_id, registry=reg)
        assert isinstance(resolved, dict)
        assert resolved["kind"] == "Finding"


# ── full Concluding-scoped trace validates clean under the union ──────


def test_well_formed_concluding_trace_is_clean():
    trace = parse(
        '<Step id="s1" name="close">'
        '<Goal id="g1" criticality="kernel">Resolve the leak</Goal>'
        '<Hypothesis id="h1">cache leaks</Hypothesis>'
        '<Evidence id="e1" for="h1" polarity="support">'
        "heap grows monotonically under load</Evidence>"
        '<Finding id="f1" for_hyp="h1" status="confirmed">'
        "leak reproduced under load</Finding>"
        '<Concluding id="c1" for_goal="g1" criticality="kernel">'
        "REFER:f1 establishes the leak is real</Concluding>"
        "</Step>"
    )
    result = validate(trace)
    assert result.ok, [e.message for e in result.errors]
