"""Operator-curated criticality manifest reader (v0.4-C).

The manifest at ``.scholia/criticality.yaml`` maps file globs to a
closed-set criticality level. The Scholia rewriter consults this map
when populating ``<Meta criticality="..."/>`` on per-file Step atoms;
the agent runtime can consult it to decide whether a file is
kernel-grade and warrants extra scrutiny.

Manifest format (YAML)::

    # Top-level keys are criticality levels (closed set).
    # Each value is a list of repo-relative glob patterns.
    kernel:
      - src/scholialang/validator.py
      - src/example/kb/scan_for_secrets.py
    verifier:
      - src/scholialang/adjudicator*.py
    ledger:
      - src/example/kb/persistence.py
    bridge:
      - src/example/atlas/orchestrator.py
    incidental:
      - scripts/admin/**/*.py

The reader returns a flat ``Path → criticality`` mapping over the
repo-relative globs the manifest names. Globs that match no files are
still represented in the result via the unresolved pattern; callers
fall back to per-pattern membership tests via
:func:`criticality_for_path`. Missing manifest → empty dict.

Closed set: ``kernel``, ``verifier``, ``ledger``, ``bridge``,
``incidental``. Unknown levels reject with :class:`CriticalityError`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from scholialang.atoms import V031_META_CRITICALITIES


MANIFEST_RELATIVE_PATH = ".scholia/criticality.yaml"


class CriticalityError(ValueError):
    """Raised when the manifest is structurally invalid or names an
    unknown criticality level."""


@dataclass(frozen=True)
class CriticalityManifest:
    """In-memory view of the operator manifest.

    ``patterns`` preserves the manifest's authored order so a glob that
    appears under two levels (an authoring mistake) raises rather than
    silently picking the last writer. ``resolved`` is the eager glob
    expansion against ``repo_root`` — a path that doesn't currently
    exist on disk still appears under ``patterns`` for future-file
    awareness.
    """

    repo_root: Path
    patterns: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    resolved: dict[Path, str] = field(default_factory=dict)

    def criticality_for_path(self, path: Path) -> Optional[str]:
        """Return the closed-set criticality for ``path``, or ``None``.

        ``path`` may be absolute or repo-relative. Lookup is two-step:
        (1) check the eager resolved dict for an exact match; (2) fall
        through to a per-pattern :func:`fnmatch` against the repo-
        relative form. The two-step shape means future files matching
        a manifest glob get the right criticality without re-globbing.
        """
        rel = _to_relative(path, self.repo_root)
        if rel is None:
            return None
        absolute = (self.repo_root / rel).resolve()
        if absolute in self.resolved:
            return self.resolved[absolute]
        from fnmatch import fnmatch

        rel_str = str(rel).replace("\\", "/")
        for pattern, level in self.patterns:
            if fnmatch(rel_str, pattern):
                return level
            # ``**`` glob — fnmatch doesn't recurse; fall back to a
            # path-segment-aware match for ``foo/**/*.py`` shapes.
            if "**" in pattern and _matches_double_star(pattern, rel_str):
                return level
        return None


def load_criticality(repo_root: Path | str) -> CriticalityManifest:
    """Read ``.scholia/criticality.yaml`` under ``repo_root``.

    Returns an empty manifest when the file is absent (the v0.4-C
    contract: absence means "no operator classification — defaults
    apply"). Raises :class:`CriticalityError` on schema violations or
    unknown criticality levels — operators should fix their manifest
    rather than silently downgrade typos to ``incidental``.
    """
    root = Path(repo_root).resolve()
    manifest_path = root / MANIFEST_RELATIVE_PATH
    if not manifest_path.is_file():
        return CriticalityManifest(repo_root=root)

    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CriticalityError(
            f"criticality manifest at {manifest_path} is not valid YAML: {exc}"
        ) from exc

    if raw is None:
        return CriticalityManifest(repo_root=root)
    if not isinstance(raw, dict):
        raise CriticalityError(
            f"criticality manifest at {manifest_path} must be a mapping "
            f"of level -> [globs]; got {type(raw).__name__}."
        )

    patterns: list[tuple[str, str]] = []
    resolved: dict[Path, str] = {}
    seen_patterns: set[str] = set()

    for level, globs in raw.items():
        if level not in V031_META_CRITICALITIES:
            raise CriticalityError(
                f"unknown criticality level {level!r}; must be one of "
                f"{sorted(V031_META_CRITICALITIES)}."
            )
        if globs is None:
            continue
        if not isinstance(globs, list):
            raise CriticalityError(
                f"criticality level {level!r} must map to a list of globs; "
                f"got {type(globs).__name__}."
            )
        for entry in globs:
            if not isinstance(entry, str) or not entry.strip():
                raise CriticalityError(
                    f"criticality level {level!r} contains non-string or "
                    f"empty glob entry {entry!r}."
                )
            pattern = entry.strip().replace("\\", "/")
            if pattern in seen_patterns:
                raise CriticalityError(
                    f"glob pattern {pattern!r} appears under more than one "
                    "criticality level — pick one."
                )
            seen_patterns.add(pattern)
            patterns.append((pattern, level))
            for match in _glob_repo(root, pattern):
                resolved[match.resolve()] = level

    return CriticalityManifest(
        repo_root=root,
        patterns=tuple(patterns),
        resolved=resolved,
    )


def criticality_for_path(
    manifest: CriticalityManifest, path: Path | str
) -> Optional[str]:
    """Free-function wrapper around :meth:`CriticalityManifest.criticality_for_path`."""
    return manifest.criticality_for_path(Path(path))


def _to_relative(path: Path, repo_root: Path) -> Optional[Path]:
    """Return ``path`` as repo-relative or ``None`` if outside the tree.

    Tolerates already-relative inputs by treating them as
    repo-relative; absolute inputs outside ``repo_root`` return ``None``
    rather than raising — callers want a clean "no classification"
    signal for files that fall outside the manifest's domain.
    """
    p = Path(path)
    if not p.is_absolute():
        return p
    try:
        return p.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return None


def _glob_repo(root: Path, pattern: str) -> list[Path]:
    """Resolve ``pattern`` under ``root`` with ``**`` support.

    ``Path.glob`` already supports ``**``; we route through it so the
    behaviour matches the recursive shape operators expect. Returns
    an empty list when the pattern matches no files (forward
    compatibility for paths that don't exist yet).
    """
    try:
        return list(root.glob(pattern))
    except (OSError, ValueError):
        return []


def _matches_double_star(pattern: str, rel_str: str) -> bool:
    """Match ``foo/**/*.py``-shaped globs without invoking the filesystem.

    Used by :meth:`CriticalityManifest.criticality_for_path` for paths
    that don't exist on disk yet — the eager glob expansion would have
    missed them, but a pattern-level match should still classify them.
    """
    import re

    regex_parts: list[str] = []
    for token in pattern.split("/"):
        if token == "**":
            regex_parts.append(".*")
        else:
            regex_parts.append(
                re.escape(token).replace(r"\*", "[^/]*").replace(r"\?", ".")
            )
    regex = "^" + "/".join(regex_parts) + "$"
    regex = regex.replace("/.*/", "(/.*/|/)")
    return re.match(regex, rel_str) is not None


__all__ = [
    "MANIFEST_RELATIVE_PATH",
    "CriticalityError",
    "CriticalityManifest",
    "criticality_for_path",
    "load_criticality",
]
