"""Scholia v0.6 canonical-prelude format — hash-list vs inline-transcript.

PRD-02 of the v0.6 content-addressable-IDs work
(``rsi-scholia-v0.6-02-migration-and-ab-validation``). Ported into the
standalone ``scholialang`` package from the v0.6 reference implementation.

The token-savings claim that motivates v0.6 is *compaction*: an agent
in session N+1 can REFER to a session-N atom by its ``canonical_id`` hash
instead of replaying the full atom XML. This module is the renderer side
of that claim — it builds the "prior atoms" prelude the agent sees ahead
of its current task.

Three CORE v0.6 modes (the official, finalized lazy-prelude contract per
the golden-records compatibility manifest, 2026-06-06):

  - ``hash_only`` — maximally compact (~30 chars/atom). One line per atom::

        - REFER:sha256:8f4a9d2c1b3e (Finding)

    No body preview; the full content is fetched on-demand from the
    registry when the emitted trace references the atom by canonical_id.

  - ``hash_list`` — compact, with a truncated body preview (~70-100
    chars/atom). The DEFAULT mode::

        - sha256:8f4a9d2c1b3e (Finding) "truncated body …"

  - ``inline`` — the v0.5 baseline. Each prior atom rendered as a full
    XML element (the format the v0.6 A/B harness measures against).

EXPERIMENTAL recovery arms (NOT v0.6 core)
------------------------------------------
Two additional render modes — ``hash_semantic_preview`` and
``selective_inline_plus_hash_only`` — were designed by the v0.6
quality-recovery work *after* the 2026-06-06 golden-records manifest was
frozen. They are shipped here for continuity with the v0.6 reference and
its test corpus, but they are **experimental**: they are NOT part of the
finalized v0.6 lazy-prelude contract, are excluded from
:data:`CORE_PRELUDE_MODES`, and must be explicitly opted into via
``build_canonical_prelude(..., allow_experimental=True)``. Treat them as a
preview surface that may change or be removed; do not advertise them as
finalized v0.6.

Pure function. No I/O during render, no LLM calls. The registry, if
supplied, is consulted to enrich a truncated/previewed body with the
registry-side persisted content; missing registry entries fall back to
the in-memory atom body.

    from scholialang.prelude import build_canonical_prelude, CORE_PRELUDE_MODES
    s = build_canonical_prelude(prior_atoms, registry=reg, mode="hash_list")
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional, Protocol

from scholialang.atoms import (
    Atom,
    atom_to_xml,
    compute_canonical_id,
)


# Body preview length on hash_list lines. Tuned so the prelude stays
# small enough to be the win it promises (>=10x smaller than inline on
# representative input) while preserving enough text for the agent to
# recognise the atom and decide whether to REFER it.
_DEFAULT_TRUNCATE: int = 60

# ── Official v0.6 mode enumeration (golden-records manifest) ──────────
#
# CORE_PRELUDE_MODES is the canonical, finalized v0.6 lazy-prelude
# contract. ``hash_list`` is the default. Any "official modes" listing
# anywhere in the package or its docs must enumerate exactly these three.
CORE_PRELUDE_MODES: tuple[str, ...] = ("hash_only", "hash_list", "inline")

# ── Experimental recovery arms (post-manifest, NOT v0.6 core) ─────────
#
# These post-date the 2026-06-06 manifest. They are opt-in only (see the
# ``allow_experimental`` flag on build_canonical_prelude) and are kept out
# of CORE_PRELUDE_MODES on purpose. Do not surface them as finalized v0.6.
EXPERIMENTAL_PRELUDE_MODES: tuple[str, ...] = (
    "hash_semantic_preview",
    "selective_inline_plus_hash_only",
)

_CORE_MODES: frozenset[str] = frozenset(CORE_PRELUDE_MODES)
_EXPERIMENTAL_MODES: frozenset[str] = frozenset(EXPERIMENTAL_PRELUDE_MODES)
_VALID_MODES: frozenset[str] = _CORE_MODES | _EXPERIMENTAL_MODES

_HASH_ONLY_HEADER: str = (
    "Prior session atoms available via REFER:canonical_id "
    "(bodies fetched lazily at parse time):"
)
_HASH_LIST_HEADER: str = (
    "Prior session atoms available via REFER:canonical_id:"
)
_INLINE_HEADER: str = "Prior session atoms (transcript form):"
_SEMANTIC_HEADER: str = (
    "Prior session atoms available via REFER:canonical_id "
    "(semantic preview — REFER by cid to hydrate the full record):"
)
_SELECTIVE_INLINE_HEADER: str = (
    "Critical prior atoms inlined below; all other prior atoms remain "
    "available via REFER:canonical_id."
)
_SELECTIVE_REMAINDER_HEADER: str = (
    "Prior session atoms available via REFER:canonical_id:"
)

# v0.6 quality-recovery (EXPERIMENTAL). Atom kinds that carry load-bearing
# commitments — the recovery arms surface these with more context than
# bare hash refs.
_CRITICAL_KINDS: frozenset[str] = frozenset({
    "Finding", "Concluding", "Deciding", "Constraint",
})
_SEMANTIC_MAX_TITLE_WORDS: int = 8
_SEMANTIC_MAX_SUMMARY_WORDS: int = 24
_SEMANTIC_MAX_CLAIMS: int = 2
_SEMANTIC_MAX_CLAIM_WORDS: int = 14
_SEMANTIC_MAX_DEPENDS: int = 3
_SELECTIVE_MAX_INLINE_ATOMS: int = 3
_SELECTIVE_MAX_INLINE_CHARS_TOTAL: int = 900
_SELECTIVE_MAX_INLINE_CHARS_PER_ATOM: int = 320


class _RegistryLike(Protocol):
    """Minimal protocol the prelude needs from a Registry-like object.

    Decoupling on duck-typing means downstream callers can pass a test
    double or an alternate store without depending on the concrete
    :class:`scholialang.registry.Registry` class.
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
    content; an in-memory atom can drift from the stored record. When the
    registry has no record for ``cid``, fall back to the atom's own body.
    """
    if registry is not None:
        record = registry.get(cid)
        if record is not None:
            stored = record.get("content")
            if isinstance(stored, str):
                return stored
    return atom.content or ""


# ── Core v0.6 renderers ──────────────────────────────────────────────


def _render_hash_only(prior_atoms: Iterable[Atom]) -> str:
    """One line per atom: ``- REFER:<cid> (<Kind>)`` — no body, no preview."""
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
    atoms = list(prior_atoms)
    if not atoms:
        return ""
    lines: list[str] = [_HASH_LIST_HEADER]
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


# ── EXPERIMENTAL recovery-arm renderers (post-manifest, NOT v0.6 core) ─
#
# All extractors are pure string transforms over the persisted body —
# no LLM calls inside the harness (PRD: "a deterministic extractor should
# ship first to avoid adding model spend inside the benchmark"). These
# back the experimental hash_semantic_preview / selective_inline modes.


def _sentences(text: str) -> list[str]:
    """Split flattened body into sentences on . ! ? boundaries."""
    flat = " ".join((text or "").split())
    if not flat:
        return []
    out: list[str] = []
    cur: list[str] = []
    for tok in flat.split(" "):
        cur.append(tok)
        if tok.endswith((".", "!", "?")):
            out.append(" ".join(cur).strip())
            cur = []
    if cur:
        out.append(" ".join(cur).strip())
    return [s for s in out if s]


def _cap_words(text: str, max_words: int) -> str:
    words = (text or "").split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(".,;:") + "…"


def _title_label(body: str) -> str:
    sents = _sentences(body)
    first = sents[0] if sents else body
    return _cap_words(first, _SEMANTIC_MAX_TITLE_WORDS)


def _body_summary(body: str) -> str:
    return _cap_words(body, _SEMANTIC_MAX_SUMMARY_WORDS)


_CLAIM_MARKERS = (
    " must ", " should ", " require", " ensure", " guarantee",
    " never ", " always ",
)


def _key_claims(body: str) -> list[str]:
    claims: list[str] = []
    for s in _sentences(body):
        low = f" {s.lower()} "
        if any(m in low for m in _CLAIM_MARKERS):
            claims.append(_cap_words(s, _SEMANTIC_MAX_CLAIM_WORDS))
        if len(claims) >= _SEMANTIC_MAX_CLAIMS:
            break
    return claims


def _depends_on(atom: Atom, body: str) -> list[str]:
    """canonical_ids this atom REFERs/IMPLIES, deterministically extracted."""
    seen: list[str] = []
    hay = " ".join([body or "", " ".join(getattr(atom, "operators", []) or [])])
    for m in re.finditer(r"(?:REFER|IMPLIES):(sha256:[0-9a-f]{6,})", hay):
        cid = m.group(1)
        if cid not in seen:
            seen.append(cid)
        if len(seen) >= _SEMANTIC_MAX_DEPENDS:
            break
    return seen


def _criticality(atom: Atom, cid: str, registry: Optional[_RegistryLike]) -> str:
    """Atom criticality from sidecar/registry/atom attr; default 'normal'."""
    val = getattr(atom, "criticality", None)
    if isinstance(val, str) and val:
        return val
    if registry is not None:
        rec = registry.get(cid)
        if isinstance(rec, dict):
            side = rec.get("sidecar") or {}
            for key in ("criticality",):
                v = side.get(key) if isinstance(side, dict) else None
                if isinstance(v, str) and v:
                    return v
            v = (
                rec.get("attrs", {}).get("criticality")
                if isinstance(rec.get("attrs"), dict)
                else None
            )
            if isinstance(v, str) and v:
                return v
    return "normal"


def _render_hash_semantic_preview(
    prior_atoms: Iterable[Atom],
    registry: Optional[_RegistryLike],
) -> str:
    """EXPERIMENTAL — hash ref + bounded deterministic semantic cues per atom.

    Recovery arm ``hash_semantic_preview``: keeps canonical_id as the only
    dereference key, but adds summary/key_claims/depends_on/criticality so
    the next session has context before choosing refs. NOT v0.6 core.
    """
    atoms = list(prior_atoms)
    if not atoms:
        return ""
    lines: list[str] = [_SEMANTIC_HEADER]
    for atom in atoms:
        cid = _ensure_canonical_id(atom)
        body = _resolve_body(atom, cid, registry)
        crit = _criticality(atom, cid, registry)
        # cid line carries kind + criticality (no separate label lines).
        lines.append(f"  - {cid} ({atom.kind}, {crit})")
        # ONE bounded summary is the core semantic cue. A short body IS its
        # own summary; a long body is truncated to ~24 words.
        summary = _body_summary(body)
        if summary:
            lines.append(f"    summary: {summary}")
        # key_claims only when a marker-sentence carries info BEYOND the
        # summary span (avoids re-rendering the same short body twice).
        claims = [c for c in _key_claims(body) if c.rstrip("…") not in summary]
        if claims:
            lines.append(f"    claims: {'; '.join(claims)}")
        deps = _depends_on(atom, body)
        if deps:
            lines.append(f"    depends_on: [{', '.join(deps)}]")
    lines.append("")
    return "\n".join(lines)


def _is_critical(atom: Atom, cid: str, registry: Optional[_RegistryLike]) -> bool:
    if atom.kind in _CRITICAL_KINDS:
        return True
    return _criticality(atom, cid, registry) == "high"


def _selective_rank(
    idx: int, atom: Atom, cid: str, registry: Optional[_RegistryLike]
) -> tuple:
    """Selection order: criticality(high) → newest → Finding/Concluding → dep-count.

    Lower tuple sorts first. ``idx`` is position in prior_atoms (older=lower),
    so newest-first uses ``-idx``.
    """
    crit_high = 0 if _criticality(atom, cid, registry) == "high" else 1
    commit = 0 if atom.kind in ("Finding", "Concluding") else 1
    deps = len(_depends_on(atom, atom.content or ""))
    return (crit_high, -idx, commit, -deps)


def _cap_chars(text: str, max_chars: int) -> str:
    flat = " ".join((text or "").split())
    if len(flat) <= max_chars:
        return flat
    return flat[: max(0, max_chars - 1)].rstrip() + "…"


def _render_selective_inline_critical(
    prior_atoms: Iterable[Atom],
    registry: Optional[_RegistryLike],
) -> str:
    """EXPERIMENTAL — inline ≤3 critical atoms (capped chars), hash-only the rest.

    Recovery arm ``selective_inline_plus_hash_only``: full language for the
    load-bearing commitments, compression for everything else. NOT v0.6 core.
    """
    atoms = list(prior_atoms)
    if not atoms:
        return ""
    cids = [_ensure_canonical_id(a) for a in atoms]
    critical = [
        (i, a, cids[i]) for i, a in enumerate(atoms)
        if _is_critical(a, cids[i], registry)
    ]
    critical.sort(key=lambda t: _selective_rank(t[0], t[1], t[2], registry))

    inline_ids: set[str] = set()
    inline_blocks: list[str] = []
    used_chars = 0
    omitted_critical = 0
    for i, atom, cid in critical:
        if len(inline_ids) >= _SELECTIVE_MAX_INLINE_ATOMS:
            omitted_critical += 1
            continue
        body = _resolve_body(atom, cid, registry)
        rendered = (
            f'<{atom.kind} canonical_id="{cid}">\n  '
            f"{_cap_chars(body, _SELECTIVE_MAX_INLINE_CHARS_PER_ATOM)}\n"
            f"</{atom.kind}>"
        )
        if used_chars + len(rendered) > _SELECTIVE_MAX_INLINE_CHARS_TOTAL:
            omitted_critical += 1
            continue
        inline_blocks.append(rendered)
        inline_ids.add(cid)
        used_chars += len(rendered)

    lines: list[str] = []
    header = _SELECTIVE_INLINE_HEADER
    if omitted_critical:
        header += (
            f" ({omitted_critical} additional critical atom(s) omitted to "
            "hash-only by cutoff.)"
        )
    lines.append(header)
    lines.extend(inline_blocks)
    remainder = [
        (a, cids[i]) for i, a in enumerate(atoms) if cids[i] not in inline_ids
    ]
    if remainder:
        lines.append(_SELECTIVE_REMAINDER_HEADER)
        for atom, cid in remainder:
            lines.append(f"  - REFER:{cid} ({atom.kind})")
    lines.append("")
    return "\n".join(lines)


def build_canonical_prelude(
    prior_atoms: Iterable[Atom],
    registry: Optional[_RegistryLike] = None,
    mode: str = "hash_list",
    *,
    truncate: int = _DEFAULT_TRUNCATE,
    allow_experimental: bool = False,
) -> str:
    """Build the prior-session prelude that introduces the current turn.

    Parameters
    ----------
    prior_atoms
        Iterable of v0.5/v0.6 atoms from the prior session(s). Order is
        preserved in the output.
    registry
        Optional registry-like object; the body preview lifts persisted
        content when a registry record is present, else falls back to the
        atom's own ``content``.
    mode
        One of the CORE v0.6 modes — ``"hash_only"`` (maximally compact,
        no body previews), ``"hash_list"`` (compact, with truncated
        previews; the default), or ``"inline"`` (v0.5 baseline, full XML).
        The two EXPERIMENTAL recovery arms
        (``"hash_semantic_preview"``, ``"selective_inline_plus_hash_only"``)
        are accepted only when ``allow_experimental=True`` — they are NOT
        part of the finalized v0.6 contract (see :data:`CORE_PRELUDE_MODES`
        / :data:`EXPERIMENTAL_PRELUDE_MODES`).
    truncate
        Body-preview character cap for ``hash_list`` mode.
    allow_experimental
        Opt-in gate for the experimental recovery arms. Defaults to
        ``False`` so the experimental modes are never reachable by accident.

    Returns
    -------
    A newline-joined prelude string ready for the agent's task slot.
    Empty input returns the empty string (no header).

    Raises
    ------
    ValueError
        If ``mode`` is unknown, or if ``mode`` is an experimental recovery
        arm and ``allow_experimental`` is ``False``.

    Determinism
    -----------
    Output is byte-identical for byte-identical input; the canonical_id is
    the same SHA-256 prefix on every machine.
    """
    if mode not in _VALID_MODES:
        raise ValueError(
            f"prelude mode must be one of {sorted(_VALID_MODES)}; "
            f"got {mode!r}"
        )
    if mode in _EXPERIMENTAL_MODES and not allow_experimental:
        raise ValueError(
            f"mode {mode!r} is an EXPERIMENTAL recovery arm, not a v0.6 core "
            f"mode. Core modes are {list(CORE_PRELUDE_MODES)}. To use an "
            "experimental arm explicitly, pass allow_experimental=True."
        )
    if mode == "hash_only":
        return _render_hash_only(prior_atoms)
    if mode == "hash_list":
        return _render_hash_list(prior_atoms, registry, truncate=truncate)
    if mode == "inline":
        return _render_inline(prior_atoms)
    if mode == "hash_semantic_preview":
        return _render_hash_semantic_preview(prior_atoms, registry)
    if mode == "selective_inline_plus_hash_only":
        return _render_selective_inline_critical(prior_atoms, registry)
    # Unreachable — _VALID_MODES is exhaustive above.
    raise ValueError(f"unhandled prelude mode {mode!r}")  # pragma: no cover


__all__ = [
    "build_canonical_prelude",
    "CORE_PRELUDE_MODES",
    "EXPERIMENTAL_PRELUDE_MODES",
]
