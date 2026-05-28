"""Unit tests — test-ownership resolver (v0.4-C, Story V04C-02).

Coverage: each of the three priority layers (override, coverage map,
name-convention heuristic) plus the empty-result and malformed-input
rejection paths.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scholialang.test_ownership import (
    COVERAGE_MAP_RELATIVE_PATH,
    OVERRIDE_RELATIVE_PATH,
    TestOwnershipError,
    load_index,
    resolve_test_owners,
)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".scholia").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path


def _write_yaml(repo: Path, body: str) -> None:
    (repo / OVERRIDE_RELATIVE_PATH).write_text(body, encoding="utf-8")


def _write_coverage(repo: Path, body: str) -> None:
    (repo / COVERAGE_MAP_RELATIVE_PATH).write_text(body, encoding="utf-8")


# ── Priority 1: override ─────────────────────────────────────────────


def test_override_takes_priority_over_heuristic(repo: Path) -> None:
    """Override entry wins even when the heuristic would also fire."""
    (repo / "src" / "foo.py").write_text("# src")
    (repo / "tests" / "test_foo.py").write_text("# heuristic match")
    (repo / "tests" / "test_alternative_foo.py").write_text("# override target")
    _write_yaml(
        repo,
        "src/foo.py:\n  - tests/test_alternative_foo.py\n",
    )
    result = resolve_test_owners("src/foo.py", repo)
    assert result == [Path("tests/test_alternative_foo.py")]


def test_override_multiple_test_paths(repo: Path) -> None:
    (repo / "src" / "bar.py").write_text("# src")
    _write_yaml(
        repo,
        "src/bar.py:\n  - tests/unit/test_bar.py\n  - tests/integration/test_bar_flow.py\n",
    )
    result = resolve_test_owners("src/bar.py", repo)
    assert result == [
        Path("tests/unit/test_bar.py"),
        Path("tests/integration/test_bar_flow.py"),
    ]


def test_override_absent_for_source_falls_through(repo: Path) -> None:
    """Override exists but doesn't mention this source → next layer runs."""
    (repo / "src" / "foo.py").write_text("# src")
    (repo / "tests" / "test_foo.py").write_text("# heuristic match")
    _write_yaml(repo, "src/other.py:\n  - tests/test_other.py\n")
    result = resolve_test_owners("src/foo.py", repo)
    assert result == [Path("tests/test_foo.py")]


# ── Priority 2: coverage map ─────────────────────────────────────────


def test_coverage_map_used_when_override_absent(repo: Path) -> None:
    (repo / "src" / "baz.py").write_text("# src")
    (repo / "tests" / "test_baz.py").write_text("# heuristic match")
    _write_coverage(
        repo,
        '{"src/baz.py": ["tests/coverage/test_baz_lite.py"]}',
    )
    result = resolve_test_owners("src/baz.py", repo)
    assert result == [Path("tests/coverage/test_baz_lite.py")]


def test_override_beats_coverage(repo: Path) -> None:
    (repo / "src" / "foo.py").write_text("# src")
    _write_yaml(repo, "src/foo.py:\n  - tests/from_override.py\n")
    _write_coverage(repo, '{"src/foo.py": ["tests/from_coverage.py"]}')
    result = resolve_test_owners("src/foo.py", repo)
    assert result == [Path("tests/from_override.py")]


# ── Priority 3: name-convention heuristic ────────────────────────────


def test_name_convention_test_prefix(repo: Path) -> None:
    (repo / "src" / "alpha.py").write_text("# src")
    (repo / "tests" / "unit").mkdir()
    (repo / "tests" / "unit" / "test_alpha.py").write_text("# match")
    result = resolve_test_owners("src/alpha.py", repo)
    assert result == [Path("tests/unit/test_alpha.py")]


def test_name_convention_test_suffix(repo: Path) -> None:
    (repo / "src" / "beta.py").write_text("# src")
    (repo / "tests" / "integration").mkdir()
    (repo / "tests" / "integration" / "beta_test.py").write_text("# match")
    result = resolve_test_owners("src/beta.py", repo)
    assert result == [Path("tests/integration/beta_test.py")]


