"""Scholia v0.6 canonical-prelude format — hash-list vs inline-transcript.

PRD-02 of the v0.6 content-addressable-IDs branch
(``rsi-scholia-v0.6-02-migration-and-ab-validation``).

The token-savings claim that motivates v0.6 is *compaction*: an agent
in session N+1 can REFER to a session-N atom by its canonical_id hash
instead of replaying the full atom XML. This module is the renderer
side of that claim — it builds the "prior atoms" prelude that the
agent sees ahead of its current task.

Three modes:

  - ``hash_only`` (v0.6 PRD-03, the maximally compact form). One line
    per atom::

        REFER:sha256:8f4a9d2c (Finding)

    No body preview at all. The agent gets only the canonical_id and
    the atom's kind label; full content is fetched on-demand at parse
    time by :func:`scholialang.parser.resolve_lazy_refs` when the
    emitted trace carries ``REFER:sha256:<cid>`` operators. Prelude
    tokens drop from ~100 chars/atom (hash_list) to ~30 chars/atom
    (hash_only) regardless of body length.

  - ``hash_list``  (v0.6 PRD-02 compact form). One line per atom::

        sha256:8f4a9d2c  (Finding) <truncated body 60 chars>

    The agent invokes a prior atom with ``REFER:sha256:8f4a9d2c`` and
    the registry resolves the hash to the full record server-side.

  - ``inline``  (v0.5 baseline). Renders each prior atom as a full
    XML element — same shape ``CanonicalRunner`` consumes today. This
    is the format the v0.6 A/B harness measures the new format against.

Pure function. No I/O during render, no LLM calls. The registry, if
supplied, is consulted only in ``hash_list`` mode to enrich the
truncated body with a registry-side preview; missing registry entries
fall back to the body from the in-memory atom list.

CLI / library shape::

    from scholialang.prelude import build_canonical_prelude
    s = build_canonical_prelude(prior_atoms, registry=reg, mode="hash_list")
"""
from __future__ import annotations

from typing import Any, Iterable, Optional, Protocol

from scholialang.atoms import (
    Atom,
    atom_to_xml,
    compute_canonical_id,
)


# Body preview length on hash_list lines. Tuned so the prelude stays
# small enough to be the win it promises (≥10× smaller than inline on
# representative input) while preserving enough text for the agent to
# recognise the atom and decide whether to REFER it.
_DEFAULT_TRUNCATE: int = 60

_VALID_MODES: frozenset[str] = frozenset({"hash_only", "hash_list", "inline"})

_HASH_ONLY_HEADER: str = (
    "Prior session atoms available via REFER:canonical_id "
    "(bodies fetched lazily at parse time):"
)
_HASH_LIST_HEADER: str = (
    "Prior session atoms available via REFER:canonical_id:"
)
_INLINE_HEADER: str = "Prior session atoms (transcript form):"


class _RegistryLike(Protocol):
    """Minimal protocol the prelude needs from a Registry-like object.

    Decoupling on duck-typing means downstream callers can pass a
    test double or an alternate store without depending on the
    concrete ``scholialang.registry.Registry`` class.
    """

    def get(self, canonical_id: str) -> Optional[dict[str, Any]]: ...


def _ensure_canonical_id(atom: Atom) -> str:
    """Return the atom's canonical_id, computing it if not yet set."""
    if atom.canonical_id is None:
        atom.canonical_id = compute_canonical_id(atom)
    return atom.canonical_id


def _preview_body(text: str, *, truncate: int) -> str:
    """One-line preview of an atom body — flattened, truncated, quoted."""
    if not text:
        return '""'
    flat = " ".join(text.split())
    if len(flat) > truncate:
        flat = flat[: max(0, truncate - 1)].rstrip() + "…"
    # Escape embedded quotes so the preview round-trips through a CLI
    # tool that splits on " characters.
    flat = flat.replace('"', '\\"')
    return f'"{flat}"'


