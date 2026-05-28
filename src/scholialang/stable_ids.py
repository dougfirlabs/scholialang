"""Content-derived stable atom IDs for Scholia v0.4-A.

This module exposes :func:`derive_atom_id`, a pure function that maps
``(atom_kind, atom_text) → "<AtomKind>_<8hex>"``. The 8-hex suffix is a
truncated SHA-256 of the canonical text, so two atoms with the same
kind and the same canonical content always receive the same ID
regardless of when, where, or by whom they were generated.

Why this exists
---------------
Scholia v0.3 emitted document-local sequence IDs (``Goal_01``,
``Observation_03``). They were unique within a Step but **not** stable
across regeneration — a fresh Atlas sweep on the same file could
produce the same atom kinds in a different order and shift every ID.
Downstream tooling that wanted to diff atoms across sweeps could not
do so reliably.

v0.4-A derives the ID from the atom's content. Same content → same ID,
deterministically. See ``docs/scholia/STABLE_IDS.md`` for the full
stability semantic and the migration guide.

Operational definition of "stable"
----------------------------------
* **Deterministic given identical input** — strict contract. Same
  ``(kind, text)`` always returns the same ID, on any machine, at any
  time, with no environment dependence.
* **Stable across regeneration when source is unchanged** — practical
  contract. If the rewriter is deterministic and the source file
  hasn't changed, the rewriter emits the same canonical atom text on
  both sweeps and the IDs match.
* **Best-effort across non-trivial source edits** — out of scope. When
  the source changes such that the rewriter produces different prose,
  IDs drift. Downstream tooling should treat drifted IDs as new atoms.

Format
------
``<AtomKind>_<8 lowercase hex chars>`` — e.g. ``Goal_a7f3e2c1``. The
8-hex space is ``2^32`` ≈ 4.3 billion; at the typical scale
(~1,500 atoms per repo) collision probability is negligible.
"""
from __future__ import annotations

import hashlib
import re

__all__ = [
    "STABLE_ID_HEX_LENGTH",
    "STABLE_ID_RE",
    "canonicalize_text",
    "derive_atom_id",
    "is_stable_id",
    "remap_to_stable_ids",
]


STABLE_ID_HEX_LENGTH: int = 8

STABLE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*_[0-9a-f]{8}$")


_WHITESPACE_RE = re.compile(r"\s+")

# Canonical operator names per NOTATION_REFERENCE.md §4. Defined here as
# a literal tuple (rather than imported from atoms) so this module
# stays import-cycle-free with the rest of the scholia package.
_CANONICAL_OPERATORS: tuple[str, ...] = (
    "AND",
    "OR",
    "XOR",
    "NOT",
    "IMPLIES",
    "REFER",
    "FORALL",
    "EXISTS",
    "BEFORE",
    "AFTER",
    "EQUALS",
)

# Matches "OP:atom_id" tokens — operator + colon + an atom-id-shaped
# target (capital-leading identifier with at least one ``_``, matching
# the parser's operator regex but with the target portion isolated for
# stripping). Only the closed-set operators trigger; emergent operators
# (FLIP / SURFACE) are not stripped today but could be added if needed.
_OP_TARGET_RE = re.compile(
    r"\b(" + "|".join(_CANONICAL_OPERATORS) + r"):[A-Za-z][A-Za-z0-9_]*"
)


def _strip_operator_targets(text: str) -> str:
    """Replace ``OP:atom_id`` tokens with bare ``OP`` in ``text``.

    Identity invariant: an atom's stable ID must not depend on the
    specific IDs of OTHER atoms it references. We achieve that by
    stripping the ``:target`` suffix from any closed-set operator
    inside the atom's content before hashing. The operator name itself
    is preserved so an atom that says ``IMPLIES`` something is still
    distinguishable from one that says ``REFER`` something — the
    structural intent stays, only the specific target dependency drops.
    """
    return _OP_TARGET_RE.sub(lambda m: m.group(1), text)


