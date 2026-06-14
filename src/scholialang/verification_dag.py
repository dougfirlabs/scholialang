"""Self-contained verification-DAG shapes for the v0.6 Scholia registry.

v0.6 compatibility shim — pending the canonical verification-DAG spec.

The v0.6 reference implementation backs its registry with a content-addressed
DAG of verification relationships — a ``VerificationDag`` shape, not a linear
chain. The standalone ``scholialang`` package keeps this dependency-free, so
this module provides a minimal, field-compatible stand-in: the same dataclass
field names and enum value strings the registry's ``walk_dag`` /
``to_verification_dag`` / ``dag_to_dict`` / ``dag_from_dict`` paths use, so a
serialized DAG is shape-identical across implementations.

This is deliberately the *least* load-bearing part of the v0.6 port — the
registry's on-disk format (``{version, atoms, edges}``) does not reference
these shapes at all; they are only the in-memory return type of the
query methods. When the canonical verification-DAG spec lands, this shim is
the single file to reconcile.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProofNodeType(str, Enum):
    """Coarse classification of a proof node. Value strings match the
    upstream ``ProofNodeType`` so ``dag_to_dict`` output is
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
class VerificationDag:
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
    "VerificationDag",
]