def _resolve_body(
    atom: Atom,
    cid: str,
    registry: Optional[_RegistryLike],
) -> str:
    """Choose the body string to preview from atom + optional registry.

    Registry hits win — they're the source-of-truth for the persisted
    content; an in-memory atom can drift from the stored record. When
    the registry has no record for ``cid``, fall back to the atom's
    own body.
    """
    if registry is not None:
        record = registry.get(cid)
        if record is not None:
            stored = record.get("content")
            if isinstance(stored, str):
                return stored
    return atom.content or ""


def _render_hash_only(prior_atoms: Iterable[Atom]) -> str:
    """One line per atom: ``REFER:<cid> (<Kind>)`` — no body, no preview.

    The maximally compact rendering. The agent receives only the
    canonical_id and the kind label; the body is fetched at parse time
    by :func:`scholialang.parser.resolve_lazy_refs` when the emitted
    trace references the atom via ``REFER:sha256:<cid>``.
    """
    atoms = list(prior_atoms)
    if not atoms:
        return ""
    lines: list[str] = [_HASH_ONLY_HEADER]
    for atom in atoms:
        cid = _ensure_canonical_id(atom)
        lines.append(f"  - REFER:{cid} ({atom.kind})")
    lines.append("")  # trailing newline so the prelude composes
    return "\n".join(lines)


def _render_hash_list(
    prior_atoms: Iterable[Atom],
    registry: Optional[_RegistryLike],
    *,
    truncate: int,
) -> str:
    lines: list[str] = []
    atoms = list(prior_atoms)
    if not atoms:
        return ""
    lines.append(_HASH_LIST_HEADER)
    for atom in atoms:
        cid = _ensure_canonical_id(atom)
        body = _resolve_body(atom, cid, registry)
        preview = _preview_body(body, truncate=truncate)
        lines.append(f"  - {cid} ({atom.kind}) {preview}")
    lines.append("")  # trailing newline so the prelude composes
    return "\n".join(lines)


def _render_inline(prior_atoms: Iterable[Atom]) -> str:
    atoms = list(prior_atoms)
    if not atoms:
        return ""
    lines: list[str] = [_INLINE_HEADER, ""]
    for atom in atoms:
        lines.append(atom_to_xml(atom))
    lines.append("")
    return "\n".join(lines)


def build_canonical_prelude(
    prior_atoms: Iterable[Atom],
    registry: Optional[_RegistryLike] = None,
    mode: str = "hash_list",
    *,
    truncate: int = _DEFAULT_TRUNCATE,
) -> str:
    """Build the prior-session prelude that introduces the current turn.

    Parameters
    ----------
    prior_atoms
        Iterable of v0.5/v0.6 atoms from the prior session(s). The
        order is preserved in the output.
    registry
        Optional registry-like object. Only consulted in ``hash_list``
        mode; the body preview lifts the persisted content if a
        registry record is present, else falls back to the atom's own
        ``content``.
    mode
        ``"hash_only"`` (v0.6 PRD-03 maximally compact, no body
        previews — the body is fetched lazily at parse time),
        ``"hash_list"`` (v0.6 PRD-02 compact, with truncated previews),
        or ``"inline"`` (v0.5 baseline, full XML).
    truncate
        Body-preview character cap for ``hash_list`` mode. Bodies
        longer than ``truncate`` are cut at ``truncate - 1`` and
        suffixed with U+2026 ``…``.

    Returns
    -------
    A newline-joined prelude string ready for the agent's task slot.
    Empty input returns the empty string (no header) — callers can
    test for truthiness before splicing it into a task prompt.

    Raises
    ------
    ValueError
        If ``mode`` is not one of the two supported renderings.

    Determinism
    -----------
    Output is byte-identical for byte-identical input. The hash_list
    mode is also deterministic across processes — the canonical_id is
    the same SHA-256 prefix on every machine.
    """
    if mode not in _VALID_MODES:
        raise ValueError(
            f"prelude mode must be one of {sorted(_VALID_MODES)}; "
            f"got {mode!r}"
        )
    if mode == "hash_only":
        return _render_hash_only(prior_atoms)
    if mode == "hash_list":
        return _render_hash_list(prior_atoms, registry, truncate=truncate)
    return _render_inline(prior_atoms)


__all__ = ["build_canonical_prelude"]
