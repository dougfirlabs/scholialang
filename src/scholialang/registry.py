"""Scholia v0.6 registry — DAG-backed canonical_id-keyed atom store.

PRD-03 of the v0.6 content-addressable-IDs epic
(``rsi-scholia-v0.6-03-dag-registry-and-lazy-prelude``).

PRD-01 introduced a flat-JSON store keyed by ``canonical_id``. PRD-03
replaces that flat structure with a standalone Scholia DAG backed by
the T42-vendored ``ProofChain`` shapes (``ProofNode`` / ``ProofEdge``
under :mod:`opentalon.goatchain._vendored_proofdag`). The DAG is local
to the Scholia substrate — it is *not* the T42 ProofDAG. The
``proofdag_bridge`` path that emits fragments for the T42 ingest
pipeline stays untouched.

What the DAG buys the substrate:

- Single-atom lookup (``get``/``put``/``find_by_kind``) — same public
  API as PRD-01's flat-JSON Registry. The existing 18-test PRD-01
  suite passes unchanged against the DAG-backed store.
- Relational queries on the operator graph: ``ancestors`` walks the
  premise side (atoms this one was derived from), ``descendants``
  walks the conclusion side (atoms that REFER this one),
  ``walk_chain`` returns the ``ProofChain`` rooted at a canonical_id.

Edge model:

  When atom A's body carries ``REFER:sha256:<B>`` or
  ``IMPLIES:sha256:<B>``, we emit a ``ProofEdge`` with
  ``premise_id=<B>`` and ``conclusion_id=<A>``. Semantically A is
  derived from B, so B is A's premise (basis) and A is B's conclusion
  (derived). The edge's ``inference_rule`` records the operator name
  (``REFER`` or ``IMPLIES``) so the DAG can answer "which operator
  produced this edge" without re-scanning content.

Storage shape on disk:

    {
      "version": "0.6",
      "atoms": {"sha256:<cid>": {...record...}, ...},
      "edges": [
        {"premise_id": "sha256:<B>", "conclusion_id": "sha256:<A>",
         "operator": "REFER"}, ...
      ]
    }

The ``atoms`` map is identical in shape to PRD-01 (back-compat —
old files load cleanly into the DAG-backed store; missing ``edges``
key is treated as an empty edge list). Concurrent writers serialize
through the same ``fcntl.LOCK_EX`` advisory locking as PRD-01.

Default path: ``~/.scholia/registry.proofchain.json`` — overridable
via the constructor (PRD-01's ``registry.json`` path is still
accepted; the file name is purely cosmetic).
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
from dataclasses import fields as dc_fields
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from opentalon.goatchain._vendored_proofdag import (
    DerivationMethod,
    ProofChain,
    ProofEdge,
    ProofNode,
    ProofNodeType,
)
from scholialang.atoms import Atom


_DEFAULT_REGISTRY_PATH = Path.home() / ".scholia" / "registry.proofchain.json"
_REGISTRY_FORMAT_VERSION = "0.6"

# Base-Atom bookkeeping fields excluded from the ``attrs`` slice of the
# stored record. ``kind``, ``id``, ``canonical_id``, ``content`` are
# surfaced as top-level record keys; ``children`` collapse to
# canonical_id pointers; ``operators`` are derivable from content.
_RECORD_NON_ATTR_FIELDS: frozenset[str] = frozenset({
    "id",
    "canonical_id",
    "content",
    "children",
    "operators",
})

# Map Scholia atom kinds to T42 ProofNodeType. We use DERIVED_FACT as
# the catch-all because every Scholia atom is — at minimum — a fact
# emitted during a reasoning run. The narrower mappings preserve
# semantic intent so a downstream consumer that filters by node_type
# (e.g. "show me all axioms") can do so without round-tripping back to
# atom.kind.
_KIND_TO_NODE_TYPE: dict[str, ProofNodeType] = {
    "Hypothesis": ProofNodeType.HYPOTHESIS,
    "Observation": ProofNodeType.AXIOM,
    "Goal": ProofNodeType.DEFINITION,
    "Constraint": ProofNodeType.DEFINITION,
    "Concluding": ProofNodeType.THEOREM,
    "Finding": ProofNodeType.LEMMA,
    "Evidence": ProofNodeType.DERIVED_FACT,
    "Contradiction": ProofNodeType.DERIVED_FACT,
}


def _kind_to_node_type(kind: str) -> ProofNodeType:
    """Map a Scholia atom kind to its ProofNode type. Default DERIVED_FACT."""
    return _KIND_TO_NODE_TYPE.get(kind, ProofNodeType.DERIVED_FACT)


# Scan atom bodies for inline operator targets. We accept both
# canonical_id targets (``REFER:sha256:8f4a9d2c1b3e``) and the legacy
# local-id targets (``REFER:f_01``) so pre-v0.6 traces continue to
# round-trip — but only the canonical_id matches become DAG edges,
# since local ids aren't unique across sessions.
_OP_CANONICAL_RE: re.Pattern[str] = re.compile(
    r"\b(REFER|IMPLIES)\s*:\s*(sha256:[0-9a-f]+)"
)


def _scan_operator_targets(content: str) -> list[tuple[str, str]]:
    """Return ``[(operator, canonical_id_target), ...]`` from atom body.

    Only canonical_id targets are returned — local-id REFER tokens
    don't have global identity, so they can't form DAG edges. A pre-v0.6
    body containing ``REFER:f_01`` returns an empty list here; that's
    intentional, the validator's reference_complete rule handles the
    local-id resolution inside the trace.
    """
    if not content:
        return []
    return [(m.group(1), m.group(2)) for m in _OP_CANONICAL_RE.finditer(content)]


def _atom_to_record(
    atom: Atom,
    *,
    sidecar: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Serialize ``atom`` to a JSON-friendly registry record.

    Record shape::

        {
          "kind": "Finding",
          "canonical_id": "sha256:8f4a9d2c1b3e",
          "id": "F_01",
          "content": "...",
          "attrs": {"for_hyp": "H_01", "status": "met"},
          "children_canonical_ids": ["sha256:..."],
          "sidecar": {"emitter": "claude", "session": "...", ...}
        }

    Children atoms are collapsed to their canonical_ids — the registry
    forms a DAG of canonical_id references rather than a nested tree.
    Folding child hashes into the parent is a v0.7 Merkle-DAG concern.
    """
    record: dict[str, Any] = {
        "kind": atom.kind,
        "canonical_id": atom.canonical_id,
    }
    if atom.id is not None:
        record["id"] = atom.id
    if atom.content:
        record["content"] = atom.content

    attrs: dict[str, Any] = {}
    for f in dc_fields(atom):
        if f.name in _RECORD_NON_ATTR_FIELDS:
            continue
        value = getattr(atom, f.name, None)
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        attrs[f.name] = value
    if attrs:
        record["attrs"] = attrs

    if atom.children:
        record["children_canonical_ids"] = [
            c.canonical_id for c in atom.children if c.canonical_id
        ]

    if sidecar:
        record["sidecar"] = dict(sidecar)

    return record


