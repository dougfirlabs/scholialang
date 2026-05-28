"""Unit tests — side-effect AST detector (v0.4-C, Story V04C-01).

Coverage: each closed-set effect kind has at least one synthetic
fixture-based positive and the ``pure`` module exercises the
all-negative path. Edge cases: ``open()`` read-only does NOT trip
``io_write``; syntactically-invalid source returns ``["pure"]``.
"""
from __future__ import annotations

from pathlib import Path

from scholialang.atoms import V031_EFFECT_KINDS
from scholialang.effects import (
    V031_EFFECT_KINDS_ORDERED,
    detect_effects,
)


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "scholia" / "effects_sample_modules"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_ordered_constant_aligns_with_validator_closed_set() -> None:
    """Ordered iteration list must be a permutation of the validator set."""
    assert set(V031_EFFECT_KINDS_ORDERED) == set(V031_EFFECT_KINDS)


def test_io_write_module_detected() -> None:
    kinds = detect_effects(_load("io_write_module.py"))
    assert "io_write" in kinds
    assert "pure" not in kinds


def test_network_module_detected() -> None:
    kinds = detect_effects(_load("network_module.py"))
    assert "network" in kinds
    assert "pure" not in kinds


def test_subprocess_module_detected() -> None:
    kinds = detect_effects(_load("subprocess_module.py"))
    assert "subprocess" in kinds
    assert "pure" not in kinds


def test_mutates_state_module_detected() -> None:
    kinds = detect_effects(_load("mutates_state_module.py"))
    assert "mutates_state" in kinds
    assert "pure" not in kinds


def test_pure_module_returns_pure() -> None:
    kinds = detect_effects(_load("pure_module.py"))
    assert kinds == ["pure"]


def test_open_read_mode_is_not_io_write() -> None:
    """Default mode + explicit 'r' must NOT trip io_write."""
    src_no_mode = "def load(p):\n    with open(p) as fh:\n        return fh.read()\n"
    src_read = "def load(p):\n    return open(p, 'r').read()\n"
    assert detect_effects(src_no_mode) == ["pure"]
    assert detect_effects(src_read) == ["pure"]


def test_open_keyword_mode_write_is_io_write() -> None:
    src = "def dump(p):\n    return open(p, mode='w')\n"
    assert "io_write" in detect_effects(src)


def test_append_mode_is_io_write() -> None:
    src = "def append(p):\n    return open(p, 'a').close()\n"
    assert "io_write" in detect_effects(src)


def test_path_write_bytes_is_io_write() -> None:
    src = (
        "from pathlib import Path\n"
        "def dump(p, b):\n"
        "    Path(p).write_bytes(b)\n"
    )
    assert "io_write" in detect_effects(src)


def test_urllib_request_urlopen_is_network() -> None:
    src = (
        "import urllib.request\n"
        "def fetch(url):\n"
        "    return urllib.request.urlopen(url)\n"
    )
    assert "network" in detect_effects(src)


def test_subprocess_check_output_is_subprocess() -> None:
    src = (
        "import subprocess\n"
        "def listing():\n"
        "    return subprocess.check_output(['ls'])\n"
    )
    assert "subprocess" in detect_effects(src)


def test_multiple_effects_combined() -> None:
    """A module with several effects returns them all, in canonical order."""
    src = (
        "import requests\n"
        "import subprocess\n"
        "def do(p, url):\n"
        "    with open(p, 'w') as fh:\n"
        "        fh.write('x')\n"
        "    requests.get(url)\n"
        "    subprocess.run(['ls'])\n"
    )
    kinds = detect_effects(src)
    # Each of the three impure kinds present; pure absent.
    assert set(kinds) >= {"io_write", "network", "subprocess"}
    assert "pure" not in kinds
    # Canonical order is preserved (io_write before network before subprocess).
    positions = {k: i for i, k in enumerate(kinds)}
    assert positions["io_write"] < positions["network"] < positions["subprocess"]


def test_global_statement_alone_is_mutates_state() -> None:
    src = "def f():\n    global X\n    X = 1\n"
    assert "mutates_state" in detect_effects(src)


def test_module_level_assignment_before_def_is_not_mutation() -> None:
    src = "X = 1\ndef f():\n    return X\n"
    assert detect_effects(src) == ["pure"]


def test_syntax_error_falls_back_to_pure() -> None:
    """Unparseable source: best-effort says no effects detected."""
    assert detect_effects("def broken(\n") == ["pure"]


def test_indirect_call_via_getattr_is_missed_intentionally() -> None:
    """Indirection isn't tracked — readability over coverage."""
    src = "import os\nrun = getattr(os, 'system')\nrun('echo')\n"
    # The dotted-name extractor cannot follow the variable binding;
    # the call ``run('echo')`` is a plain Name so no detection.
    kinds = detect_effects(src)
    # ``run = ...`` is module-level assignment but BEFORE any def, so no
    # mutation. The call ``run('echo')`` isn't subprocess.
    assert kinds == ["pure"]


def test_empty_source_returns_pure() -> None:
    assert detect_effects("") == ["pure"]
