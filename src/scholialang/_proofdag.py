"""Self-contained proof-DAG shapes for the v0.6 Scholia registry.

⚠️  v0.6 HOTFIX STUB — pending Darren's canonical PRD.

The v0.6 reference implementation backs its DAG registry with OpenTalon's
T42-vendored ``ProofChain`` shapes (``opentalon.goatchain._vendored_proofdag``).
The standalone ``scholialang`` package must not depend on OpenTalon, so this
module provides a minimal, field-compatible stand-in: the same dataclass
field names and enum value strings the registry's ``walk_chain`` /
``to_proof_chain`` / ``chain_to_dict`` / ``chain_from_dict`` paths use, so a
serialized chain is shape-identical across implementations.

This is deliberately the *least* load-bearing part of the v0.6 port — the
registry's on-disk format (``{version, atoms, edges}``) does not reference
these shapes at all; they are only the in-memory return type of the DAG
query methods. When Darren's canonical DAG spec lands, this shim is the
single file to reconcile.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProofNodeType(str, Enum):
    """Coarse classification of a proof node. Value strings match the
    upstream T42 ``ProofNodeType`` so ``chain_to_dict`` output is
    cross-implementation stable."""

    AXIOM = "AXIOM"
    DEFINITION = "DEFINITION"
    HYPOTHESIS = "HYPOTHESIS"
    LEMMA = "LEMMA"
    THEOREM = "THEOREM"
    DERIVED_FACT = "DERIVED_FACT"


class DerivationMethod(str, Enum):
    """How a conclusion was derived from its premises."""

    UNKNOWN = "UNKNOWN"
    DEDUCTION = "DEDUCTION"
    INDUCTION = "INDUCTION"
    ABDUCTION = "ABDUCTION"


@dataclass
class ProofNode:
    node_id: str = ""
    node_type: ProofNodeType = ProofNodeType.DERIVED_FACT
    content: str = ""
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProofEdge:
    edge_id: str = ""
    premise_id: str = ""
    conclusion_id: str = ""
    derivation_method: DerivationMethod = DerivationMethod.UNKNOWN
    inference_rule: str = ""
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProofChain:
    conclusion_id: str = ""
    nodes: list[ProofNode] = field(default_factory=list)
    edges: list[ProofEdge] = field(default_factory=list)
    is_complete: bool = False
    total_confidence: float = 0.0


__all__ = [
    "ProofNodeType",
    "DerivationMethod",
    "ProofNode",
    "ProofEdge",
    "ProofChain",
]
