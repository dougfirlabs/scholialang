"""Atom-catalog tests for Scholia v0.5.

Covers the six required cases from PRD
``rsi-scholia-v0.5-01-atom-catalog-reconciliation``:

(a) Concluding parses from XML with required for_goal.
(b) Concluding rejects without for_goal.
(c) Finding accepts both for_goal and for_hyp.
(d) Finding for_goal emits DeprecationWarning when set.
(e) CRITICALITY_RANK has the 5-tier ordering.
(f) closed-set has exactly 32 atoms including Concluding.

Plus fixture round-trip:
- v04 fixture parses with zero warnings.
- v05 fixture parses cleanly with the new Concluding atom.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from scholialang.atoms import (
    ATOM_KINDS,
    CRITICALITY_RANK,
    Concluding,
    Finding,
    atom_to_xml,
    parse_atom,
    parse_trace,
)
import xml.etree.ElementTree as ET


_FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ── (a) Concluding parses from XML with required for_goal ────────────

def test_concluding_parses_from_xml_with_for_goal() -> None:
    xml = (
        '<Concluding id="Concl_01" for_goal="G_01" confidence="0.9">'
        'REFER:F_01 closes the goal.</Concluding>'
    )
    elem = ET.fromstring(xml)
    atom = parse_atom(elem)
    assert isinstance(atom, Concluding)
    assert atom.id == "Concl_01"
    assert atom.for_goal == "G_01"
    assert atom.confidence == 0.9
    assert "REFER:F_01" in atom.content


def test_concluding_round_trips_through_xml() -> None:
    original = Concluding(
        id="Concl_99",
        for_goal="G_42",
        confidence=0.75,
        criticality="kernel",
        content="REFER:F_03 establishes the close.",
    )
    xml = atom_to_xml(original)
    parsed = parse_atom(ET.fromstring(xml))
    assert isinstance(parsed, Concluding)
    assert parsed.id == original.id
    assert parsed.for_goal == original.for_goal
    assert parsed.confidence == original.confidence
    assert parsed.criticality == original.criticality
    assert "REFER:F_03" in parsed.content


# ── (b) Concluding rejects without for_goal ──────────────────────────

def test_concluding_rejects_when_for_goal_missing_in_xml() -> None:
    xml = '<Concluding id="Concl_02">REFER:F_01 missing target.</Concluding>'
    with pytest.raises(ValueError, match="for_goal"):
        parse_atom(ET.fromstring(xml))


def test_concluding_constructor_rejects_when_for_goal_missing() -> None:
    with pytest.raises(ValueError, match="for_goal"):
        Concluding(id="Concl_03", content="REFER:F_02")


# ── (c) Finding accepts both for_goal and for_hyp ────────────────────

def test_finding_accepts_for_hyp() -> None:
    f = Finding(id="F_01", for_hyp="H_01", status="met", content="OK")
    assert f.for_hyp == "H_01"
    assert f.for_goal is None
    assert f.status == "met"


def test_finding_accepts_for_goal_back_compat() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        f = Finding(id="F_02", for_goal="G_01", status="met", content="OK")
    assert f.for_goal == "G_01"
    assert f.for_hyp is None


def test_finding_from_legacy_copies_for_goal_into_for_hyp() -> None:
    f = Finding.from_legacy(
        {"id": "F_03", "for_goal": "G_99", "status": "met", "content": "x"}
    )
    assert f.for_hyp == "G_99"
    assert f.for_goal is None
    assert f.status == "met"


# ── (d) Finding for_goal emits DeprecationWarning when set ───────────

def test_finding_for_goal_emits_deprecation_warning_on_init() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Finding(id="F_04", for_goal="G_01")
    deprecation_warnings = [
        w for w in caught if issubclass(w.category, DeprecationWarning)
    ]
    assert len(deprecation_warnings) == 1
    assert "for_hyp" in str(deprecation_warnings[0].message)


def test_finding_for_goal_emits_warning_only_once_per_instance() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        f = Finding(id="F_05", for_goal="G_01")
        f.for_goal = "G_02"
        f.for_goal = "G_03"
    deprecation_warnings = [
        w for w in caught if issubclass(w.category, DeprecationWarning)
    ]
    assert len(deprecation_warnings) == 1


def test_finding_for_hyp_does_not_emit_warning() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Finding(id="F_06", for_hyp="H_01")
    deprecation_warnings = [
        w for w in caught if issubclass(w.category, DeprecationWarning)
    ]
    assert deprecation_warnings == []


# ── (e) CRITICALITY_RANK has the 5-tier ordering ─────────────────────

def test_criticality_rank_has_five_tiers() -> None:
    assert set(CRITICALITY_RANK.keys()) == {
        "incidental",
        "bridge",
        "ledger",
        "verifier",
        "kernel",
    }


def test_criticality_rank_ordering_is_monotone() -> None:
    assert CRITICALITY_RANK["incidental"] == 0
    assert CRITICALITY_RANK["bridge"] == 1
    assert CRITICALITY_RANK["ledger"] == 2
    assert CRITICALITY_RANK["verifier"] == 3
    assert CRITICALITY_RANK["kernel"] == 4
    ordered = sorted(CRITICALITY_RANK, key=CRITICALITY_RANK.__getitem__)
    assert ordered == ["incidental", "bridge", "ledger", "verifier", "kernel"]


# ── (f) Closed set has exactly 32 atoms including Concluding ─────────

def test_closed_set_size_is_thirty_two() -> None:
    assert len(ATOM_KINDS) == 32


def test_closed_set_includes_concluding() -> None:
    assert "Concluding" in ATOM_KINDS


def test_closed_set_kinds_unique() -> None:
    assert len(set(ATOM_KINDS)) == len(ATOM_KINDS)


# ── Fixture parses ───────────────────────────────────────────────────

def test_v04_fixture_parses_with_zero_warnings() -> None:
    xml = (_FIXTURE_DIR / "v04_trace.xml").read_text()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        trace = parse_trace(xml)
    assert len(trace) == 1
    step = trace[0]
    assert step.id == "step_01"
    # Finding came in as v04-style for_goal; parser migrates to for_hyp
    # via from_legacy without emitting the deprecation warning.
    assert caught == []
    finding = [a for a in step.atoms if a.kind == "Finding"][0]
    assert finding.for_hyp == "G_01"
    assert finding.for_goal is None


def test_v05_fixture_parses_with_concluding() -> None:
    xml = (_FIXTURE_DIR / "v05_trace.xml").read_text()
    trace = parse_trace(xml)
    assert len(trace) == 1
    step = trace[0]
    kinds = [a.kind for a in step.atoms]
    assert "Concluding" in kinds
    concluding = [a for a in step.atoms if a.kind == "Concluding"][0]
    assert concluding.for_goal == "G_01"
    assert concluding.confidence == 0.92