def canonicalize_text(text: str) -> str:
    """Reduce ``text`` to its content-equivalence canonical form.

    The canonical form is the input with:

    1. ``OP:atom_id`` tokens (closed-set operator references) reduced
       to just their operator name — so an atom's identity is
       invariant under any later remapping of OTHER atoms' IDs that it
       references via REFER / IMPLIES / NOT. Without this step, the
       remap pipeline would break the downstream-recomputation
       contract: an atom stored with ``IMPLIES:Observation_a7f3e2c1``
       in its text would re-hash to a different ID than the one
       originally assigned (when content was ``IMPLIES:Observation_01``).
    2. Leading/trailing whitespace stripped.
    3. Lowercased.
    4. Internal whitespace runs (including newlines and tabs) collapsed
       to a single space.

    Two prose strings that differ only in operator-id targets, casing,
    or formatting hash to the same stable ID.
    """
    if not text:
        return ""
    text = _strip_operator_targets(text)
    return _WHITESPACE_RE.sub(" ", text.strip().lower())


def derive_atom_id(kind: str, text: str) -> str:
    """Return the stable Scholia v0.4 ID for an atom of ``kind`` + ``text``.

    Pure function. No system clock, no random seed, no environment
    inputs. The result is fully determined by the two arguments.

    Parameters
    ----------
    kind:
        The Scholia atom kind (e.g. ``"Goal"``, ``"Observation"``,
        ``"Finding"``). Used as the literal prefix in the returned ID
        so consumers can tell at a glance what kind of atom an ID
        refers to.
    text:
        The atom's content text. Whitespace and case are normalized
        before hashing — see :func:`canonicalize_text`.

    Returns
    -------
    str
        ``"<kind>_<8hex>"`` — e.g. ``"Goal_a7f3e2c1"``.

    Raises
    ------
    ValueError
        If ``kind`` is empty or not a valid identifier (must start
        with a letter and contain only letters/digits).
    """
    if not kind:
        raise ValueError("kind must be a non-empty string")
    if not kind[0].isalpha() or not all(c.isalnum() for c in kind):
        raise ValueError(
            f"kind must be a simple identifier (letters/digits, leading letter); got {kind!r}"
        )
    canonical = canonicalize_text(text)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{kind}_{digest[:STABLE_ID_HEX_LENGTH]}"


def is_stable_id(value: str) -> bool:
    """Return ``True`` if ``value`` matches the stable-ID format.

    This is a *format* check only — it does not verify that the ID
    actually derives from any particular text. Use it to distinguish
    v0.4 content-stable IDs (``Goal_a7f3e2c1``) from v0.3 sequence-
    style IDs (``Goal_01``) when migrating or routing.
    """
    if not value:
        return False
    return bool(STABLE_ID_RE.match(value))


# Reference attributes on atoms whose value is another atom's ID. Drawn
# from the validator's reference-completeness rule
# (scholialang.validator.check_reference_complete). The mapping
# pass rewrites these so that REFER/IMPLIES/NOT operators and ID-shaped
# attributes all point at the new content-stable IDs.
_REFERENCE_ATTRS: tuple[str, ...] = (
    "for_goal",
    "target",
    "for_ref",
    "next",
    "of",
    "on",
)

# Operators whose RHS is an atom ID. ``check_unknown_operator`` rejects
# anything outside this canonical set, so the remapper rewrites exactly
# these — emergent operators (FLIP / SURFACE) ride through unchanged
# because they're not used as ``OP:atom_id`` against rewriter-emitted IDs.
_REFERENCE_OPERATORS: tuple[str, ...] = ("REFER", "IMPLIES", "NOT")


