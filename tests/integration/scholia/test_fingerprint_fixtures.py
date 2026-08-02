"""Shared fingerprint= fixture consumption — scholialang-spec, no forks.

The ``fingerprint`` corpus lives ONCE in ``scholialang-spec`` at
``tests/fixtures/fingerprint/`` (proposal: ``docs/scholia/FINGERPRINT.md``).
Per the contract, implementations CONSUME that single copy rather than
vendoring a fork. This suite locates the spec fixtures and drives the two
layers the manifest distinguishes:

* **notation** — the ``fingerprint_well_formed`` rule, decided on the trace
  alone (no source access). This repo's validator OWNS this layer, so these
  assertions are executable here: ``notation_valid: true`` fixtures must carry
  no ``fingerprint_well_formed`` error; ``notation_valid: false`` fixtures must.
* **consumer** — the verifies / rebinds / span_mismatch / stale verdicts,
  which recompute the digest over source using 52X-B2's single definition.
  A notation validator has NO repo access, so those verdicts are NOT computed
  here (§3/§5); we only assert the notation layer for consumer-layer fixtures
  and record their declared verdict.

The spec repo is a sibling checkout in CI (the spec-conformance workflow
clones it to ``../scholialang-spec``) and in local dev. When it is not
present the whole module SKIPS — the fixtures are shared, not forked, so
their absence is a missing-dependency skip, never a copied-in fallback.

Point the suite at an explicit checkout with ``SCHOLIALANG_SPEC_DIR``.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scholialang.parser import parse
from scholialang.validator import RULE_FINGERPRINT_WELL_FORMED, validate

yaml = pytest.importorskip("yaml")


_SPEC_ENV = "SCHOLIALANG_SPEC_DIR"
_FIXTURE_SUBPATH = Path("tests") / "fixtures" / "fingerprint"


def _candidate_spec_dirs() -> list[Path]:
    """Ordered spec-checkout candidates: env override, then sibling repos."""
    candidates: list[Path] = []
    env = os.environ.get(_SPEC_ENV)
    if env:
        candidates.append(Path(env))
    repo_root = Path(__file__).resolve().parents[3]
    candidates.append(repo_root.parent / "scholialang-spec")
    candidates.append(repo_root.parent.parent / "scholialang-spec")
    return candidates


def _find_fixture_dir() -> Path | None:
    for spec_dir in _candidate_spec_dirs():
        fixtures = spec_dir / _FIXTURE_SUBPATH
        if (fixtures / "manifest.yaml").is_file():
            return fixtures
    return None


_FIXTURE_DIR = _find_fixture_dir()

pytestmark = pytest.mark.skipif(
    _FIXTURE_DIR is None,
    reason=(
        f"scholialang-spec fingerprint fixtures not found; set {_SPEC_ENV} or "
        "place a scholialang-spec checkout beside this repo (shared corpus, "
        "no in-repo fork)."
    ),
)


def _manifest() -> dict:
    assert _FIXTURE_DIR is not None
    return yaml.safe_load((_FIXTURE_DIR / "manifest.yaml").read_text(encoding="utf-8"))


def _fixtures() -> list[dict]:
    return list(_manifest().get("fixtures", []))


def _fixture_ids() -> list[str]:
    return [f["name"] for f in _fixtures()]


def test_manifest_declares_the_expected_corpus():
    """The shared corpus carries the positive + negative fixtures the
    contract names (guards against consuming a truncated/renamed copy)."""
    manifest = _manifest()
    assert manifest.get("attribute") == "fingerprint"
    assert manifest.get("well_formed_regex") == r"^[a-z0-9]+:[0-9a-f]+$"
    names = set(_fixture_ids())
    assert {
        "valid_fingerprint",
        "moved_symbol_rebind",
        "ignore_if_absent",
        "malformed_hash",
        "span_mismatch",
        "stale_fingerprint",
    } <= names


@pytest.mark.parametrize("fixture", _fixtures(), ids=_fixture_ids())
def test_shared_fixture_notation_layer(fixture: dict) -> None:
    """Every shared fixture's NOTATION verdict matches this validator.

    ``notation_valid`` in the manifest is exactly the ``fingerprint_well_formed``
    outcome: ``true`` → no rule error; ``false`` → at least one. Consumer-layer
    verdicts (rebinds / span_mismatch / stale) are not decided here.
    """
    assert _FIXTURE_DIR is not None
    trace = parse((_FIXTURE_DIR / fixture["trace"]).read_text(encoding="utf-8"))
    result = validate(trace)
    fp_errors = result.errors_by_rule[RULE_FINGERPRINT_WELL_FORMED]

    if fixture["notation_valid"]:
        assert fp_errors == [], (
            f"{fixture['name']}: expected notation-valid, got "
            f"{[e.message for e in fp_errors]}"
        )
    else:
        assert fp_errors, (
            f"{fixture['name']}: expected a fingerprint_well_formed hard-fail"
        )


def test_ignore_if_absent_strips_losslessly() -> None:
    """The older-validator-tolerance demonstrator: stripping every
    ``fingerprint=`` yields a trace that parses + validates clean under this
    validator, and whose atoms keep the same canonical_id (non-load-bearing,
    §4.1)."""
    assert _FIXTURE_DIR is not None
    raw = (_FIXTURE_DIR / "positive" / "ignore_if_absent.xml").read_text(
        encoding="utf-8"
    )
    assert 'fingerprint="' in raw  # the fixture actually exercises the attribute

    import re

    stripped = re.sub(r'\s+fingerprint="[^"]*"', "", raw)
    assert 'fingerprint="' not in stripped

    with_fp = parse(raw)
    without_fp = parse(stripped)

    assert validate(without_fp).ok
    assert validate(with_fp).errors_by_rule[RULE_FINGERPRINT_WELL_FORMED] == []

    fp_cids = [a.canonical_id for s in with_fp for a in s.atoms]
    plain_cids = [a.canonical_id for s in without_fp for a in s.atoms]
    assert fp_cids == plain_cids


def test_malformed_hash_is_the_only_negative_notation_fixture() -> None:
    """Exactly the ``malformed_hash`` fixture fails the notation layer; the
    other negatives (span_mismatch, stale) are consumer-layer and stay
    notation-valid."""
    notation_failures = {
        f["name"] for f in _fixtures() if not f["notation_valid"]
    }
    assert notation_failures == {"malformed_hash"}
