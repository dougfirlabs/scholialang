"""Scholia serializers — AST ↔ JSON ↔ YAML.

JSON is the canonical machine format; YAML is the config-friendly
twin. Both are lossless round-trips per NOTATION_REFERENCE.md §10b/c
— a trace serialised and parsed back is bit-identical under canonical
key ordering (see :func:`to_canonical_json`).

Why a separate canonical form: the enforcement layer hashes trace
bytes via ``content hashing`` to produce a content
address. Hashing arbitrary JSON whitespace + key order is brittle;
``to_canonical_json`` pins both so the hash is stable across agent
runs and across serializer versions.

YAML support leans on PyYAML's ``safe_dump`` / ``safe_load`` so no
arbitrary Python objects reconstitute. Every atom kind roundtrips
through both paths — exercised end-to-end in the unit tests.
"""
from __future__ import annotations

import json
from typing import Any

import yaml

from scholialang.atoms import (
    KIND_SPECIFIC_FIELDS,
    PSEUDO_ATOM_KINDS,
    Atom,
    Step,
    atom_class_for_kind,
    wire_name,
)


# ── Atom → dict ──────────────────────────────────────────────────────


def _atom_to_dict(atom: Atom) -> dict[str, Any]:
    """Convert an atom dataclass into a plain dict for serialization.

    Key order is stable: ``kind`` first (so the dispatch is cheap on
    read), then common fields, then kind-specific fields. Empty
    collections are emitted as empty — a parsed-then-serialized atom
    should equal its source for the roundtrip invariant, and that
    means not dropping fields based on content.
    """
    out: dict[str, Any] = {"kind": atom.kind}
    if atom.id is not None:
        out["id"] = atom.id
    out["content"] = atom.content
    out["operators"] = list(atom.operators)
    for field_name in KIND_SPECIFIC_FIELDS.get(atom.kind, ()):
        value = getattr(atom, field_name)
        if isinstance(value, list):
            out[wire_name(field_name)] = list(value)
        else:
            out[wire_name(field_name)] = value
    if atom.children:
        out["children"] = [_atom_to_dict(c) for c in atom.children]
    else:
        out["children"] = []
    return out


def _step_to_dict(step: Step) -> dict[str, Any]:
    """Convert a ``Step`` into a dict with the §10b shape."""
    out: dict[str, Any] = {}
    if step.id is not None:
        out["id"] = step.id
    if step.name is not None:
        out["name"] = step.name
    out["atoms"] = [_atom_to_dict(a) for a in step.atoms]
    return out


def trace_to_dict(
    trace: list[Step], *, trace_id: str | None = None
) -> dict[str, Any]:
    """Convert a full trace into the §10b JSON-shaped dict."""
    out: dict[str, Any] = {}
    if trace_id is not None:
        out["trace_id"] = trace_id
    out["steps"] = [_step_to_dict(s) for s in trace]
    return out


# ── dict → Atom ──────────────────────────────────────────────────────


def _atom_from_dict(payload: dict[str, Any]) -> Atom:
    """Reconstruct the right atom dataclass from a dict payload."""
    kind = payload.get("kind")
    if not isinstance(kind, str):
        raise ValueError(
            "Scholia atom dict missing 'kind' discriminator."
        )
    cls = atom_class_for_kind(kind)
    if cls is None:
        if kind not in PSEUDO_ATOM_KINDS:
            raise ValueError(f"Unknown Scholia atom kind: {kind!r}")
        atom = Atom()
        atom.kind = kind
    elif kind == "Concluding":
        atom = cls(for_goal=payload.get("for_goal"))
    else:
        atom = cls()
    atom.id = payload.get("id")
    atom.content = str(payload.get("content", ""))
    atom.operators = list(payload.get("operators", []))
    for field_name in KIND_SPECIFIC_FIELDS.get(kind, ()):
        wire_key = wire_name(field_name)
        if wire_key in payload:
            if (
                kind == "Finding"
                and field_name == "for_goal"
                and "for_hyp" not in payload
            ):
                setattr(atom, "for_hyp", payload[wire_key])
            else:
                setattr(atom, field_name, payload[wire_key])
    atom.children = [_atom_from_dict(c) for c in payload.get("children", [])]
    return atom


def _step_from_dict(payload: dict[str, Any]) -> Step:
    return Step(
        id=payload.get("id"),
        name=payload.get("name"),
        atoms=[_atom_from_dict(a) for a in payload.get("atoms", [])],
    )


def trace_from_dict(payload: dict[str, Any]) -> list[Step]:
    """Reconstruct a trace from the §10b JSON-shaped dict."""
    steps_raw = payload.get("steps", [])
    if not isinstance(steps_raw, list):
        raise ValueError("Scholia trace dict must carry a list 'steps'.")
    return [_step_from_dict(s) for s in steps_raw]


# ── JSON ─────────────────────────────────────────────────────────────


def to_json(
    trace: list[Step],
    *,
    trace_id: str | None = None,
    indent: int | None = 2,
) -> str:
    """Serialize a trace to JSON (non-canonical — readable)."""
    payload = trace_to_dict(trace, trace_id=trace_id)
    return json.dumps(payload, indent=indent, ensure_ascii=False)


def to_canonical_json(
    trace: list[Step], *, trace_id: str | None = None
) -> str:
    """Serialize with sorted keys + compact separators — hashing input.

    Canonical form is deterministic across Python versions: same
    trace always produces byte-identical output. The enforcement
    layer feeds this string to ``goat_hash`` so a trace's
    ``content_hash`` field is reproducible by an auditor who only has
    the AST.
    """
    payload = trace_to_dict(trace, trace_id=trace_id)
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def from_json(text: str) -> list[Step]:
    """Parse a JSON trace string back into Steps."""
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Scholia JSON trace must be a top-level object.")
    return trace_from_dict(payload)


# ── YAML ─────────────────────────────────────────────────────────────


def to_yaml(
    trace: list[Step], *, trace_id: str | None = None
) -> str:
    """Serialize a trace to YAML via ``safe_dump``."""
    payload = trace_to_dict(trace, trace_id=trace_id)
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def from_yaml(text: str) -> list[Step]:
    """Parse a YAML trace string back into Steps."""
    payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError("Scholia YAML trace must be a top-level mapping.")
    return trace_from_dict(payload)