def _apply_id_substitution(text: str, old: str, new: str) -> str:
    """Rewrite every reference to ``old`` (as an attribute value or as
    the RHS of a closed-set operator) into ``new`` within ``text``.

    Uses anchored regexes so that a literal occurrence of ``old`` inside
    free-form prose (e.g. someone wrote "see Goal_01 in the spec") is
    NOT silently rewritten — only structured references are touched.
    Word-boundaries around the operator RHS keep ``REFER:Goal_01`` from
    matching ``REFER:Goal_01x`` (no such IDs exist today, but the
    anchoring future-proofs the substitution against an emergent ID
    shape).
    """
    escaped_old = re.escape(old)
    # 1. id="OLD" → id="NEW" (the declaration itself)
    text = re.sub(rf'\bid="{escaped_old}"', f'id="{new}"', text)
    # 2. Structured reference attributes (for_goal="OLD" etc.)
    for attr in _REFERENCE_ATTRS:
        text = re.sub(rf'\b{attr}="{escaped_old}"', f'{attr}="{new}"', text)
    # 3. Closed-set operator references (REFER:OLD, IMPLIES:OLD, NOT:OLD)
    for op in _REFERENCE_OPERATORS:
        text = re.sub(
            rf'\b{op}:{escaped_old}(?![A-Za-z0-9_])',
            f'{op}:{new}',
            text,
        )
    return text


def remap_to_stable_ids(codeblock: str) -> tuple[str, dict[str, str]]:
    """Post-hoc rewrite of sequence-style atom IDs to content-stable IDs.

    Takes a Scholia codeblock (XML-ish text), parses it with the
    standard parser, computes a content-derived stable ID for every
    atom that has one, and rewrites the codeblock in place so all
    declarations + references use the new IDs. Returns the rewritten
    codeblock plus the ``{old_id: new_id}`` mapping for traceability.

    The Step container's own ``id`` is **left alone** — Step IDs are
    positional ("step_01" / "step_02"), not content-derived, and have
    no semantic mapping to atom content. Only atom IDs inside Steps
    are remapped.

    If parsing fails or the codeblock has no remappable IDs, returns
    ``(codeblock, {})`` unchanged. Parse errors are swallowed
    deliberately — the rewriter pipeline runs its own validator pass
    immediately after this step and that pass owns the rejection
    decision.

    Idempotent: applying the remap to an already-remapped codeblock
    returns it unchanged (the second pass derives the same IDs that
    are already in place).
    """
    if not (codeblock or "").strip():
        return codeblock, {}
    # Late import to avoid a parser → stable_ids → parser cycle.
    try:
        from scholialang.parser import ScholiaParseError, parse
    except ImportError:
        return codeblock, {}
    try:
        trace = parse(codeblock)
    except ScholiaParseError:
        return codeblock, {}
    except Exception:  # noqa: BLE001 — defensive against parser bugs
        return codeblock, {}

    mapping: dict[str, str] = {}
    for step in trace:
        for atom in step.atoms:
            for descendant in _walk(atom):
                if not descendant.id:
                    continue
                if descendant.kind == "Step":
                    # Defensive: parser doesn't nest Steps, but skip if it
                    # ever does. Step IDs stay positional.
                    continue
                if is_stable_id(descendant.id):
                    # Atom already carries a content-stable ID — we
                    # honour it verbatim so the remap is idempotent and
                    # so consumers can pin IDs explicitly when migrating
                    # an artifact by hand. We do NOT recompute and
                    # overwrite: this would create a churn loop when an
                    # atom's content contains an IMPLIES:<id> reference
                    # that was itself just remapped (the atom's text
                    # would shift on each pass, drifting its own ID).
                    continue
                mapping[descendant.id] = derive_atom_id(
                    descendant.kind, descendant.content
                )

    if not mapping:
        return codeblock, {}

    rewritten = codeblock
    for old, new in mapping.items():
        rewritten = _apply_id_substitution(rewritten, old, new)
    return rewritten, mapping


def _walk(atom):
    """Yield ``atom`` and every descendant atom in pre-order."""
    yield atom
    for child in getattr(atom, "children", []):
        yield from _walk(child)
