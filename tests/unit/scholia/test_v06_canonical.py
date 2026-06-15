"""v0.6 — content-addressable canonical_id, registry, and prelude.

Covers the additive v0.6 surface: the canonical_id hasher + parser
stamping, the ``canonical_id_well_formed`` validator rule, the 4-path
``resolve_refer`` resolver, the DAG-backed registry, and the canonical
prelude renderer. v0.5 back-compat is exercised by the rest of the suite
(a v0.5 atom with ``canonical_id=None`` is vacuously well-formed).
"""
from __future__ import annotations

import os
import tempfile

import pytest

from scholialang.atoms import (
    Concluding,
    EventRef,
    Finding,
    Goal,
    Observation,
    compute_canonical_id,
)
from scholialang.parser import parse, parse_atom
from scholialang.prelude import build_canonical_prelude
from scholialang.registry import Registry, dag_from_dict, dag_to_dict
from scholialang.validator import (
    RULE_CANONICAL_ID_WELL_FORMED,
    RULE_NAMES,
    resolve_refer,
    validate,
)


# ── canonical_id hashing ─────────────────────────────────────────────


def test_canonical_id_format_and_stability():
    g = Goal(content="Find the root cause", scope="trace", criticality="kernel")
    cid = compute_canonical_id(g)
    assert cid.startswith("sha256:")
    assert len(cid) == len("sha256:") + 12
    # deterministic
    assert compute_canonical_id(g) == cid


def test_canonical_id_excludes_provenance():
    """Provenance fields (timestamp/run_id/sequence/...) don't change the hash."""
    o1 = Observation(content="ls output", location="src/x.py:1:9", confidence="0.9",
                     timestamp="2026-06-06T08:00:00Z")
    o2 = Observation(content="ls output", location="src/x.py:1:9", confidence="0.9",
                     timestamp="2020-01-01T00:00:00Z")
    assert compute_canonical_id(o1) == compute_canonical_id(o2)

    e1 = EventRef(content="evt", for_ref="F_1", run_id="r1", sequence=5, instance="i1")
    e2 = EventRef(content="evt", for_ref="F_1", run_id="r9", sequence=9, instance="i9")
    assert compute_canonical_id(e1) == compute_canonical_id(e2)


def test_canonical_id_distinguishes_content_and_attrs():
    assert compute_canonical_id(Goal(content="a")) != compute_canonical_id(Goal(content="b"))
    assert compute_canonical_id(
        Finding(content="x", for_hyp="H_1", status="confirmed")
    ) != compute_canonical_id(
        Finding(content="x", for_hyp="H_1", status="refuted")
    )


def test_parser_stamps_canonical_id():
    a = parse_atom('<Goal scope="trace" criticality="kernel">Ship it</Goal>')
    assert a.canonical_id == compute_canonical_id(a)


def test_parser_preserves_tampered_claimed_id_in_lazy_mode():
    a = parse_atom('<Goal canonical_id="sha256:deadbeef0000">x</Goal>')
    assert a.canonical_id == "sha256:deadbeef0000"
    assert a.canonical_id != compute_canonical_id(a)


# ── canonical_id_well_formed validator rule ──────────────────────────


def test_rule_registered():
    assert RULE_CANONICAL_ID_WELL_FORMED in RULE_NAMES


def test_clean_trace_passes_canonical_rule():
    trace = parse(
        '<Step id="s1" name="x"><Goal id="g1">Ship it</Goal></Step>'
    )
    result = validate(trace)
    assert not result.errors_by_rule.get(RULE_CANONICAL_ID_WELL_FORMED)


def test_tampered_atom_fails_canonical_rule():
    trace = parse(
        '<Step id="s1" name="x"><Goal id="g1">Ship it</Goal></Step>'
    )
    # mutate content after the canonical_id was stamped
    trace[0].atoms[0].content = "Ship something else"
    result = validate(trace)
    errs = result.errors_by_rule[RULE_CANONICAL_ID_WELL_FORMED]
    assert len(errs) == 1
    assert "canonical_id mismatch" in errs[0].message


