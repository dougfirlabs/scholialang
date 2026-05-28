"""Unit tests — operator-curated criticality manifest reader (v0.4-C).

Story V04C-00. Coverage: presence/absence; closed-set validation;
glob expansion (literal + ``**``); rejection paths for malformed YAML,
duplicate globs, unknown criticality levels, non-list values.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scholialang.criticality import (
    MANIFEST_RELATIVE_PATH,
    CriticalityError,
    criticality_for_path,
    load_criticality,
)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".scholia").mkdir()
    return tmp_path


def _write_manifest(repo: Path, body: str) -> Path:
    path = repo / MANIFEST_RELATIVE_PATH
    path.write_text(body, encoding="utf-8")
    return path


def test_load_returns_empty_when_manifest_absent(tmp_path: Path) -> None:
    manifest = load_criticality(tmp_path)
    assert manifest.patterns == ()
    assert manifest.resolved == {}
    assert manifest.criticality_for_path(tmp_path / "src/x.py") is None


def test_load_empty_yaml_returns_empty_manifest(repo: Path) -> None:
    _write_manifest(repo, "")
    manifest = load_criticality(repo)
    assert manifest.patterns == ()
    assert manifest.resolved == {}


def test_literal_path_is_resolved_when_file_exists(repo: Path) -> None:
    target = repo / "src/scholialang/validator.py"
    target.parent.mkdir(parents=True)
    target.write_text("# kernel-grade")
    _write_manifest(
        repo,
        "kernel:\n  - src/scholialang/validator.py\n",
    )
    manifest = load_criticality(repo)
    assert target.resolve() in manifest.resolved
    assert manifest.criticality_for_path(target) == "kernel"


def test_pattern_matches_future_file_via_fnmatch(repo: Path) -> None:
    """File doesn't exist yet but pattern is on the manifest — still classify."""
    _write_manifest(
        repo,
        "kernel:\n  - src/foo.py\n",
    )
    manifest = load_criticality(repo)
    # Path is repo-relative and doesn't exist on disk yet.
    assert criticality_for_path(manifest, "src/foo.py") == "kernel"


def test_glob_star_expansion(repo: Path) -> None:
    target = repo / "src/scholialang/adjudicator_faithfulness.py"
    target.parent.mkdir(parents=True)
    target.write_text("# verifier")
    _write_manifest(
        repo,
        "verifier:\n  - src/scholialang/adjudicator*.py\n",
    )
    manifest = load_criticality(repo)
    assert manifest.criticality_for_path(target) == "verifier"


def test_double_star_glob_matches_nested_paths(repo: Path) -> None:
    target = repo / "scripts/admin/data/recompute.py"
    target.parent.mkdir(parents=True)
    target.write_text("# incidental")
    _write_manifest(
        repo,
        "incidental:\n  - scripts/admin/**/*.py\n",
    )
    manifest = load_criticality(repo)
    assert manifest.criticality_for_path(target) == "incidental"


def test_relative_path_lookup(repo: Path) -> None:
    target = repo / "src/foo.py"
    target.parent.mkdir(parents=True)
    target.write_text("# bridge")
    _write_manifest(repo, "bridge:\n  - src/foo.py\n")
    manifest = load_criticality(repo)
    assert criticality_for_path(manifest, "src/foo.py") == "bridge"


def test_path_outside_repo_returns_none(repo: Path, tmp_path: Path) -> None:
    _write_manifest(repo, "kernel:\n  - src/foo.py\n")
    manifest = load_criticality(repo)
    outsider = tmp_path / "elsewhere" / "src" / "foo.py"
    outsider.parent.mkdir(parents=True)
    outsider.write_text("")
    assert manifest.criticality_for_path(outsider) is None


def test_unknown_criticality_level_rejects(repo: Path) -> None:
    _write_manifest(repo, "important:\n  - src/foo.py\n")
    with pytest.raises(CriticalityError, match="unknown criticality level"):
        load_criticality(repo)


def test_duplicate_pattern_across_levels_rejects(repo: Path) -> None:
    _write_manifest(
        repo,
        "kernel:\n  - src/foo.py\nbridge:\n  - src/foo.py\n",
    )
    with pytest.raises(CriticalityError, match="more than one"):
        load_criticality(repo)


def test_non_mapping_root_rejects(repo: Path) -> None:
    _write_manifest(repo, "- just a list\n- of strings\n")
    with pytest.raises(CriticalityError, match="must be a mapping"):
        load_criticality(repo)


def test_non_list_globs_value_rejects(repo: Path) -> None:
    _write_manifest(repo, "kernel: src/foo.py\n")
    with pytest.raises(CriticalityError, match="list of globs"):
        load_criticality(repo)


def test_non_string_glob_entry_rejects(repo: Path) -> None:
    _write_manifest(repo, "kernel:\n  - 42\n")
    with pytest.raises(CriticalityError, match="non-string or empty"):
        load_criticality(repo)


def test_empty_glob_entry_rejects(repo: Path) -> None:
    _write_manifest(repo, "kernel:\n  - ''\n")
    with pytest.raises(CriticalityError, match="non-string or empty"):
        load_criticality(repo)


def test_malformed_yaml_rejects(repo: Path) -> None:
    _write_manifest(repo, "kernel:\n  - foo\n bridge: bar\n")
    with pytest.raises(CriticalityError, match="not valid YAML"):
        load_criticality(repo)


def test_empty_globs_list_is_tolerated(repo: Path) -> None:
    _write_manifest(repo, "kernel: []\nbridge:\n")
    manifest = load_criticality(repo)
    assert manifest.patterns == ()


def test_sample_fixture_loads(repo: Path) -> None:
    """The committed sample manifest under tests/fixtures/ parses cleanly."""
    sample = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "scholia"
        / "criticality.yaml"
    )
    assert sample.is_file()
    # Copy into a temp repo, then load — the sample referenced paths
    # that may or may not exist in the test environment; we only assert
    # the schema validates.
    (repo / MANIFEST_RELATIVE_PATH).write_text(sample.read_text())
    manifest = load_criticality(repo)
    # 5 patterns spread across all five levels.
    levels = {level for _, level in manifest.patterns}
    assert levels == {"kernel", "verifier", "ledger", "bridge", "incidental"}
