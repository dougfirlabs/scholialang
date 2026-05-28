"""Tests for the closed-set canonical helpers in scholia.atoms.

Exercises:
* ``CANONICAL_OPERATORS`` + ``KNOWN_KINDS`` shape — the validator-ratified
  vocabulary the grammar-emergence detector compares against.
* ``parse_operators_from_content`` — regex extraction of
  ``UPPERCASE_TOKEN:atom_id`` pairs from atom content.
* Membership helpers ``is_canonical_operator`` / ``is_known_kind``.
"""
from __future__ import annotations

from scholialang.atoms import (
    ATOM_KINDS,
    CANONICAL_OPERATORS,
    KNOWN_KINDS,
    is_canonical_operator,
    is_known_kind,
    parse_operators_from_content,
)


# ── CANONICAL_OPERATORS shape ────────────────────────────────────────


def test_canonical_operators_matches_v04_spec_enum():
    # v0.4 (2026-05-11) — operator-driven mass-promotion brings the
    # validator-ratified set in line with the full ``Operator`` enum
    # ahead of the pre-MS-Co-Pilot benchmark window. CANONICAL_OPERATORS
    # must equal the set of all values declared by the spec enum.
    from scholialang.atoms import OPERATORS

    assert isinstance(CANONICAL_OPERATORS, frozenset)
    assert CANONICAL_OPERATORS == frozenset(OPERATORS)


def test_canonical_operators_includes_v04_promotions():
    # Regression guard for the 2026-05-11 promotion. Pins every
    # operator the spec declares so a future enum trim doesn't silently
    # take the validator out of sync with the notation reference.
    for op in (
        "REFER",
        "IMPLIES",
        "NOT",
        "AND",
        "OR",
        "XOR",
        "FORALL",
        "EXISTS",
        "BEFORE",
        "AFTER",
        "EQUALS",
    ):
        assert op in CANONICAL_OPERATORS, f"{op} must be canonical post-v0.4"


def test_known_kinds_matches_atom_kinds():
    assert isinstance(KNOWN_KINDS, frozenset)
    assert KNOWN_KINDS == frozenset(ATOM_KINDS)


# ── Membership helpers ──────────────────────────────────────────────


def test_is_canonical_operator_true_for_canonical():
    # Post-v0.4 every spec-listed operator is canonical.
    for op in ("REFER", "IMPLIES", "NOT", "AND", "OR", "XOR", "FORALL"):
        assert is_canonical_operator(op)


def test_is_canonical_operator_false_for_novel():
    # Tokens outside the spec enum still fall through as novel; the
    # grammar-emergence detector will surface them for future review.
    assert not is_canonical_operator("MAYBE")
    assert not is_canonical_operator("UNKNOWN_OP")
    assert not is_canonical_operator("THEREFORE")


def test_is_known_kind_true_for_every_atom_kind():
    for kind in ATOM_KINDS:
        assert is_known_kind(kind), f"{kind} should be in KNOWN_KINDS"


def test_is_known_kind_false_for_novel():
    assert not is_known_kind("Conjecturing")
    assert not is_known_kind("BogusKind")


# ── parse_operators_from_content edge cases ─────────────────────────


def test_parse_no_operators_in_content():
    assert parse_operators_from_content("Plain prose with no operators.") == []
    assert parse_operators_from_content("") == []
    assert parse_operators_from_content(None) == []  # type: ignore[arg-type]


def test_parse_single_canonical_operator():
    assert parse_operators_from_content("see REFER:Obs_01 for context") == [
        ("REFER", "Obs_01"),
    ]


def test_parse_multiple_operators_in_same_content():
    pairs = parse_operators_from_content(
        "REFER:Obs_01 and IMPLIES:Fin_02 follows from above."
    )
    assert pairs == [("REFER", "Obs_01"), ("IMPLIES", "Fin_02")]


def test_parse_operator_in_mid_sentence():
    pairs = parse_operators_from_content(
        "the conclusion REFER:Fin_03 was retracted later"
    )
    assert pairs == [("REFER", "Fin_03")]


def test_parse_operator_with_underscore_in_name():
    # The regex permits underscores in operator names so future
    # multi-word emergent operators (e.g. ``NOT_REFER``) are captured.
    pairs = parse_operators_from_content(
        "experimental NOT_REFER:Obs_22 from gemma4"
    )
    assert pairs == [("NOT_REFER", "Obs_22")]


def test_parse_handles_whitespace_around_colon():
    pairs = parse_operators_from_content("REFER : Obs_01")
    assert pairs == [("REFER", "Obs_01")]


def test_parse_does_not_match_lowercase_tokens():
    # Lowercase prose words (``refer``, ``implies``) must not match — the
    # detector only fires on the spec's UPPERCASE convention.
    assert parse_operators_from_content("we refer:something here") == []


def test_parse_does_not_match_single_letter_token():
    # The regex requires length ≥ 2 to avoid matching arbitrary
    # initialisms like ``A:B`` in URLs or comments.
    assert parse_operators_from_content("A:B is unrelated") == []


def test_parse_captures_novel_operator_maybe():
    # Post-v0.3, NOT is canonical; MAYBE stands in as the representative
    # novel operator the regex must still extract for the detector to
    # flag as a novel-operator finding.
    pairs = parse_operators_from_content(
        "the conclusion MAYBE:Obs_22 was tentative"
    )
    assert pairs == [("MAYBE", "Obs_22")]


def test_parse_preserves_duplicate_occurrences():
    # Multiple uses of the same operator in one atom count as multiple
    # findings — the threshold engine compares against
    # min_occurrences across all findings.
    pairs = parse_operators_from_content(
        "REFER:Obs_01 then REFER:Obs_02 also REFER:Obs_03"
    )
    assert pairs == [
        ("REFER", "Obs_01"),
        ("REFER", "Obs_02"),
        ("REFER", "Obs_03"),
    ]


# ── Coverage: every canonical operator + a representative novel ─────


def test_every_canonical_operator_round_trips():
    for op in CANONICAL_OPERATORS:
        pairs = parse_operators_from_content(f"{op}:Atom_01 sample")
        assert pairs == [(op, "Atom_01")]


def test_three_representative_novels_round_trip():
    # The PRD mandates coverage of three novel cases. Post-v0.4 the
    # whole Operator enum is canonical, so the novel examples must be
    # tokens that have NEVER been in the spec — picking distinct shapes:
    # bare uppercase, underscore-bearing, multi-char.
    for novel in ("MAYBE", "THEREFORE", "BEFORE_AFTER"):
        pairs = parse_operators_from_content(f"{novel}:Tgt_99 trailing")
        assert pairs == [(novel, "Tgt_99")]
        assert not is_canonical_operator(novel)
