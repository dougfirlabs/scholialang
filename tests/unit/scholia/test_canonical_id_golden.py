"""Byte-identity check — local hasher vs frozen v06-qf golden vectors.

The golden vectors in ``tests/fixtures/canonical_id_golden.json`` were frozen
from the v0.6 reference implementation
(``opentalon-v06-qf/scholialang/src/scholialang/atoms.py``, committed
2026-06-06). This test reconstructs each vector atom from its stored kwargs and
asserts the standalone ``compute_canonical_id`` reproduces the reference id
byte-for-byte. It is the cross-implementation lock for the canonical_id
contract (shared with PRD-02); a single mismatch is a release blocker.
"""
from __future__ import annotations

import json
from pathlib import Path

import scholialang.atoms as atoms_module
from scholialang.atoms import compute_canonical_id

_FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "canonical_id_golden.json"
)


def _load_vectors() -> list[dict]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return data["vectors"]


def test_golden_fixture_present_and_substantial():
    """>=10 atoms per the PRD acceptance criterion."""
    vectors = _load_vectors()
    assert len(vectors) >= 10, f"expected >=10 golden vectors, got {len(vectors)}"


def test_local_canonical_ids_match_v06qf_golden_vectors():
    vectors = _load_vectors()
    mismatches: list[str] = []
    for v in vectors:
        cls = getattr(atoms_module, v["kind"])
        atom = cls(**v["kwargs"])
        got = compute_canonical_id(atom)
        if got != v["expected_canonical_id"]:
            mismatches.append(
                f"{v['kind']} {v['kwargs']}: got {got} "
                f"expected {v['expected_canonical_id']}"
            )
    assert not mismatches, "canonical_id drift from v06-qf golden vectors:\n" + "\n".join(
        mismatches
    )


def test_golden_ids_are_well_formed():
    for v in _load_vectors():
        cid = v["expected_canonical_id"]
        assert cid.startswith("sha256:")
        assert len(cid) == len("sha256:") + 12
