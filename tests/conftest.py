"""Pytest bootstrap — put scholialang's src layout on sys.path.

The scholialang package uses ``src/scholialang`` layout. Until a
``pyproject.toml`` lands and we run ``pip install -e scholialang``,
this conftest inserts the src dir so ``import scholialang`` works
from any test runner invocation (``pytest scholialang/tests/...``).
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
