"""Release-version parity across every version surface in this package.

The 0.7.2 release bumps three constants by hand -- ``pyproject.toml``,
``scholialang.__version__``, and ``SCHOLIA_VALIDATOR_VERSION`` -- with nothing
asserting they agree. A release that ships them out of step is silently wrong:
the wheel METADATA says one thing and ``ValidationResult`` reports another, and
downstream floors (scholialang-mcp's ``MIN_VALIDATOR_VERSION``) gate on the
constant, not the package.

This mirrors the parity gate scholialang-mcp already has in
``tests/test_release_versions.py``. Bumping a release now means updating
``EXPECTED_VERSION`` here too, which is the point: one deliberate edit rather
than three independent ones that can drift.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import scholialang
from scholialang.atoms import SCHOLIA_VALIDATOR_VERSION


EXPECTED_VERSION = "0.7.2"
ROOT = Path(__file__).resolve().parents[3]


def _pyproject_version() -> str:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return metadata["project"]["version"]


def test_pyproject_version_matches_expected() -> None:
    assert _pyproject_version() == EXPECTED_VERSION


def test_dunder_version_matches_pyproject() -> None:
    assert scholialang.__version__ == _pyproject_version()


def test_validator_version_matches_package_version() -> None:
    """The validator constant tracks the package version.

    This is the synchronized-release decision (see CHANGELOG): the constant is kept in step
    with the package rather than versioned separately. If a future release
    decouples a spec-conformance version from the package version, this is the
    test that should be changed deliberately -- and the module docstring in
    ``scholialang/validator.py`` alongside it.
    """
    assert SCHOLIA_VALIDATOR_VERSION == EXPECTED_VERSION


def test_all_version_surfaces_agree() -> None:
    surfaces = {
        "pyproject.toml": _pyproject_version(),
        "scholialang.__version__": scholialang.__version__,
        "SCHOLIA_VALIDATOR_VERSION": SCHOLIA_VALIDATOR_VERSION,
    }
    assert len(set(surfaces.values())) == 1, f"version surfaces disagree: {surfaces}"
