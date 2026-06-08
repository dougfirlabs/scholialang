"""v0.6 EXPERIMENTAL prelude recovery arms — hash_semantic_preview + selective_inline.

Ported from the v06-qf reference (``tests/test_prelude_recovery_modes.py``).
These two modes post-date the 2026-06-06 golden-records manifest and are
shipped as an EXPERIMENTAL extension — they are NOT part of the finalized
v0.6 core (``CORE_PRELUDE_MODES``) and must be opted into explicitly via
``build_canonical_prelude(..., allow_experimental=True)``. The tests cover
both the gating contract and the renderers' behaviour.
"""
from __future__ import annotations

import pytest

from scholialang.atoms import Finding, Goal, Observation, compute_canonical_id
from scholialang.prelude import (
    CORE_PRELUDE_MODES,
    EXPERIMENTAL_PRELUDE_MODES,
    build_canonical_prelude,
)


def _atoms():
    g = Goal(content="Audit the token-rotation patch for atomicity and theft handling.")
    o = Observation(
        content="Session 2 patch revokes the old token before issuing the new one."
    )
    f = Finding(
        content=(
            "The patch must invalidate the old token before returning the new "
            "token; rollback should leave exactly one valid token."
        )
    )
    for a in (g, o, f):
        a.canonical_id = compute_canonical_id(a)
    return [g, o, f]


# ── Mode enumeration / gating contract ───────────────────────────────


def test_recovery_arms_are_not_core():
    """The 2 recovery arms must NOT appear in the official core enumeration."""
    assert set(CORE_PRELUDE_MODES) == {"hash_only", "hash_list", "inline"}
    assert "hash_semantic_preview" in EXPERIMENTAL_PRELUDE_MODES
    assert "selective_inline_plus_hash_only" in EXPERIMENTAL_PRELUDE_MODES
    assert not (set(EXPERIMENTAL_PRELUDE_MODES) & set(CORE_PRELUDE_MODES))


def test_experimental_modes_require_optin():
    """Experimental arms are gated: calling them without the opt-in raises."""
    for mode in EXPERIMENTAL_PRELUDE_MODES:
        with pytest.raises(ValueError):
            build_canonical_prelude(_atoms(), mode=mode)
        # and succeed when explicitly opted in
        out = build_canonical_prelude(_atoms(), mode=mode, allow_experimental=True)
        assert isinstance(out, str)


# ── hash_semantic_preview ────────────────────────────────────────────


def test_semantic_preview_shape():
    out = build_canonical_prelude(
        _atoms(), mode="hash_semantic_preview", allow_experimental=True
    )
    assert "semantic preview" in out
    # compact form: cid line carries (Kind, criticality), plus a summary
    assert "sha256:" in out
    assert "(Finding, normal)" in out
    assert "summary:" in out


def test_semantic_preview_no_field_triplication():
    # A short atom must not be rendered 3x (title+summary+claims). Its
    # rendered block should be on the order of its body, not a multiple.
    f = Finding(
        content="The patch must invalidate the old token before returning the new one."
    )
    f.canonical_id = compute_canonical_id(f)
    out = build_canonical_prelude(
        [f], mode="hash_semantic_preview", allow_experimental=True
    )
    assert out.count("must invalidate the old token") <= 1


def test_semantic_preview_compresses_long_bodies():
    # Semantic preview's compression materializes when atom BODIES are long
    # (the bounded summary truncates them).
    atoms = []
    for i in range(8):
        body = (
            f"Finding {i}: the patch must invalidate the old token before "
            "returning the new one and ensure rollback leaves exactly one "
            "valid token across concurrent refresh attempts. " * 4
        )
        a = Finding(content=body)
        a.canonical_id = compute_canonical_id(a)
        atoms.append(a)
    sem = build_canonical_prelude(
        atoms, mode="hash_semantic_preview", allow_experimental=True
    )
    inline = build_canonical_prelude(atoms, mode="inline")
    assert len(sem) < len(inline), (
        f"semantic {len(sem)} should be < inline {len(inline)} on long bodies"
    )


def test_semantic_preview_per_atom_budget():
    # Per-atom rendered size stays bounded regardless of body length.
    long_body = "x y z must ensure correctness " * 50
    f = Finding(content=long_body)
    f.canonical_id = compute_canonical_id(f)
    out = build_canonical_prelude(
        [f], mode="hash_semantic_preview", allow_experimental=True
    )
    block = out.split("\n", 1)[1]
    assert len(block) < 500, f"per-atom block {len(block)} chars exceeds budget"


# ── selective_inline_plus_hash_only ──────────────────────────────────


def test_selective_inline_critical_shape():
    out = build_canonical_prelude(
        _atoms(), mode="selective_inline_plus_hash_only", allow_experimental=True
    )
    assert "Critical prior atoms inlined" in out
    # Finding + Goal are critical -> inlined with canonical_id attr
    assert 'canonical_id="sha256:' in out
    # the non-critical Observation goes to the hash-only remainder
    assert "REFER:sha256:" in out
    # inline cap respected (<=3 atoms)
    assert out.count('canonical_id="sha256:') <= 3


# ── shared invariants ────────────────────────────────────────────────


def test_empty_input_is_empty():
    assert (
        build_canonical_prelude(
            [], mode="hash_semantic_preview", allow_experimental=True
        )
        == ""
    )
    assert (
        build_canonical_prelude(
            [], mode="selective_inline_plus_hash_only", allow_experimental=True
        )
        == ""
    )


def test_deterministic():
    a = build_canonical_prelude(
        _atoms(), mode="hash_semantic_preview", allow_experimental=True
    )
    b = build_canonical_prelude(
        _atoms(), mode="hash_semantic_preview", allow_experimental=True
    )
    assert a == b
