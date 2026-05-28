"""Side-effect AST detector for Scholia v0.4-C file metadata.

Given Python source text, classify the module against the v0.3.1
``<Effect kind="...">`` closed set:

* ``io_write`` — ``open(..., 'w'/'a'/'wb'/'ab'/...)``,
  ``Path.write_text``, ``Path.write_bytes``.
* ``network`` — calls under the standard library/3rd-party network
  surface: ``requests.*``, ``urllib.*``, ``http.client.*``, ``socket.*``,
  ``aiohttp.*``, ``httpx.*``.
* ``subprocess`` — ``subprocess.run/Popen/...``, ``os.system``,
  ``os.popen``, ``os.exec*``, ``os.spawn*``.
* ``mutates_state`` — module-level ``global`` declarations OR
  module-level attribute assignment after a top-level def/class (i.e.
  the module rewrites its own state after import).
* ``pure`` — emitted only when none of the above are detected.

Detection is best-effort and AST-static; runtime indirection (a name
bound to ``subprocess.run`` in a dict) is intentionally missed to
keep the rule readable. False positives are worse than false
negatives because the rewriter prompts the model to confirm/refine
the detected list — a false positive forces the model to argue with
ground truth.

The detector returns the list of kinds in canonical iteration order
(the order defined in :data:`V031_EFFECT_KINDS_ORDERED`) so callers
that render the result into the rewriter prompt get a stable string.
"""
from __future__ import annotations

import ast
from typing import Optional


# Canonical iteration order — distinct from the validator's frozenset
# (which is unordered). The rewriter renders the prompt block from this
# order so trace diffs are stable across re-sweeps.
V031_EFFECT_KINDS_ORDERED: tuple[str, ...] = (
    "io_write",
    "network",
    "subprocess",
    "mutates_state",
    "pure",
)


_NETWORK_ROOTS: frozenset[str] = frozenset({
    "requests",
    "urllib",
    "urllib2",  # py2 holdover; still appears in vendored code
    "http",  # http.client.*
    "socket",
    "aiohttp",
    "httpx",
    "urllib3",
})

_SUBPROCESS_CALLABLES: frozenset[str] = frozenset({
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.getoutput",
    "subprocess.getstatusoutput",
    "os.system",
    "os.popen",
    "os.spawnl",
    "os.spawnle",
    "os.spawnlp",
    "os.spawnlpe",
    "os.spawnv",
    "os.spawnve",
    "os.spawnvp",
    "os.spawnvpe",
    "os.execv",
    "os.execve",
    "os.execvp",
    "os.execvpe",
    "os.execl",
    "os.execle",
    "os.execlp",
    "os.execlpe",
})

_IO_WRITE_PATH_METHODS: frozenset[str] = frozenset({
    "write_text",
    "write_bytes",
})

_WRITE_MODE_CHARS: frozenset[str] = frozenset({"w", "a", "x", "+"})


def detect_effects(source: str) -> list[str]:
    """Return the list of detected effect kinds, in canonical order.

    Returns ``["pure"]`` when no other side effect is detected; never
    pairs ``pure`` with any of the impure kinds. A syntax error in the
    source returns ``["pure"]`` (best-effort posture: unparseable
    code can't be shown to have side effects).
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return ["pure"]

    detected: set[str] = set()
    detector = _EffectVisitor()
    detector.visit(tree)
    detected.update(detector.kinds)

    if not detected:
        return ["pure"]
    return [k for k in V031_EFFECT_KINDS_ORDERED if k in detected]


class _EffectVisitor(ast.NodeVisitor):
    """Walks an AST collecting effect-kind hits.

    Tracks module-level ``def``/``class`` boundaries so the
    ``mutates_state`` heuristic can detect assignments that come AFTER
    a top-level def/class — those are the canonical "mutates own
    module" anti-pattern (e.g. ``_CACHE = {}; def foo(): _CACHE[k] = v``
    is benign; ``def foo(): ...; SOMETHING = compute()`` after the def
    is a mutation of module state).
    """

    def __init__(self) -> None:
        self.kinds: set[str] = set()
        self._past_first_def_or_class: bool = False

    # ── ``mutates_state`` ────────────────────────────────────────────

    def visit_Module(self, node: ast.Module) -> None:
        seen_def = False
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                seen_def = True
            elif isinstance(child, ast.Assign) and seen_def:
                # Assignment AFTER the first def/class — module-state mutation.
                self.kinds.add("mutates_state")
            elif isinstance(child, ast.AugAssign) and seen_def:
                self.kinds.add("mutates_state")
            self.visit(child)

    def visit_Global(self, node: ast.Global) -> None:
        # A ``global`` statement inside any def implies the function
        # rewrites module-level state.
        self.kinds.add("mutates_state")
        self.generic_visit(node)

    # ── Calls — io_write, network, subprocess ────────────────────────

    def visit_Call(self, node: ast.Call) -> None:
        dotted = _dotted_name(node.func)
        if dotted is not None:
            if dotted in _SUBPROCESS_CALLABLES:
                self.kinds.add("subprocess")
            elif _is_network(dotted):
                self.kinds.add("network")
            elif dotted == "open":
                if _open_writes(node):
                    self.kinds.add("io_write")
        # ``Path(...).write_text(...)`` / attribute-style write
        if isinstance(node.func, ast.Attribute) and node.func.attr in _IO_WRITE_PATH_METHODS:
            self.kinds.add("io_write")
        # Module-attribute mutation expressed as a call would be exotic;
        # ignore for v0.1.
        self.generic_visit(node)


def _dotted_name(node: ast.AST) -> Optional[str]:
    """Recover a dotted-name form (``os.system``) from an AST node.

    Returns ``None`` for forms that aren't pure attribute/name chains
    — e.g. ``getattr(os, 'system')(...)``. The detector intentionally
    misses indirection; cleanliness of the rule matters more than
    coverage.
    """
    parts: list[str] = []
    cursor = node
    while isinstance(cursor, ast.Attribute):
        parts.append(cursor.attr)
        cursor = cursor.value
    if isinstance(cursor, ast.Name):
        parts.append(cursor.id)
    else:
        return None
    return ".".join(reversed(parts))


def _is_network(dotted: str) -> bool:
    """True when ``dotted`` is a call into a recognised network surface.

    Matches by leftmost identifier so ``urllib.request.urlopen`` counts
    as a network call even though only ``urllib`` is in
    :data:`_NETWORK_ROOTS`.
    """
    root = dotted.split(".", 1)[0]
    return root in _NETWORK_ROOTS


def _open_writes(call: ast.Call) -> bool:
    """Inspect an ``open(...)`` call's ``mode`` arg for a write flag.

    Positional mode is the second arg per ``open(file, mode='r', ...)``.
    Keyword form ``mode='w'`` also accepted. Absent mode defaults to
    ``'r'`` — read-only, NOT a write effect.
    """
    mode_value: Optional[str] = None
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        if isinstance(call.args[1].value, str):
            mode_value = call.args[1].value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            if isinstance(kw.value.value, str):
                mode_value = kw.value.value
    if mode_value is None:
        return False
    return any(ch in _WRITE_MODE_CHARS for ch in mode_value)


__all__ = [
    "V031_EFFECT_KINDS_ORDERED",
    "detect_effects",
]
