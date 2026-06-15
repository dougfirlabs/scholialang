"""v0.3.1 corpus-replay regression — backwards-compat with v0.3 atoms.

The promise of v0.3.1 is that every v0.3 atom that validated before
this release MUST validate after it. This test walks the known-good
v0.3 corpus fixture set + the v0.3.1 fixture set (atoms that populate
the new optional fields) and asserts 100% validation pass.

If this test breaks, the v0.3.1 release has regressed the backwards-
compatibility promise; the offending change is not safe to ship.

For full-corpus replay against a real production sweep, set
``SCHOLIA_CORPUS_DIR`` to a directory of ``.xml`` traces;
``test_external_corpus_*`` walks every file under it and asserts a
configurable failure-rate ceiling. This keeps the committed fixture set
small while still letting operators gate on real-world artifacts.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scholialang.parser import ScholiaParseError, parse
from scholialang.validator import (
    SCHOLIA_VALIDATOR_VERSION,
    validate,
)


_FIXTURES_ROOT = Path(__file__).parent.parent.parent / "fixtures" / "scholia"
_V03_CORPUS = _FIXTURES_ROOT / "v03_known_corpus"
_V031_CORPUS = _FIXTURES_ROOT / "v031_atoms"
_EXTERNAL_CORPUS_ENV = "SCHOLIA_CORPUS_DIR"
_EXTERNAL_FAILURE_CEILING_ENV = "SCHOLIA_CORPUS_FAILURE_CEILING"


def _xml_fixtures(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.suffix == ".xml")


@pytest.mark.parametrize("fixture", _xml_fixtures(_V03_CORPUS), ids=lambda p: p.name)
def test_v0_3_known_corpus_validates_under_v031(fixture: Path) -> None:
    """Every v0.3-shape fixture validates under the v0.3.1 validator.

    This is the load-bearing regression: the 1,529-atom production sweep
    won't be checked in as a fixture, but this representative sample
    exercises the same shapes the sweep produced (Goal/Finding,
    Hypothesis/Evidence, Deciding/Branch, research-mode marker, and
    inline operators). If any of these break, the larger corpus
    would also break.
    """
    text = fixture.read_text(encoding="utf-8")
    trace = parse(text)
    result = validate(trace)
    assert result.ok, (
        f"{fixture.name} regressed v0.3 backwards-compat: {result.summary()} "
        f"errors={[e.message for e in result.errors]}"
    )
    assert result.scholia_validator_version == SCHOLIA_VALIDATOR_VERSION


@pytest.mark.parametrize("fixture", _xml_fixtures(_V031_CORPUS), ids=lambda p: p.name)
def test_v0_3_1_fixtures_validate(fixture: Path) -> None:
    """Every v0.3.1-shape fixture (atoms WITH new optional fields) validates."""
    text = fixture.read_text(encoding="utf-8")
    trace = parse(text)
    result = validate(trace)
    assert result.ok, (
        f"{fixture.name} failed v0.3.1 validation: {result.summary()} "
        f"errors={[e.message for e in result.errors]}"
    )
    assert result.scholia_validator_version == SCHOLIA_VALIDATOR_VERSION


def test_corpus_dirs_have_fixtures() -> None:
    """Guard — if someone deletes the fixture set this test surfaces it."""
    assert _xml_fixtures(_V03_CORPUS), (
        f"v0.3 known corpus is empty under {_V03_CORPUS}"
    )
    assert _xml_fixtures(_V031_CORPUS), (
        f"v0.3.1 fixtures are empty under {_V031_CORPUS}"
    )


# ── External-corpus replay (opt-in via env) ──────────────────────────


def _external_corpus_dir() -> Path | None:
    """Resolve ``SCHOLIA_CORPUS_DIR`` to a directory or None.

    Empty/unset → None (test is skipped). Existing path → used.
    Non-existent path → fail loudly so misconfigured CI surfaces it.
    """
    raw = os.environ.get(_EXTERNAL_CORPUS_ENV)
    if not raw:
        return None
    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        raise AssertionError(
            f"{_EXTERNAL_CORPUS_ENV}={raw!r} is set but not a directory."
        )
    return path


def _failure_ceiling() -> float:
    """Allowed failure fraction for external-corpus replay (default 0.0).

    Real-world sweeps occasionally produce edge-case shapes the parser
    legitimately rejects (truncated atoms, partial streams). The
    default ceiling is 0; bump via env when running against known-
    dirty corpora.
    """
    raw = os.environ.get(_EXTERNAL_FAILURE_CEILING_ENV)
    if not raw:
        return 0.0
    return float(raw)


@pytest.mark.skipif(
    _external_corpus_dir() is None,
    reason=(
        f"set {_EXTERNAL_CORPUS_ENV}=/path/to/sweep to enable full-corpus replay"
    ),
)
def test_external_corpus_replay_under_v031() -> None:
    """Walk every ``.xml`` under ``$SCHOLIA_CORPUS_DIR`` and
    assert the failure rate stays under the configured ceiling.

    This is the load-bearing v0.3.1 corpus-replay test: pointed at a
    real production sweep, it proves the strict-closed-set check + the new
    optional-field rules don't regress the live artifact stream. The
    in-tree fixture tests above only cover representative shapes; this
    test covers shape *coverage* at production scale when wired up.
    """
    corpus_dir = _external_corpus_dir()
    assert corpus_dir is not None
    ceiling = _failure_ceiling()

    files = sorted(corpus_dir.rglob("*.xml"))
    assert files, f"no .xml files found under {corpus_dir}"

    failures: list[tuple[Path, str]] = []
    for path in files:
        try:
            trace = parse(path.read_text(encoding="utf-8"))
            result = validate(trace)
        except ScholiaParseError as exc:
            failures.append((path, f"parse: {exc}"))
            continue
        if not result.ok:
            failures.append(
                (path, f"validate: {[e.message for e in result.errors]}")
            )

    rate = len(failures) / len(files)
    assert rate <= ceiling, (
        f"external corpus replay failure rate {rate:.4f} exceeds ceiling "
        f"{ceiling:.4f}: {len(failures)}/{len(files)} failed. First 5: "
        f"{[(str(p.relative_to(corpus_dir)), m) for p, m in failures[:5]]}"
    )
