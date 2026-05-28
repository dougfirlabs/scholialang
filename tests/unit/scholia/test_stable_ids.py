"""Tests for ``scholialang.stable_ids`` — v0.4-A derivation."""
from __future__ import annotations

import pytest

from scholialang.stable_ids import (
    STABLE_ID_HEX_LENGTH,
    canonicalize_text,
    derive_atom_id,
    is_stable_id,
)


# ── derive_atom_id: format ──────────────────────────────────────────


def test_derive_atom_id_returns_kind_underscore_8hex() -> None:
    atom_id = derive_atom_id("Goal", "Convert syntax trees to lambda-calculus")
    assert atom_id.startswith("Goal_")
    suffix = atom_id.split("_", 1)[1]
    assert len(suffix) == STABLE_ID_HEX_LENGTH
    assert all(c in "0123456789abcdef" for c in suffix)


@pytest.mark.parametrize(
    "kind",
    ["Goal", "Observation", "Hypothesis", "Evidence", "Finding", "Concluding", "Step"],
)
def test_derive_atom_id_preserves_kind_prefix(kind: str) -> None:
    atom_id = derive_atom_id(kind, "some content")
    assert atom_id.startswith(f"{kind}_")


# ── derive_atom_id: determinism ─────────────────────────────────────


def test_derive_atom_id_is_deterministic() -> None:
    a = derive_atom_id("Goal", "Convert syntax trees to lambda-calculus")
    b = derive_atom_id("Goal", "Convert syntax trees to lambda-calculus")
    assert a == b


def test_derive_atom_id_deterministic_across_kinds() -> None:
    # Same text, different kinds → different IDs (kind is in the prefix).
    text = "Identical body of text"
    goal = derive_atom_id("Goal", text)
    obs = derive_atom_id("Observation", text)
    assert goal != obs
    # But the hex suffix is the same because the canonical text matches.
    assert goal.split("_")[1] == obs.split("_")[1]


# ── canonicalization ────────────────────────────────────────────────


def test_canonicalize_strips_leading_and_trailing_whitespace() -> None:
    assert canonicalize_text("  hello world  ") == "hello world"


def test_canonicalize_lowercases() -> None:
    assert canonicalize_text("Hello World") == "hello world"


def test_canonicalize_collapses_internal_whitespace() -> None:
    assert canonicalize_text("hello   world\n\nfoo\tbar") == "hello world foo bar"


def test_canonicalize_empty_returns_empty() -> None:
    assert canonicalize_text("") == ""
    assert canonicalize_text("   \n\t  ") == ""


def test_derive_atom_id_canonicalization_collapses_whitespace_drift() -> None:
    # The same logical sentence with different whitespace/case → same ID.
    a = derive_atom_id("Observation", "Reads the file and writes to disk.")
    b = derive_atom_id("Observation", "  reads   the  file\nand WRITES to disk.  ")
    assert a == b


# ── operator-target stripping ──────────────────────────────────────


def test_canonicalize_strips_operator_targets() -> None:
    # OP:atom_id becomes OP alone — the target dependency is removed.
    canon = canonicalize_text("This atom IMPLIES:Observation_01 and is done.")
    assert "implies" in canon
    assert "observation_01" not in canon


def test_derive_atom_id_invariant_under_referenced_id_changes() -> None:
    """An atom's stable ID must not shift when the IDs of atoms it
    references are remapped — otherwise the remap pipeline breaks the
    downstream-recomputation contract."""
    a = derive_atom_id(
        "Finding",
        "A leaf utility module, IMPLIES:Observation_03.",
    )
    b = derive_atom_id(
        "Finding",
        "A leaf utility module, IMPLIES:Observation_a7f3e2c1.",
    )
    assert a == b


def test_derive_atom_id_distinguishes_operator_kinds() -> None:
    """REFER vs IMPLIES vs NOT carry different structural intent —
    they should NOT collapse to a single canonical form."""
    refer = derive_atom_id("Observation", "x REFER:Y and y")
    implies = derive_atom_id("Observation", "x IMPLIES:Y and y")
    assert refer != implies


# ── argument validation ─────────────────────────────────────────────


def test_derive_atom_id_rejects_empty_kind() -> None:
    with pytest.raises(ValueError):
        derive_atom_id("", "text")


def test_derive_atom_id_rejects_kind_with_underscore() -> None:
    # Underscores would collide with the kind-suffix separator.
    with pytest.raises(ValueError):
        derive_atom_id("Bad_Kind", "text")


def test_derive_atom_id_rejects_kind_starting_with_digit() -> None:
    with pytest.raises(ValueError):
        derive_atom_id("1Goal", "text")


def test_derive_atom_id_accepts_empty_text() -> None:
    # Empty text is still valid input; it just hashes the empty canonical.
    atom_id = derive_atom_id("Goal", "")
    assert atom_id.startswith("Goal_")
    assert len(atom_id.split("_")[1]) == STABLE_ID_HEX_LENGTH


# ── purity: no environment dependence ──────────────────────────────


def test_derive_atom_id_independent_of_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No system clock, no environment vars, no random seed."""
    before = derive_atom_id("Goal", "stability check")
    monkeypatch.setenv("TZ", "Pacific/Auckland")
    monkeypatch.setenv("PYTHONHASHSEED", "12345")
    after = derive_atom_id("Goal", "stability check")
    assert before == after


# ── is_stable_id format check ───────────────────────────────────────


def test_is_stable_id_accepts_v04_form() -> None:
    assert is_stable_id("Goal_a7f3e2c1")
    assert is_stable_id("Observation_deadbeef")


def test_is_stable_id_rejects_sequence_form() -> None:
    assert not is_stable_id("Goal_01")
    assert not is_stable_id("Observation_12")


def test_is_stable_id_rejects_garbage() -> None:
    assert not is_stable_id("")
    assert not is_stable_id("just-some-string")
    assert not is_stable_id("Goal_xyz")  # non-hex chars
    assert not is_stable_id("Goal_ABCDEF12")  # uppercase hex not accepted
    assert not is_stable_id("Goal_a7f3e2c")  # too short
    assert not is_stable_id("Goal_a7f3e2c12")  # too long


# ── fixture-based determinism table ─────────────────────────────────


# Golden IDs for known (kind, text) pairs. If this table changes, every
# stored Atlas artifact under .ot-codex/ keyed by these IDs becomes
# unreadable, so this serves as a tripwire against accidental drift in
# the canonicalization or hashing.
GOLDEN_PAIRS: list[tuple[str, str, str]] = [
    ("Goal", "Provide a tiny date helper utility module.", "Goal_"),
    ("Observation", "Exports utc_iso_now returning ISO-8601 UTC.", "Observation_"),
    ("Finding", "A leaf utility module with no internal dependencies.", "Finding_"),
    ("Hypothesis", "Callers timestamp events.", "Hypothesis_"),
]


@pytest.mark.parametrize("kind,text,prefix", GOLDEN_PAIRS)
def test_golden_pairs_have_stable_format(kind: str, text: str, prefix: str) -> None:
    atom_id = derive_atom_id(kind, text)
    assert atom_id.startswith(prefix)
    assert is_stable_id(atom_id)


def test_golden_pairs_pairwise_distinct() -> None:
    """The fixture set is chosen so all derived IDs are distinct — if
    this ever fails, the canonicalization or fixture set has drifted."""
    ids = {derive_atom_id(kind, text) for kind, text, _ in GOLDEN_PAIRS}
    assert len(ids) == len(GOLDEN_PAIRS)