# ── ProofChain serialization helpers ────────────────────────────────
#
# The vendored ProofChain dataclasses don't ship with to_dict/from_dict
# — the upstream T42 module is read-only-ish (see the module docstring
# in ``opentalon.goatchain._vendored_proofdag``). These helpers live
# here so we can round-trip a walk_chain result without forking the
# vendored shape.


def chain_to_dict(chain: ProofChain) -> dict[str, Any]:
    """Serialize a :class:`ProofChain` to a plain ``dict``.

    Round-trip pair with :func:`chain_from_dict`. The output is
    JSON-safe (enums coerced to their string value; datetimes left as
    ISO strings via ``isoformat``). Use this when you want to ship the
    ProofChain over the wire or persist a snapshot.
    """
    return {
        "conclusion_id": chain.conclusion_id,
        "is_complete": chain.is_complete,
        "total_confidence": chain.total_confidence,
        "nodes": [
            {
                "node_id": n.node_id,
                "node_type": n.node_type.value,
                "content": n.content,
                "confidence": n.confidence,
                "metadata": dict(n.metadata),
            }
            for n in chain.nodes
        ],
        "edges": [
            {
                "edge_id": e.edge_id,
                "premise_id": e.premise_id,
                "conclusion_id": e.conclusion_id,
                "derivation_method": e.derivation_method.value,
                "inference_rule": e.inference_rule,
                "confidence": e.confidence,
                "metadata": dict(e.metadata),
            }
            for e in chain.edges
        ],
    }


