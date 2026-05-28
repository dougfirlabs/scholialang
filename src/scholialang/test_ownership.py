"""Test-ownership resolver for Scholia v0.4-C file metadata.

For a source file under ``repo_root``, return the list of test files
that exercise it. The Scholia rewriter consults this to populate
``<Ref type="test_owner" target="..."/>`` sub-elements on Observations
about testing or coverage.

Three priority sources (highest first):

1. **Operator override** — ``.scholia/test_ownership.yaml`` at repo
   root, a mapping of repo-relative source paths to a list of
   repo-relative test paths. Authoritative when present.

2. **Coverage map** — ``.scholia/coverage_map.json`` produced by
   ``pytest --cov`` post-processing. Shape: ``{src_path: [test_paths]}``.
   Used when override is silent on a given source.

3. **Name-convention heuristic** — for ``src/foo.py``, glob the
   conventional locations (``tests/**/test_foo.py``,
   ``tests/**/foo_test.py``) and emit every hit. The most common
   project layouts hit this path.

A source with no override entry, no coverage entry, and no name-
convention match returns ``[]`` — the rewriter then omits the Ref
sub-element. Absence is the v0.4-C contract for "we don't know which
tests own this file" rather than a failure.

The reader is silent about which source produced a given match; if
that detail becomes useful, the function signature can grow a
``return_source: bool`` argument without breaking existing callers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


OVERRIDE_RELATIVE_PATH = ".scholia/test_ownership.yaml"
COVERAGE_MAP_RELATIVE_PATH = ".scholia/coverage_map.json"


class TestOwnershipError(ValueError):
    """Raised when override or coverage data is malformed."""

    __test__ = False  # tell pytest this is not a test class


@dataclass(frozen=True)
class TestOwnershipIndex:
    """Pre-computed lookup over override + coverage sources.

    The name-convention heuristic is path-dependent and runs at lookup
    time; the override + coverage layers are pre-materialised here so
    repeated ``resolve_test_owners`` calls are O(1) on the hit path.
    """

    __test__ = False  # tell pytest this is not a test class

    repo_root: Path
    overrides: dict[str, tuple[str, ...]] = field(default_factory=dict)
    coverage: dict[str, tuple[str, ...]] = field(default_factory=dict)


def load_index(repo_root: Path | str) -> TestOwnershipIndex:
    """Build a :class:`TestOwnershipIndex` from on-disk sources.

    Missing sources are silently skipped — operators add either layer
    incrementally. Malformed sources raise :class:`TestOwnershipError`
    rather than degrading to the heuristic, because a malformed
    override is a strong signal the operator wanted something specific.
    """
    root = Path(repo_root).resolve()
    overrides = _load_overrides(root)
    coverage = _load_coverage_map(root)
    return TestOwnershipIndex(
        repo_root=root,
        overrides=overrides,
        coverage=coverage,
    )


def resolve_test_owners(
    source_path: Path | str,
    repo_root: Path | str,
    *,
    index: Optional[TestOwnershipIndex] = None,
) -> list[Path]:
    """Return the test files associated with ``source_path``.

    Lookup walks the three priority layers in order; the first layer
    with a non-empty result returns. ``source_path`` accepts absolute
    or repo-relative inputs.

    The returned list is repo-relative :class:`Path` objects in
    discovery order — operators reading them in a trace get a stable,
    diff-friendly rendering.
    """
    root = Path(repo_root).resolve()
    idx = index if index is not None else load_index(root)

    rel = _to_relative_str(Path(source_path), root)
    if rel is None:
        return []

    # 1. Override
    if rel in idx.overrides:
        return [Path(p) for p in idx.overrides[rel]]

    # 2. Coverage map
    if rel in idx.coverage:
        return [Path(p) for p in idx.coverage[rel]]

    # 3. Name-convention heuristic
    return _name_convention_lookup(rel, root)


def _load_overrides(root: Path) -> dict[str, tuple[str, ...]]:
    path = root / OVERRIDE_RELATIVE_PATH
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise TestOwnershipError(
            f"test ownership override at {path} is not valid YAML: {exc}"
        ) from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise TestOwnershipError(
            f"test ownership override at {path} must be a mapping of "
            f"source_path -> [test_paths]; got {type(raw).__name__}."
        )
    result: dict[str, tuple[str, ...]] = {}
    for src, tests in raw.items():
        if not isinstance(src, str) or not src.strip():
            raise TestOwnershipError(
                f"test ownership override key must be a non-empty string; got {src!r}."
            )
        if not isinstance(tests, list):
            raise TestOwnershipError(
                f"test ownership override entry for {src!r} must be a list of "
                f"test paths; got {type(tests).__name__}."
            )
        cleaned: list[str] = []
        for t in tests:
            if not isinstance(t, str) or not t.strip():
                raise TestOwnershipError(
                    f"test ownership override entry for {src!r} contains "
                    f"non-string or empty test path {t!r}."
                )
            cleaned.append(t.strip().replace("\\", "/"))
        result[src.strip().replace("\\", "/")] = tuple(cleaned)
    return result


def _load_coverage_map(root: Path) -> dict[str, tuple[str, ...]]:
    path = root / COVERAGE_MAP_RELATIVE_PATH
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TestOwnershipError(
            f"coverage map at {path} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise TestOwnershipError(
            f"coverage map at {path} must be a JSON object of "
            f"source_path -> [test_paths]; got {type(raw).__name__}."
        )
    result: dict[str, tuple[str, ...]] = {}
    for src, tests in raw.items():
        if not isinstance(src, str) or not src.strip():
            continue
        if not isinstance(tests, list):
            raise TestOwnershipError(
                f"coverage map entry for {src!r} must be a list; got "
                f"{type(tests).__name__}."
            )
        cleaned = tuple(
            t.strip().replace("\\", "/")
            for t in tests
            if isinstance(t, str) and t.strip()
        )
        result[src.strip().replace("\\", "/")] = cleaned
    return result


def _to_relative_str(path: Path, repo_root: Path) -> Optional[str]:
    """Convert ``path`` to a forward-slash repo-relative string."""
    p = Path(path)
    if not p.is_absolute():
        return str(p).replace("\\", "/")
    try:
        rel = p.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return None
    return str(rel).replace("\\", "/")


def _name_convention_lookup(rel_src: str, root: Path) -> list[Path]:
    """Heuristic: ``src/foo.py`` → ``tests/**/test_foo.py`` etc.

    Only triggers on Python source files (``.py``); other languages
    return ``[]`` because their test-naming conventions aren't
    universal enough to pin down here. The patterns mirror what
    pytest's default collection picks up.
    """
    src = Path(rel_src)
    if src.suffix != ".py":
        return []
    stem = src.stem
    if stem.startswith("test_") or stem.endswith("_test"):
        # ``rel_src`` is itself a test file; tests don't "own" tests.
        return []
    if stem == "__init__":
        # ``__init__.py`` has no canonical test counterpart.
        return []
    patterns = (
        f"tests/**/test_{stem}.py",
        f"tests/**/{stem}_test.py",
    )
    found: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for hit in sorted(root.glob(pattern)):
            try:
                rel = hit.resolve().relative_to(root.resolve())
            except ValueError:
                continue
            if rel in seen:
                continue
            seen.add(rel)
            found.append(rel)
    return found


__all__ = [
    "COVERAGE_MAP_RELATIVE_PATH",
    "OVERRIDE_RELATIVE_PATH",
    "TestOwnershipError",
    "TestOwnershipIndex",
    "load_index",
    "resolve_test_owners",
]
