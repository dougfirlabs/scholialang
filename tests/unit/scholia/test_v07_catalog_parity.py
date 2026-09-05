"""v0.7 catalog parity — exports, kind sets, wire fields, id policy.

The proposed 0.7.3 contract requires every catalog surface to agree on
the CURRENT 35-kind set (public ``__all__``, ``_ATOM_CLASSES``,
``ATOM_KINDS``, ``KNOWN_KINDS``, ``KIND_SPECIFIC_FIELDS``, grammar
profiles) while the LEGACY 32-kind projection stays frozen and
byte-stable. The inline expectations here run unconditionally; when a
scholialang-spec checkout is available (``SCHOLIALANG_SPEC_DIR`` or a
sibling checkout), the same structures are additionally compared
field-by-field against the current normative index
``reference/v0.7/atoms_index.yaml`` — including the three
documentation-parity repairs the index records for fields the core
always had (``Observation.fingerprint``, ``Uncertainty.on``,
``Confidence.on``).
"""
from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest

import scholialang
from scholialang.atoms import (
    ATOM_KINDS,
    GRAMMAR_PROFILES,
    KIND_SPECIFIC_FIELDS,
    KNOWN_KINDS,
    LEGACY_ATOM_KINDS,
    LEGACY_GRAMMAR_VERSION,
    LEGACY_KNOWN_KINDS,
    MAP_VALUE_TYPES,
    SCHOLIA_GRAMMAR_VERSION,
    SEMANTIC_ATOM_KINDS,
    SEMANTIC_ID_PATTERNS,
    SEMANTIC_KINDS,
    SEMANTIC_REF_FIELDS,
    TASK_EVIDENCE_KINDS,
    TASK_STATUSES,
    Event,
    Map,
    Task,
    atom_class_for_kind,
    wire_name_for,
)

_SPEC_ENV = "SCHOLIALANG_SPEC_DIR"
_INDEX_SUBPATH = Path("reference") / "v0.7" / "atoms_index.yaml"


def _find_index_path() -> Path | None:
    candidates: list[Path] = []
    env = os.environ.get(_SPEC_ENV)
    if env:
        candidates.append(Path(env))
    repo_root = Path(__file__).resolve().parents[3]
    candidates.append(repo_root.parent / "scholialang-spec")
    candidates.append(repo_root.parent.parent / "scholialang-spec")
    for spec_dir in candidates:
        index = spec_dir / _INDEX_SUBPATH
        if index.is_file():
            return index
    return None


_INDEX_PATH = _find_index_path()


# ── Inline expectations (always run — no spec checkout needed) ───────


def test_current_catalog_is_exactly_35_kinds():
    assert len(ATOM_KINDS) == 35
    assert KNOWN_KINDS == frozenset(ATOM_KINDS)
    assert set(SEMANTIC_ATOM_KINDS) == {"Map", "Event", "Task"}
    assert SEMANTIC_KINDS == frozenset(SEMANTIC_ATOM_KINDS)
    assert set(ATOM_KINDS) == set(LEGACY_ATOM_KINDS) | SEMANTIC_KINDS


def test_legacy_projection_is_exactly_32_kinds():
    assert len(LEGACY_ATOM_KINDS) == 32
    assert LEGACY_KNOWN_KINDS == frozenset(LEGACY_ATOM_KINDS)
    assert not LEGACY_KNOWN_KINDS & SEMANTIC_KINDS
    # The legacy projection preserves the pre-0.7 catalog order exactly.
    assert tuple(ATOM_KINDS[:32]) == LEGACY_ATOM_KINDS


def test_grammar_profiles_agree_with_catalogs():
    assert SCHOLIA_GRAMMAR_VERSION == "0.7.0"
    assert LEGACY_GRAMMAR_VERSION == "0.6.2"
    assert GRAMMAR_PROFILES[SCHOLIA_GRAMMAR_VERSION] == KNOWN_KINDS
    assert GRAMMAR_PROFILES[LEGACY_GRAMMAR_VERSION] == LEGACY_KNOWN_KINDS
    assert set(GRAMMAR_PROFILES) == {"0.6.2", "0.7.0"}


def test_public_exports_carry_the_semantic_kinds():
    for name in (
        "Map",
        "Event",
        "Task",
        "SEMANTIC_ATOM_KINDS",
        "LEGACY_ATOM_KINDS",
        "MAP_VALUE_TYPES",
        "TASK_STATUSES",
        "SCHOLIA_GRAMMAR_VERSION",
        "LEGACY_GRAMMAR_VERSION",
        "GRAMMAR_PROFILES",
        "SemanticShapeError",
        "CanonicalCollisionError",
        "RULE_GRAMMAR_PROFILE_UNSUPPORTED",
    ):
        assert name in scholialang.__all__, f"{name} missing from __all__"
        assert hasattr(scholialang, name)
    assert scholialang.Map is Map
    assert scholialang.Event is Event
    assert scholialang.Task is Task


