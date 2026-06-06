"""Scholia v0.6 parser — content-addressable canonical_id auto-population.

This module is the canonical import path for Scholia parsing in v0.6.
The XML structural parse continues to live in :mod:`scholialang.atoms`
(the dataclasses and the closed-set enforcement are right next to each
other there). What this module adds is the v0.6 contract:

- :func:`parse_atom` and :func:`parse_trace` always populate
  ``Atom.canonical_id`` post-construction by calling
  :func:`compute_canonical_id`.
- If the source XML already carried a ``canonical_id`` attribute (a
  v0.6 emission), the parser verifies the claimed value matches the
  recomputed hash. Mismatch behavior is gated by the ``strict`` flag:

  - ``strict=True`` raises :class:`CanonicalIdMismatch` at parse time.
  - ``strict=False`` (default) preserves the claimed value on the atom
    so the validator's ``canonical_id_well_formed`` rule can surface
    the mismatch as a structured violation rather than as an
    exception.

- :class:`CanonicalIdMismatch` is re-exported here so callers do not
  need to reach into :mod:`scholialang.atoms` for it.
- :func:`resolve_lazy_refs` (PRD-03) walks a parsed trace, finds
  ``REFER:sha256:<cid>`` operators in atom bodies, looks the canonical
  id up in a Registry-like object, and appends the resolved atom as a
  child of the referencing atom (marked with a ``resolved_from_registry``
  sidecar marker on ``Atom.operators``). This makes the
  ``mode='hash_only'`` prelude pay off — the agent ships only a
  hash; the parser hydrates the body downstream.

v0.5 traces (no ``canonical_id`` attribute on any atom) parse cleanly
under this module; every parsed atom acquires a freshly-computed
``canonical_id``, but no claimed-vs-computed comparison runs because
nothing was claimed. The substrate's portability promise becomes
operational without requiring agents to emit canonical_ids — they
still emit short local IDs and the parser does the hashing.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional, Protocol

from scholialang.atoms import (
    Atom,
    CanonicalIdMismatch,
    Trace,
    atom_class_for_kind,
    compute_canonical_id,
    parse_atom,
    parse_trace,
)


# Matches ``REFER:sha256:<hex>`` and ``IMPLIES:sha256:<hex>`` — the two
# operators that can carry a canonical_id target. Local-id REFER tokens
# (``REFER:f_01``) are deliberately ignored: those resolve within the
# trace via the validator's :func:`resolve_refer` and have no global
# identity to hydrate from the registry.
_LAZY_REF_RE: re.Pattern[str] = re.compile(
    r"\b(REFER|IMPLIES)\s*:\s*(sha256:[0-9a-f]+)"
)

# Sidecar marker pushed onto the resolved child's ``operators`` list so
# downstream consumers can tell at a glance that this atom was hydrated
# from the registry rather than emitted in-trace.
_RESOLVED_MARKER: str = "resolved_from_registry"


class _RegistryLike(Protocol):
    """Minimal protocol the lazy resolver needs from a Registry-like object."""

    def get(self, canonical_id: str) -> Optional[dict[str, Any]]: ...


def _record_to_atom(record: dict[str, Any]) -> Optional[Atom]:
    """Reconstitute an :class:`Atom` from a registry ``record`` dict.

    Returns ``None`` if the record's ``kind`` is unknown — that's a
    forward-compat case (a future Scholia version stored a kind we
    don't recognize) and the resolver swallows it as a no-op rather
    than raising.
    """
    kind = record.get("kind")
    if not isinstance(kind, str):
        return None
    atom_cls = atom_class_for_kind(kind)
    if atom_cls is None:
        return None
    kwargs: dict[str, Any] = {}
    rid = record.get("id")
    if isinstance(rid, str):
        kwargs["id"] = rid
    content = record.get("content")
    if isinstance(content, str):
        kwargs["content"] = content
    attrs = record.get("attrs") or {}
    if isinstance(attrs, dict):
        for k, v in attrs.items():
            kwargs[k] = v
    try:
        atom = atom_cls(**kwargs)
    except (TypeError, ValueError):
        # An unknown attr or a Concluding without for_goal both land
        # here — treat as resolver no-op rather than crashing the
        # caller mid-walk.
        return None
    cid = record.get("canonical_id")
    if isinstance(cid, str):
        atom.canonical_id = cid
    if _RESOLVED_MARKER not in atom.operators:
        atom.operators.append(_RESOLVED_MARKER)
    return atom


def _iter_atoms_with_parents(
    trace: Trace,
) -> Iterable[Atom]:
    """Yield every atom in ``trace`` (top-level + recursive children)."""
    pending: list[Atom] = []
    for step in trace:
        pending.extend(step.atoms)
    while pending:
        atom = pending.pop(0)
        yield atom
        pending.extend(atom.children)


def resolve_lazy_refs(
    trace: Trace,
    registry: _RegistryLike,
) -> Trace:
    """Hydrate ``REFER:sha256:<cid>`` references against ``registry``.

    Walks every atom in ``trace`` (top-level + recursive children),
    scans each atom's ``content`` for ``REFER:sha256:<cid>`` or
    ``IMPLIES:sha256:<cid>`` operator tokens, and for each canonical_id
    that resolves via ``registry.get``, appends the reconstituted atom
    as a child of the referencing atom.

    Behavior:

    - **Idempotent.** A second call is a no-op: already-hydrated
      children are detected by their ``resolved_from_registry`` marker
      on ``Atom.operators`` and skipped.
    - **Fail-soft.** A canonical_id that does not resolve in the
      registry is left untouched — the downstream validator's
      ``reference_complete`` rule surfaces the dangling REFER as a
      structured violation; the resolver itself does not raise.
    - **Pre-v0.6 safe.** Local-id REFER tokens (``REFER:f_01``) are
      ignored — only ``sha256:`` targets are treated as candidates for
      DAG lookup. A v0.5 trace passing through this function comes out
      byte-identical.

    Returns the same ``Trace`` object (mutated in place) for fluent
    chaining; the resolver does not deep-copy.
    """
    for atom in list(_iter_atoms_with_parents(trace)):
        content = atom.content or ""
        if not content:
            continue
        # Dedupe targets so a body that says "REFER:sha256:X REFER:sha256:X"
        # only hydrates once.
        seen: set[str] = set()
        for match in _LAZY_REF_RE.findall(content):
            cid = match[1]
            if cid in seen:
                continue
            seen.add(cid)
            # Skip if an existing resolved-from-registry child already
            # carries this canonical_id (idempotency).
            already_resolved = any(
                c.canonical_id == cid and _RESOLVED_MARKER in c.operators
                for c in atom.children
            )
            if already_resolved:
                continue
            record = registry.get(cid)
            if record is None:
                continue
            resolved = _record_to_atom(record)
            if resolved is None:
                continue
            atom.children.append(resolved)
    return trace


__all__ = [
    "CanonicalIdMismatch",
    "compute_canonical_id",
    "parse_atom",
    "parse_trace",
    "resolve_lazy_refs",
]
