"""Publish-hygiene leak guard — no internal references in the public tree.

scholialang is published to PyPI as a standalone reference implementation.
Internal product references (the host orchestrator's name, internal worktree
labels, internal ticket ids, internal-process phrasing) must never ship in
the distributed source. This guard scans the publishable tree (``src/``,
``tests/``, ``scripts/``) and hard-fails on any forbidden token.

The scan helper :func:`scan_for_leaks` is exercised two ways:

* :func:`test_no_internal_references_in_public_tree` runs it over the real
  tree and asserts it is clean — this is the release gate.
* :func:`test_leak_guard_detects_planted_reference` plants a forbidden token
  in a temp file and asserts the scanner flags it — this proves the guard is
  not vacuously passing.

Legitimate public identity (``Doug Fir Labs`` / ``dougfirlabs``, the
``LICENSE``/``NOTICE`` bylines, the public spec author byline) is intentionally
NOT in the forbidden set and must stay intact.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Repo root: tests/unit/scholia/test_public_hygiene.py -> parents[3].
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCAN_ROOTS = ("src", "tests", "scripts")

# This guard file necessarily contains the forbidden tokens (as regex
# sources); exclude it from the real-tree scan so it does not flag itself.
_SELF_PATH = Path(__file__).resolve()

# Only scan human-authored text formats; skip build artifacts / caches.
_TEXT_SUFFIXES = frozenset(
    {".py", ".json", ".md", ".txt", ".toml", ".yaml", ".yml", ".xml", ".cfg", ".ini"}
)
_SKIP_DIR_PARTS = frozenset({"__pycache__"})


# (label, compiled pattern). Patterns are deliberately specific so they catch
# the real leaks without false-positiving on ordinary technical prose.
_FORBIDDEN: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("host-orchestrator name", re.compile(r"opentalon", re.IGNORECASE)),
    ("internal proof-DAG module name", re.compile(r"proofdag", re.IGNORECASE)),
    ("interim verification-DAG module name", re.compile(r"proofchain", re.IGNORECASE)),
    ("Co-Pilot strategic phrasing", re.compile(r"co-?pilot", re.IGNORECASE)),
    ("internal ticket reference", re.compile(r"\bT42\b")),
    ("internal ticket reference", re.compile(r"\bT6x7\b")),
    ("internal worktree label", re.compile(r"v\d{2}-qf", re.IGNORECASE)),
    ("internal worktree path", re.compile(r"/home/[A-Za-z0-9._-]+/")),
    ("internal worktree path", re.compile(r"/Users/[A-Za-z0-9._-]+/")),
)


def _iter_text_files(root: Path):
    """Yield every scannable text file under ``root`` (recursively)."""
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIR_PARTS for part in path.parts):
            continue
        if ".egg-info" in str(path):
            continue
        if path.suffix not in _TEXT_SUFFIXES:
            continue
        if path.resolve() == _SELF_PATH:
            continue
        yield path


def scan_for_leaks(roots) -> list[tuple[str, int, str, str]]:
    """Scan ``roots`` for forbidden tokens.

    Returns a list of ``(relative_path, line_number, label, matched_text)``
    tuples — one per forbidden-token hit. Empty list means clean.
    """
    violations: list[tuple[str, int, str, str]] = []
    for root in roots:
        root = Path(root)
        for path in _iter_text_files(root):
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                for label, pattern in _FORBIDDEN:
                    match = pattern.search(line)
                    if match:
                        try:
                            display = str(path.relative_to(_REPO_ROOT))
                        except ValueError:
                            display = str(path)
                        violations.append(
                            (display, lineno, label, match.group(0))
                        )
    return violations


def test_no_internal_references_in_public_tree():
    """Release gate — the publishable tree carries no forbidden tokens."""
    roots = [_REPO_ROOT / r for r in _SCAN_ROOTS]
    violations = scan_for_leaks(roots)
    assert not violations, "internal references leaked into the public tree:\n" + "\n".join(
        f"  {path}:{lineno} [{label}] matched {text!r}"
        for path, lineno, label, text in violations
    )


def test_leak_guard_detects_planted_reference(tmp_path):
    """Self-test — a planted forbidden token must be flagged."""
    planted = tmp_path / "planted_module.py"
    planted.write_text(
        '"""A docstring that references opentalon internals."""\n'
        "VALUE = 1\n",
        encoding="utf-8",
    )
    violations = scan_for_leaks([tmp_path])
    assert violations, "leak guard failed to flag a planted forbidden token"
    assert any(label == "host-orchestrator name" for _, _, label, _ in violations)


def test_leak_guard_passes_clean_file(tmp_path):
    """Self-test — a clean file must NOT be flagged (no false positives)."""
    clean = tmp_path / "clean_module.py"
    clean.write_text(
        '"""Scholia reference helper from Doug Fir Labs (dougfirlabs)."""\n'
        "VALUE = 42\n",
        encoding="utf-8",
    )
    violations = scan_for_leaks([tmp_path])
    assert not violations, f"clean file wrongly flagged: {violations}"


@pytest.mark.parametrize(
    "token",
    ["opentalon", "OpenTalon", "proofdag", "proofchain", "Co-Pilot", "T42", "T6x7", "v06-qf"],
)
def test_each_forbidden_token_is_caught(tmp_path, token):
    """Every forbidden token shape is independently detectable."""
    planted = tmp_path / "f.py"
    planted.write_text(f"# leak: {token}\n", encoding="utf-8")
    assert scan_for_leaks([tmp_path]), f"{token!r} not caught by the guard"