def chain_from_dict(data: dict[str, Any]) -> ProofChain:
    """Rebuild a :class:`ProofChain` from a :func:`chain_to_dict` payload."""
    nodes = [
        ProofNode(
            node_id=n.get("node_id", ""),
            node_type=ProofNodeType(n.get("node_type", "DERIVED_FACT")),
            content=n.get("content", ""),
            confidence=float(n.get("confidence", 0.0)),
            metadata=dict(n.get("metadata", {})),
        )
        for n in data.get("nodes", [])
    ]
    edges = [
        ProofEdge(
            edge_id=e.get("edge_id", ""),
            premise_id=e.get("premise_id", ""),
            conclusion_id=e.get("conclusion_id", ""),
            derivation_method=DerivationMethod(
                e.get("derivation_method", "UNKNOWN")
            ),
            inference_rule=e.get("inference_rule", ""),
            confidence=float(e.get("confidence", 0.0)),
            metadata=dict(e.get("metadata", {})),
        )
        for e in data.get("edges", [])
    ]
    return ProofChain(
        conclusion_id=data.get("conclusion_id", ""),
        nodes=nodes,
        edges=edges,
        is_complete=bool(data.get("is_complete", False)),
        total_confidence=float(data.get("total_confidence", 0.0)),
    )


class Registry:
    """DAG-backed file-backed canonical_id store.

    On disk::

        {
          "version": "0.6",
          "atoms": {"sha256:<cid>": {...record...}, ...},
          "edges": [{"premise_id", "conclusion_id", "operator"}, ...]
        }

    In-memory, atoms live as a dict keyed by canonical_id (same as
    PRD-01); edges live as a list of dicts that ``ancestors`` /
    ``descendants`` / ``walk_chain`` traverse. A coarse-grained
    lock-and-rewrite remains acceptable for v0.6 throughput; a future
    v0.7 Merkle-DAG would warrant log-structured storage.
    """

    def __init__(self, path: Optional[Path | str] = None) -> None:
        self.path = Path(path) if path is not None else _DEFAULT_REGISTRY_PATH
        self._lock_path = Path(str(self.path) + ".lock")
        self._cache: dict[str, dict[str, Any]] = {}
        self._edges: list[dict[str, str]] = []
        self._cache_loaded = False

    # ── Internal helpers ────────────────────────────────────────────

    def _read_disk(self) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
        if not self.path.exists():
            return {}, []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}, []
        atoms = payload.get("atoms", {})
        if not isinstance(atoms, dict):
            atoms = {}
        edges_raw = payload.get("edges", [])
        edges: list[dict[str, str]] = []
        if isinstance(edges_raw, list):
            for e in edges_raw:
                if (
                    isinstance(e, dict)
                    and "premise_id" in e
                    and "conclusion_id" in e
                ):
                    edges.append(
                        {
                            "premise_id": str(e["premise_id"]),
                            "conclusion_id": str(e["conclusion_id"]),
                            "operator": str(e.get("operator", "REFER")),
                        }
                    )
        return atoms, edges

    def _write_disk(
        self,
        atoms: dict[str, dict[str, Any]],
        edges: list[dict[str, str]],
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = Path(str(self.path) + ".tmp")
        payload = {
            "version": _REGISTRY_FORMAT_VERSION,
            "atoms": atoms,
            "edges": edges,
        }
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, sort_keys=True, separators=(",", ":"))
        os.replace(tmp_path, self.path)

    @contextlib.contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, "w", encoding="utf-8") as lock_fd:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)

    def _ensure_loaded(self) -> None:
        if self._cache_loaded:
            return
        self._cache, self._edges = self._read_disk()
        self._cache_loaded = True

    def _new_edges_for(self, atom: Atom) -> list[dict[str, str]]:
        """Return the canonical-id edges that ``atom``'s body declares."""
        if atom.canonical_id is None:
            return []
        new_edges: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for operator, target_cid in _scan_operator_targets(atom.content):
            key = (target_cid, atom.canonical_id, operator)
            if key in seen:
                continue
            seen.add(key)
            new_edges.append(
                {
                    "premise_id": target_cid,
                    "conclusion_id": atom.canonical_id,
                    "operator": operator,
                }
            )
        return new_edges

    # ── Public API — back-compat with PRD-01 ────────────────────────

    def put(
        self,
        atom: Atom,
        *,
        sidecar: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Append ``atom`` under its canonical_id. Idempotent.

        Returns ``True`` if newly inserted, ``False`` if the
        canonical_id was already present. Edge emission is best-effort:
        if ``atom.content`` carries ``REFER:sha256:<B>`` or
        ``IMPLIES:sha256:<B>`` operators, an edge is appended for each
        canonical_id target. Edges are de-duplicated by
        ``(premise_id, conclusion_id, operator)``.

        Raises ``ValueError`` if ``atom.canonical_id`` is not set —
        callers must parse through :func:`scholialang.parser.parse_trace`
        or call :func:`scholialang.atoms.compute_canonical_id` first.
        """
        if atom.canonical_id is None:
            raise ValueError(
                "Registry.put requires atom.canonical_id to be set; "
                "parse through scholialang.parser.parse_trace or call "
                "scholialang.atoms.compute_canonical_id(atom) first."
            )
        with self._exclusive_lock():
            # Re-read under lock so concurrent put()s from other
            # processes don't lose each other's writes.
            data, edges = self._read_disk()
            if atom.canonical_id in data:
                self._cache = data
                self._edges = edges
                self._cache_loaded = True
                return False
            data[atom.canonical_id] = _atom_to_record(atom, sidecar=sidecar)

            existing_keys = {
                (e["premise_id"], e["conclusion_id"], e.get("operator", "REFER"))
                for e in edges
            }
            for new_edge in self._new_edges_for(atom):
                key = (
                    new_edge["premise_id"],
                    new_edge["conclusion_id"],
                    new_edge["operator"],
                )
                if key in existing_keys:
                    continue
                existing_keys.add(key)
                edges.append(new_edge)

            self._write_disk(data, edges)
            self._cache = data
            self._edges = edges
            self._cache_loaded = True
        return True

    def get(self, canonical_id: str) -> Optional[dict[str, Any]]:
        """Look up a record by canonical_id. Returns the JSON record dict."""
        self._ensure_loaded()
        return self._cache.get(canonical_id)

    def list_canonical_ids(
        self,
        filter: Optional[str] = None,
    ) -> Iterable[str]:
        """Yield every stored canonical_id, optionally substring-filtered."""
        self._ensure_loaded()
        for cid in self._cache:
            if filter is None or filter in cid:
                yield cid

    def find_by_kind(self, kind: str) -> Iterable[dict[str, Any]]:
        """Yield every stored record whose ``kind`` matches."""
        self._ensure_loaded()
        for record in self._cache.values():
            if record.get("kind") == kind:
                yield record

    def reload(self) -> None:
        """Drop the in-memory cache and re-read from disk on next access."""
        self._cache_loaded = False
        self._cache = {}
        self._edges = []

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._cache)

    def __contains__(self, canonical_id: object) -> bool:
        self._ensure_loaded()
        return canonical_id in self._cache

    # ── DAG queries — PRD-03 extension ──────────────────────────────

    def ancestors(
        self,
        canonical_id: str,
        *,
        depth: Optional[int] = None,
    ) -> Iterable[dict[str, Any]]:
        """Atoms reachable backward via REFER/IMPLIES edges.

        An ancestor of ``A`` is an atom ``A`` was derived from — i.e.
        an atom referenced (as premise) by ``A`` or by an atom in
        ``A``'s ancestor closure. ``depth=1`` returns only direct
        premises; ``depth=None`` returns the full transitive closure.

        Yields record dicts in BFS order. Atoms whose canonical_id is
        referenced but never ``put`` into the registry are silently
        skipped — the edge exists, but there is no record to yield.
        """
        return self._walk_edges(
            canonical_id,
            direction="ancestors",
            depth=depth,
        )

    def descendants(
        self,
        canonical_id: str,
        *,
        depth: Optional[int] = None,
    ) -> Iterable[dict[str, Any]]:
        """Atoms reachable forward via REFER/IMPLIES edges.

        A descendant of ``B`` is an atom whose body REFERs ``B`` (or
        whose body REFERs an atom that REFERs ``B``, transitively).
        ``depth=1`` returns only direct referrers; ``depth=None``
        returns the full transitive closure.

        Yields record dicts in BFS order. Atoms whose canonical_id is
        referenced but never ``put`` into the registry are silently
        skipped.
        """
        return self._walk_edges(
            canonical_id,
            direction="descendants",
            depth=depth,
        )

    def _walk_edges(
        self,
        canonical_id: str,
        *,
        direction: str,
        depth: Optional[int],
    ) -> list[dict[str, Any]]:
        """BFS walker shared by ``ancestors`` / ``descendants``.

        ``direction='ancestors'`` follows ``conclusion_id == current``
        edges (the current node is the conclusion; the premise is
        older). ``direction='descendants'`` follows ``premise_id ==
        current`` edges (the current node is the premise; the
        conclusion is newer).
        """
        self._ensure_loaded()

        # Build adjacency once per query — cheap for v0.6 corpora and
        # avoids stale-cache concerns when atoms are added between
        # successive queries.
        adjacency: dict[str, set[str]] = {}
        for edge in self._edges:
            if direction == "ancestors":
                src = edge["conclusion_id"]
                dst = edge["premise_id"]
            else:
                src = edge["premise_id"]
                dst = edge["conclusion_id"]
            adjacency.setdefault(src, set()).add(dst)

        visited: set[str] = set()
        ordered: list[str] = []
        frontier: list[tuple[str, int]] = [(canonical_id, 0)]
        while frontier:
            current, current_depth = frontier.pop(0)
            if depth is not None and current_depth >= depth:
                neighbors: set[str] = set()
            else:
                neighbors = adjacency.get(current, set())
            for nxt in neighbors:
                if nxt in visited or nxt == canonical_id:
                    continue
                visited.add(nxt)
                ordered.append(nxt)
                frontier.append((nxt, current_depth + 1))

        return [self._cache[cid] for cid in ordered if cid in self._cache]

    def walk_chain(self, canonical_id: str) -> ProofChain:
        """Return the :class:`ProofChain` rooted at ``canonical_id``.

        The returned chain contains:

        - The node identified by ``canonical_id`` (if stored), plus
          every ancestor reachable via REFER/IMPLIES edges.
        - Every edge whose ``conclusion_id`` is in the included node
          set (i.e. the edges that derived this subgraph).

        The chain's ``conclusion_id`` is the input ``canonical_id``;
        ``is_complete`` is set to ``True`` when every premise referenced
        by an included edge is also an included node. The result
        round-trips through :func:`chain_to_dict` /
        :func:`chain_from_dict`.
        """
        self._ensure_loaded()

        included: dict[str, dict[str, Any]] = {}
        if canonical_id in self._cache:
            included[canonical_id] = self._cache[canonical_id]
        for record in self.ancestors(canonical_id):
            cid = record.get("canonical_id")
            if cid:
                included[cid] = record

        nodes: list[ProofNode] = []
        for cid, record in included.items():
            nodes.append(
                ProofNode(
                    node_id=cid,
                    node_type=_kind_to_node_type(record.get("kind", "")),
                    content=str(record.get("content", "")),
                    metadata={"scholia_record": record},
                )
            )

        included_edges: list[ProofEdge] = []
        is_complete = True
        for edge in self._edges:
            if edge["conclusion_id"] not in included:
                continue
            if edge["premise_id"] not in included:
                # Edge points outside the included subgraph — the chain
                # is technically incomplete because we didn't include
                # this premise. Carry the edge through anyway; the
                # validator can decide what to do with the dangling
                # reference.
                is_complete = False
            included_edges.append(
                ProofEdge(
                    edge_id=f"{edge['premise_id']}->{edge['conclusion_id']}",
                    premise_id=edge["premise_id"],
                    conclusion_id=edge["conclusion_id"],
                    inference_rule=edge.get("operator", "REFER"),
                )
            )

        return ProofChain(
            conclusion_id=canonical_id,
            nodes=nodes,
            edges=included_edges,
            is_complete=is_complete,
        )

    def to_proof_chain(self) -> ProofChain:
        """Return the entire registry as a single :class:`ProofChain`.

        Useful for snapshot/serialization paths that want the whole DAG
        in one shape. The ``conclusion_id`` is empty because the chain
        has no single conclusion.
        """
        self._ensure_loaded()
        nodes = [
            ProofNode(
                node_id=cid,
                node_type=_kind_to_node_type(record.get("kind", "")),
                content=str(record.get("content", "")),
                metadata={"scholia_record": record},
            )
            for cid, record in self._cache.items()
        ]
        edges = [
            ProofEdge(
                edge_id=f"{e['premise_id']}->{e['conclusion_id']}",
                premise_id=e["premise_id"],
                conclusion_id=e["conclusion_id"],
                inference_rule=e.get("operator", "REFER"),
            )
            for e in self._edges
        ]
        return ProofChain(
            conclusion_id="",
            nodes=nodes,
            edges=edges,
            is_complete=False,
        )


__all__ = [
    "Registry",
    "chain_to_dict",
    "chain_from_dict",
]