def test_name_convention_multiple_matches_returned(repo: Path) -> None:
    (repo / "src" / "shared.py").write_text("# src")
    (repo / "tests" / "unit").mkdir()
    (repo / "tests" / "integration").mkdir()
    (repo / "tests" / "unit" / "test_shared.py").write_text("# unit")
    (repo / "tests" / "integration" / "test_shared.py").write_text("# integration")
    result = resolve_test_owners("src/shared.py", repo)
    # Both hits returned; order is deterministic via sorted+glob.
    assert Path("tests/unit/test_shared.py") in result
    assert Path("tests/integration/test_shared.py") in result


def test_test_file_returns_empty(repo: Path) -> None:
    """A test file does not have a test_owner of its own."""
    (repo / "tests" / "unit").mkdir()
    (repo / "tests" / "unit" / "test_alpha.py").write_text("# test file")
    result = resolve_test_owners("tests/unit/test_alpha.py", repo)
    assert result == []


def test_init_file_returns_empty(repo: Path) -> None:
    (repo / "src" / "foo").mkdir()
    (repo / "src" / "foo" / "__init__.py").write_text("")
    result = resolve_test_owners("src/foo/__init__.py", repo)
    assert result == []


def test_non_python_source_returns_empty(repo: Path) -> None:
    """Heuristic only fires for ``.py`` sources."""
    (repo / "src" / "schema.json").write_text("{}")
    result = resolve_test_owners("src/schema.json", repo)
    assert result == []


def test_no_matches_returns_empty_list(repo: Path) -> None:
    """When no override, no coverage, no test by convention exists."""
    (repo / "src" / "orphan.py").write_text("# no test")
    result = resolve_test_owners("src/orphan.py", repo)
    assert result == []


def test_absolute_path_input(repo: Path) -> None:
    (repo / "src" / "abs.py").write_text("")
    (repo / "tests" / "test_abs.py").write_text("")
    result = resolve_test_owners(repo / "src" / "abs.py", repo)
    assert result == [Path("tests/test_abs.py")]


def test_path_outside_repo_returns_empty(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere" / "src" / "x.py"
    outside.parent.mkdir(parents=True)
    outside.write_text("")
    result = resolve_test_owners(outside, repo)
    assert result == []


# ── Index reuse ──────────────────────────────────────────────────────


def test_resolve_accepts_prebuilt_index(repo: Path) -> None:
    (repo / "src" / "foo.py").write_text("")
    (repo / "tests" / "test_foo.py").write_text("")
    idx = load_index(repo)
    result = resolve_test_owners("src/foo.py", repo, index=idx)
    assert result == [Path("tests/test_foo.py")]


# ── Malformed-input rejection ────────────────────────────────────────


def test_malformed_override_yaml_rejects(repo: Path) -> None:
    _write_yaml(repo, "src/foo.py:\n  - tests/x.py\n bad: indent\n")
    with pytest.raises(TestOwnershipError, match="not valid YAML"):
        load_index(repo)


def test_non_mapping_override_rejects(repo: Path) -> None:
    _write_yaml(repo, "- just a list\n- of strings\n")
    with pytest.raises(TestOwnershipError, match="must be a mapping"):
        load_index(repo)


def test_non_list_test_value_rejects(repo: Path) -> None:
    _write_yaml(repo, "src/foo.py: tests/test_foo.py\n")
    with pytest.raises(TestOwnershipError, match="must be a list"):
        load_index(repo)


def test_malformed_coverage_json_rejects(repo: Path) -> None:
    _write_coverage(repo, "{not json}")
    with pytest.raises(TestOwnershipError, match="not valid JSON"):
        load_index(repo)


def test_non_object_coverage_rejects(repo: Path) -> None:
    _write_coverage(repo, "[1, 2, 3]")
    with pytest.raises(TestOwnershipError, match="must be a JSON object"):
        load_index(repo)