def test_semantic_wire_fields_are_the_contract_fields():
    assert KIND_SPECIFIC_FIELDS["Map"] == ("value_type", "entries")
    assert KIND_SPECIFIC_FIELDS["Event"] == (
        "source",
        "occurrence_id",
        "event_type",
        "timestamp",
        "for_task",
        "for_action",
        "for_goal",
        "effect_ref",
        "map_ref",
        "external_ref",
    )
    assert KIND_SPECIFIC_FIELDS["Task"] == (
        "status",
        "for_goal",
        "input_map",
        "output_map",
        "action_ref",
        "evidence_ref",
        "runtime_ref",
    )
    # Wire names are identical to field names for the new kinds (no
    # reserved-word aliasing needed).
    for kind in SEMANTIC_ATOM_KINDS:
        for field in KIND_SPECIFIC_FIELDS[kind]:
            assert wire_name_for(kind, field) == field


def test_semantic_dataclasses_carry_exactly_the_contract_fields():
    base_fields = {f.name for f in dataclasses.fields(scholialang.Atom)}
    for kind in SEMANTIC_ATOM_KINDS:
        cls = atom_class_for_kind(kind)
        assert cls is not None
        own = {
            f.name for f in dataclasses.fields(cls)
        } - base_fields
        assert own == set(KIND_SPECIFIC_FIELDS[kind]), (
            f"{kind} dataclass fields {sorted(own)} != contract "
            f"{sorted(KIND_SPECIFIC_FIELDS[kind])}"
        )


def test_closed_sets_match_the_contract():
    assert MAP_VALUE_TYPES == {"string", "integer", "boolean", "atom_ref"}
    assert TASK_STATUSES == {"open", "satisfied", "unsatisfied", "withdrawn"}
    assert TASK_EVIDENCE_KINDS == (
        "Observation",
        "Evidence",
        "Finding",
        "Concluding",
    )
    assert SEMANTIC_REF_FIELDS["Event"] == {
        "for_task": ("Task",),
        "for_action": ("Action",),
        "for_goal": ("Goal",),
        "effect_ref": ("Effect",),
        "map_ref": ("Map",),
    }
    assert SEMANTIC_REF_FIELDS["Task"] == {
        "for_goal": ("Goal",),
        "input_map": ("Map",),
        "output_map": ("Map",),
        "action_ref": ("Action",),
        "evidence_ref": TASK_EVIDENCE_KINDS,
    }


def test_semantic_id_patterns_are_kind_prefixed():
    for kind in SEMANTIC_ATOM_KINDS:
        pattern = SEMANTIC_ID_PATTERNS[kind]
        assert pattern.match(f"{kind}_01")
        assert pattern.match(f"{kind}_a_B_9")
        assert not pattern.match(f"{kind}_")
        assert not pattern.match(f"{kind.lower()}_01")
        assert not pattern.match(f"{kind}-01")
        assert not pattern.match("X" + f"{kind}_01")


def test_legacy_documentation_repair_fields_exist_on_real_core():
    """The three index documentation repairs name fields the core always
    had — they are parity repair, not new language semantics."""
    assert "fingerprint" in KIND_SPECIFIC_FIELDS["Observation"]
    assert "on" in KIND_SPECIFIC_FIELDS["Uncertainty"]
    assert "on" in KIND_SPECIFIC_FIELDS["Confidence"]


# ── Index-driven parity (runs when a spec checkout is available) ─────


@pytest.mark.skipif(
    _INDEX_PATH is None,
    reason=(
        f"current normative index not found; set {_SPEC_ENV} or place a "
        "scholialang-spec checkout beside this repo"
    ),
)
def test_current_index_kinds_and_fields_match_core():
    yaml = pytest.importorskip("yaml")
    assert _INDEX_PATH is not None
    index = yaml.safe_load(_INDEX_PATH.read_text(encoding="utf-8"))
    assert index["total_atoms"] == 35
    assert index["legacy_atoms"] == 32
    assert index["grammar_version"] == SCHOLIA_GRAMMAR_VERSION
    assert index["package_version"] == scholialang.__version__

    entries = {e["kind"]: e for e in index["atoms"]}
    assert set(entries) == set(ATOM_KINDS)

    for kind, entry in entries.items():
        attributes = entry.get("attributes") or []
        names = [a["name"] for a in attributes if isinstance(a, dict)]
        expected = ["id"] + [
            wire_name_for(kind, f) for f in KIND_SPECIFIC_FIELDS.get(kind, ())
        ]
        # Complete field parity for every kind; exact ORDER for the new
        # kinds (their table order is part of the proposed contract) —
        # legacy documentation may order its columns differently.
        assert set(names) == set(expected), (
            f"{kind}: index attributes {sorted(names)} != core wire "
            f"fields {sorted(expected)}"
        )
        if kind in SEMANTIC_ATOM_KINDS:
            assert names == expected, (
                f"{kind}: index attribute order {names} != contract "
                f"order {expected}"
            )

    for kind in SEMANTIC_ATOM_KINDS:
        policy = entries[kind].get("id_policy") or {}
        assert policy.get("required") is True
        assert policy.get("prefix") == f"{kind}_"