# ── resolve_refer — 4-path resolver ──────────────────────────────────


def test_resolve_refer_by_local_id_and_canonical_id():
    trace = parse(
        '<Step id="s1" name="x"><Hypothesis id="h1">it works</Hypothesis></Step>'
    )
    h = trace[0].atoms[0]
    assert resolve_refer(trace, "h1") is h
    assert resolve_refer(trace, h.canonical_id) is h
    assert resolve_refer(trace, "sha256:000000000000") is None


# ── canonical prelude ────────────────────────────────────────────────


def test_prelude_modes():
    atoms = parse(
        '<Step id="s1" name="x">'
        '<Hypothesis id="h1">cache leaks</Hypothesis>'
        '<Finding id="f1" for_hyp="h1" status="confirmed">it reproduces</Finding>'
        '</Step>'
    )[0].atoms
    assert build_canonical_prelude([], mode="hash_only") == ""
    hash_only = build_canonical_prelude(atoms, mode="hash_only")
    assert "REFER:sha256:" in hash_only
    hash_list = build_canonical_prelude(atoms, mode="hash_list")
    assert "(Finding)" in hash_list
    inline = build_canonical_prelude(atoms, mode="inline")
    assert "<Hypothesis" in inline
    with pytest.raises(ValueError):
        build_canonical_prelude(atoms, mode="bogus")


# ── DAG registry ─────────────────────────────────────────────────────


def test_registry_put_get_and_edges():
    atoms = parse(
        '<Step id="s1" name="x">'
        '<Hypothesis id="h1">cache leaks</Hypothesis>'
        '<Finding id="f1" for_hyp="h1" status="confirmed">it reproduces</Finding>'
        '</Step>'
    )[0].atoms
    h, f = atoms
    with tempfile.TemporaryDirectory() as d:
        reg = Registry(os.path.join(d, "reg.json"))
        assert reg.put(h) is True
        assert reg.put(f) is True
        assert reg.put(f) is False  # idempotent
        assert reg.get(f.canonical_id)["kind"] == "Finding"
        assert len(reg) == 2

        c = parse(
            f'<Concluding for_goal="g1" confidence="0.9">'
            f'closes REFER:{f.canonical_id}</Concluding>'
        )[0].atoms[0]
        reg.put(c)
        ancestors = [a["kind"] for a in reg.ancestors(c.canonical_id)]
        assert "Finding" in ancestors
        descendants = [a["kind"] for a in reg.descendants(f.canonical_id)]
        assert "Concluding" in descendants


def test_registry_walk_dag_and_disk_format():
    f = parse_atom('<Finding id="f1" for_hyp="h1" status="confirmed">repro</Finding>')
    c = parse_atom(
        f'<Concluding for_goal="g1" confidence="0.9">REFER:{f.canonical_id}</Concluding>'
    )
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "reg.json")
        reg = Registry(path)
        reg.put(f)
        reg.put(c)
        dag = reg.walk_dag(c.canonical_id)
        assert dag.conclusion_id == c.canonical_id
        assert len(dag.nodes) == 2
        assert len(dag.edges) == 1
        assert dag.is_complete

        # dag round-trips through dict
        rt = dag_from_dict(dag_to_dict(dag))
        assert rt.conclusion_id == dag.conclusion_id
        assert len(rt.nodes) == len(dag.nodes)

        # on-disk format is v0.6 {version, atoms, edges}
        import json
        raw = json.load(open(path))
        assert raw["version"] == "0.6"
        assert set(raw.keys()) == {"version", "atoms", "edges"}
        assert len(raw["edges"]) == 1


def test_registry_put_requires_canonical_id():
    with tempfile.TemporaryDirectory() as d:
        reg = Registry(os.path.join(d, "reg.json"))
        with pytest.raises(ValueError):
            reg.put(Goal(content="no canonical id set"))
