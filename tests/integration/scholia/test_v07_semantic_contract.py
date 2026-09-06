"""v0.7 semantic-contract consumer gate — corpus execution + obligations.

This module is the reference implementation's CONSUMER side of the
proposed Map/Event/Task contract:

* It executes EVERY case of the shared self-describing conformance
  suite ``conformance/v0.7/semantic_atoms.json`` from a scholialang-spec
  checkout (``SCHOLIALANG_SPEC_DIR`` or a sibling checkout), pinned by
  exact spec revision and corpus SHA-256 — coverage may not shrink or
  drift silently.
* It binds every structured runtime obligation the suite declares
  (behaviors that cannot be represented safely in static fixtures) to a
  concrete executable test node: no-I/O probes, no-caller-mutation
  round trips, forced truncated-hash collisions, registry idempotence
  and provenance controls, in-memory shape rejection, the full
  canonical-reference matrix, structural-identity mutations, opaque
  correlators, the installed legacy-artifact probe, and packaging
  parity.

Like the shared fingerprint corpus, the suite is consumed from the
spec checkout — never vendored. When no checkout is present the
corpus-bound tests skip; setting ``SCHOLIALANG_REQUIRE_SEMANTIC_FIXTURES=1``
makes absence a hard failure (the conformance gate must prove all
cases ran, never report green while validating zero). The
obligation probes that need no corpus run unconditionally.

Environment knobs (all optional):

* ``SCHOLIALANG_SPEC_DIR`` — explicit spec checkout.
* ``SCHOLIALANG_REQUIRE_SEMANTIC_FIXTURES=1`` — fail closed on absence.
* ``SCHOLIALANG_OLD_ARTIFACT_PYTHON`` — interpreter of a separately
  installed 0.7.2 environment for the real old-consumer probe.
* ``SCHOLIALANG_REQUIRE_OLD_ARTIFACT=1`` — fail closed when the old
  artifact probe cannot run.
* ``SCHOLIALANG_EXPECT_IMPORT_PREFIX`` — packaging-parity import-origin
  assertion (set by the wheel/sdist gate environments).
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import scholialang
from scholialang.atoms import (
    ATOM_KINDS,
    CANONICAL_ID_HEX_LENGTH,
    KIND_SPECIFIC_FIELDS,
    LEGACY_ATOM_KINDS,
    SEMANTIC_KINDS,
    Atom,
    Event,
    Map,
    SemanticShapeError,
    Task,
    atom_class_for_kind,
    compute_canonical_id,
)
from scholialang.parser import ScholiaParseError, parse
from scholialang.registry import CanonicalCollisionError, Registry
from scholialang.serializer import (
    from_json,
    from_yaml,
    to_canonical_json,
    to_json,
    to_yaml,
    trace_from_dict,
)
from scholialang.validator import (
    RULE_ACTION_RECORDED,
    RULE_CANONICAL_ID_WELL_FORMED,
    RULE_GOAL_DECLARED,
    RULE_GRAMMAR_PROFILE_UNSUPPORTED,
    RULE_MAP_ENTRIES_SHAPE,
    RULE_MAP_ENTRIES_TYPED,
    RULE_MAP_REF_RESOLVES,
    RULE_SEMANTIC_CHILDREN_EMPTY,
    RULE_SEMANTIC_OPERATORS_LIST,
    RULE_SEMANTIC_REF_TARGET_KIND,
    RULE_TASK_STATUS_ENUM,
    validate,
)

# ── Pinned accepted-producer identity ────────────────────────────────
#
# The exact accepted spec revision this consumer implements, plus the
# SHA-256 of the corpus and its independently validated coverage
# inventory. A checkout whose corpus hashes differ FAILS (not skips):
# executing a drifted corpus would prove nothing about the accepted
# contract.

ACCEPTED_SPEC_SHA = "4e19eae3e55566dac450c0dbf7bcba03d12afc50"
SEMANTIC_CORPUS_SHA256 = (
    "8ef6db811290522e6234fbc9d1b748d567aaa3b78f86c536527c98e77a8f3a6e"
)
COVERAGE_INVENTORY_SHA256 = (
    "eed5d0c6d4ed982a8115e85bc6354b9c37695468f403dd4321bff0612a82366d"
)
EXPECTED_TOTAL_CASES = 204
EXPECTED_POSITIVE = 36
EXPECTED_NEGATIVE = 168
EXPECTED_OBLIGATIONS = 11

_SPEC_ENV = "SCHOLIALANG_SPEC_DIR"
_REQUIRE_ENV = "SCHOLIALANG_REQUIRE_SEMANTIC_FIXTURES"
_OLD_PY_ENV = "SCHOLIALANG_OLD_ARTIFACT_PYTHON"
_REQUIRE_OLD_ENV = "SCHOLIALANG_REQUIRE_OLD_ARTIFACT"
_IMPORT_PREFIX_ENV = "SCHOLIALANG_EXPECT_IMPORT_PREFIX"

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SUITE_SUBPATH = Path("conformance") / "v0.7" / "semantic_atoms.json"


def _candidate_spec_dirs() -> list[Path]:
    candidates: list[Path] = []
    env = os.environ.get(_SPEC_ENV)
    if env:
        candidates.append(Path(env))
    candidates.append(_REPO_ROOT.parent / "scholialang-spec")
    candidates.append(_REPO_ROOT.parent.parent / "scholialang-spec")
    return candidates


def _find_spec_dir() -> Path | None:
    for spec_dir in _candidate_spec_dirs():
        if (spec_dir / _SUITE_SUBPATH).is_file():
            return spec_dir
    return None


_SPEC_DIR = _find_spec_dir()
_REQUIRE_FIXTURES = os.environ.get(_REQUIRE_ENV) == "1"


def _load_suite() -> dict:
    # Collection-time helper (parametrize) — must be safe when the spec
    # checkout is absent so the corpus-bound tests skip cleanly.
    if _SPEC_DIR is None:
        return {}
    return json.loads(
        (_SPEC_DIR / _SUITE_SUBPATH).read_text(encoding="utf-8")
    )


_SUITE = _load_suite()
_CASES = list(_SUITE.get("cases", []))
_CASE_IDS = [str(c.get("id") or f"case-{i}") for i, c in enumerate(_CASES)]

_corpus_skip = pytest.mark.skipif(
    _SPEC_DIR is None and not _REQUIRE_FIXTURES,
    reason=(
        f"scholialang-spec semantic corpus not found; set {_SPEC_ENV} or "
        "place a scholialang-spec checkout beside this repo (shared "
        "corpus, no in-repo fork)."
    ),
)


def _load_runner():
    """Import the conformance runner (single executor, no fork)."""
    path = _REPO_ROOT / "scripts" / "run_spec_conformance.py"
    spec = importlib.util.spec_from_file_location("_spec_conformance", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_spec_conformance"] = module  # dataclass introspection needs this
    spec.loader.exec_module(module)
    return module


_RUNNER = _load_runner()


# ── Required consumer-gate tests ─────────────────────────────────────


@_corpus_skip
def test_exact_spec_revision_and_required_corpus():
    """The pinned revision, corpus hash, inventory hash, and counts all
    match the accepted producer contract — fail closed on drift."""
    pin = (_REPO_ROOT / "scholialang-spec-ref.txt").read_text(encoding="utf-8")
    assert pin.strip() == ACCEPTED_SPEC_SHA

    if _SPEC_DIR is None:
        assert not _REQUIRE_FIXTURES or False, (
            f"{_REQUIRE_ENV}=1 but no semantic corpus resolved"
        )
        pytest.skip("corpus absent (not required)")

    suite_bytes = (_SPEC_DIR / _SUITE_SUBPATH).read_bytes()
    assert hashlib.sha256(suite_bytes).hexdigest() == SEMANTIC_CORPUS_SHA256, (
        "semantic_atoms.json does not match the accepted corpus hash"
    )
    inventory_path = _SPEC_DIR / "conformance" / "v0.7" / "coverage-inventory.json"
    assert (
        hashlib.sha256(inventory_path.read_bytes()).hexdigest()
        == COVERAGE_INVENTORY_SHA256
    ), "coverage-inventory.json does not match the accepted inventory hash"

    assert len(_CASES) == EXPECTED_TOTAL_CASES
    assert (
        sum(1 for c in _CASES if c.get("category") == "positive")
        == EXPECTED_POSITIVE
    )
    assert (
        sum(1 for c in _CASES if c.get("category") == "negative")
        == EXPECTED_NEGATIVE
    )
    assert len(_SUITE.get("runtime_obligations", [])) == EXPECTED_OBLIGATIONS

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert [str(i) for i in inventory["case_ids"]] == _CASE_IDS

    git_dir = _SPEC_DIR / ".git"
    if git_dir.exists():
        head = subprocess.run(
            ["git", "-C", str(_SPEC_DIR), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if head.returncode == 0:
            assert head.stdout.strip() == ACCEPTED_SPEC_SHA


def test_corpus_present_when_required():
    if not _REQUIRE_FIXTURES:
        pytest.skip(f"{_REQUIRE_ENV} not set (isolated checkout)")
    assert _SPEC_DIR is not None, (
        f"{_REQUIRE_ENV}=1 but no scholialang-spec semantic corpus resolved"
    )
    assert len(_CASES) == EXPECTED_TOTAL_CASES


@_corpus_skip
@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_every_semantic_fixture_executes(case: dict) -> None:
    """Every pinned corpus case executes with its declared phase/rule/
    diagnostic/round-trip expectations — zero skips, no generic
    negative outcomes."""
    failures = _RUNNER._run_semantic_case(case)
    assert failures == [], "\n".join(failures)


@_corpus_skip
def test_current_catalog_and_exports_match_pinned_spec():
    yaml = pytest.importorskip("yaml")
    assert _SPEC_DIR is not None
    index = yaml.safe_load(
        (_SPEC_DIR / "reference" / "v0.7" / "atoms_index.yaml").read_text(
            encoding="utf-8"
        )
    )
    index_kinds = [e["kind"] for e in index["atoms"]]
    assert set(index_kinds) == set(ATOM_KINDS)
    assert len(index_kinds) == 35
    assert index["package_version"] == scholialang.__version__
    assert index["grammar_version"] == scholialang.SCHOLIA_GRAMMAR_VERSION
    assert _SUITE["package_version"].startswith(scholialang.__version__)
    assert _SUITE["spec_version"].startswith(
        scholialang.SCHOLIA_GRAMMAR_VERSION
    )
    for name in ("Map", "Event", "Task"):
        assert name in scholialang.__all__


@_corpus_skip
def test_current_wire_fields_match_pinned_spec():
    yaml = pytest.importorskip("yaml")
    assert _SPEC_DIR is not None
    from scholialang.atoms import wire_name_for

    index = yaml.safe_load(
        (_SPEC_DIR / "reference" / "v0.7" / "atoms_index.yaml").read_text(
            encoding="utf-8"
        )
    )
    for entry in index["atoms"]:
        kind = entry["kind"]
        names = {a["name"] for a in (entry.get("attributes") or [])}
        expected = {"id"} | {
            wire_name_for(kind, f) for f in KIND_SPECIFIC_FIELDS.get(kind, ())
        }
        assert names == expected, (
            f"{kind}: index fields {sorted(names)} != core wire fields "
            f"{sorted(expected)}"
        )


def test_legacy_profile_remains_exactly_32_kinds():
    assert len(LEGACY_ATOM_KINDS) == 32
    for kind in ("Map", "Event", "Task"):
        assert kind not in LEGACY_ATOM_KINDS
    trace = parse(
        '<Step id="S_01">'
        '<Task id="Task_01" status="open">Review the fixture output.</Task>'
        "</Step>"
    )
    result = validate(trace, profile="0.6.2")
    profile_errors = result.errors_by_rule[RULE_GRAMMAR_PROFILE_UNSUPPORTED]
    assert profile_errors, "legacy profile must reject the new kinds"
    assert "0.6.2" in profile_errors[0].message
    assert "Task" in profile_errors[0].message
    # Same trace under the current profile (and the default) is fine.
    assert validate(trace, profile="0.7.0").errors_by_rule[
        RULE_GRAMMAR_PROFILE_UNSUPPORTED
    ] == []
    # An unknown future profile is a structured rejection, not a guess.
    unknown = validate(trace, profile="0.9").errors_by_rule[
        RULE_GRAMMAR_PROFILE_UNSUPPORTED
    ]
    assert unknown and "0.9" in unknown[0].message


def test_legacy_hashes_and_required_corpora_unchanged():
    """Legacy golden canonical identities and the frozen fixture corpora
    validate byte-identically under the 0.7.3 core."""
    golden = json.loads(
        (_REPO_ROOT / "tests" / "fixtures" / "canonical_id_golden.json").read_text(
            encoding="utf-8"
        )
    )
    import scholialang.atoms as atoms_module

    for vector in golden["vectors"]:
        cls = getattr(atoms_module, vector["kind"])
        atom = cls(**vector["kwargs"])
        assert compute_canonical_id(atom) == vector["expected_canonical_id"], (
            f"golden canonical id regressed for {vector['kind']}"
        )

    fixtures_root = _REPO_ROOT / "tests" / "fixtures" / "scholia"
    corpus_files = sorted(
        list((fixtures_root / "v03_known_corpus").glob("*.xml"))
        + list((fixtures_root / "v031_atoms").glob("*.xml"))
    )
    assert corpus_files, "frozen fixture corpora are missing"
    for path in corpus_files:
        result = validate(parse(path.read_text(encoding="utf-8")))
        assert result.ok, f"{path.name} regressed: {result.errors}"


def test_explicit_old_consumer_rejects_new_kinds_without_rewrite():
    """The REAL installed 0.7.2 artifact fails on new kinds with its own
    unknown-kind error (probed in its own environment), and the new
    library's legacy-profile diagnostic stays a distinct arm."""
    old_python = os.environ.get(_OLD_PY_ENV)
    require_old = os.environ.get(_REQUIRE_OLD_ENV) == "1"
    if not old_python:
        if require_old:
            pytest.fail(
                f"{_REQUIRE_OLD_ENV}=1 but {_OLD_PY_ENV} is not set — the "
                "old-artifact probe is required"
            )
        pytest.skip(f"{_OLD_PY_ENV} not set (old-artifact env unavailable)")

    probe = (
        "import json, scholialang\n"
        "from scholialang.parser import parse, ScholiaParseError\n"
        "out = {'version': scholialang.__version__,"
        " 'origin': scholialang.__file__, 'errors': {}}\n"
        "for kind, xml in {\n"
        "    'Map': '<Step id=\"S_01\"><Map id=\"Map_01\" value_type=\"string\""
        " entries=\"{}\">Inputs.</Map></Step>',\n"
        "    'Event': '<Step id=\"S_01\"><Event id=\"Event_01\" source=\"w\""
        " occurrence_id=\"o1\" event_type=\"t.r\">Recorded.</Event></Step>',\n"
        "    'Task': '<Step id=\"S_01\"><Task id=\"Task_01\" status=\"open\">"
        "Review.</Task></Step>',\n"
        "}.items():\n"
        "    try:\n"
        "        parse(xml)\n"
        "        out['errors'][kind] = None\n"
        "    except Exception as exc:\n"
        "        out['errors'][kind] = f'{type(exc).__name__}: {exc}'\n"
        "print(json.dumps(out))\n"
    )
    proc = subprocess.run(
        [old_python, "-c", probe],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PYTHONPATH": ""},
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["version"] == "0.7.2", f"old artifact reports {out['version']}"
    origin = Path(out["origin"]).resolve()
    assert _REPO_ROOT not in origin.parents, (
        f"old-artifact probe imported from this source tree: {origin}"
    )
    for kind in ("Map", "Event", "Task"):
        error = out["errors"][kind]
        assert error is not None, (
            f"the 0.7.2 artifact unexpectedly accepted <{kind}>"
        )
        assert kind in error, f"old error does not name the kind: {error}"

    # Distinct arm: the NEW library under an explicit legacy profile
    # emits the structured diagnostic — no exception, no rewrite.
    trace = parse(
        '<Step id="S_01"><Map id="Map_01" value_type="string" entries="{}">'
        "Inputs.</Map></Step>"
    )
    result = validate(trace, profile="0.6.2")
    errors = result.errors_by_rule[RULE_GRAMMAR_PROFILE_UNSUPPORTED]
    assert errors and "0.6.2" in errors[0].message and "Map" in errors[0].message
    assert trace[0].atoms[0].kind == "Map"  # never down-converted


def _denial(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deny filesystem writes, subprocess creation, and network calls.

    Imports/fixtures load BEFORE this is applied; the implementation is
    not replaced — only the process-boundary primitives are tripwired.
    """
    import builtins
    import socket

    def _deny(*_a, **_k):
        raise AssertionError("side effect attempted during a pure operation")

    real_open = builtins.open

    def _guarded_open(file, mode="r", *args, **kwargs):
        if any(flag in str(mode) for flag in ("w", "a", "x", "+")):
            raise AssertionError(
                f"filesystem write attempted during a pure operation: {file}"
            )
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _guarded_open)
    monkeypatch.setattr(socket, "socket", _deny)
    monkeypatch.setattr(socket, "create_connection", _deny)
    monkeypatch.setattr(subprocess, "Popen", _deny)
    monkeypatch.setattr(os, "system", _deny)
    monkeypatch.setattr(os, "popen", _deny)


def test_semantic_task_does_not_execute_or_close_goal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A satisfied Task neither executes anything nor stands in for the
    existing closure rules: a required Goal stays unclosed and an
    Action stays unrecorded."""
    xml = (
        '<Step id="S_01">'
        '<Goal id="G_01" priority="required">Ship the fixture change.</Goal>'
        '<Observation id="Obs_01">The fixture output was reviewed.</Observation>'
        '<Action id="A_01">Edited the fixture.</Action>'
        '<Task id="Task_01" status="satisfied" evidence_ref="Obs_01" '
        'for_goal="G_01" action_ref="A_01" '
        'runtime_ref="opaque-task-handle">Review the fixture output.</Task>'
        "</Step>"
    )
    _denial(monkeypatch)
    trace = parse(xml)
    result = validate(trace)
    # The Task itself is well-formed (its semantic rules are clean) …
    for rule in (
        "task_required_fields",
        "task_status_enum",
        "task_evidence_required",
        RULE_SEMANTIC_REF_TARGET_KIND,
    ):
        assert result.errors_by_rule[rule] == []
    # … but it closes NOTHING: the required Goal still demands a
    # Finding/Concluding and the Action still demands a recorded result.
    assert result.errors_by_rule[RULE_GOAL_DECLARED], (
        "a satisfied Task must not close a required Goal"
    )
    assert result.errors_by_rule[RULE_ACTION_RECORDED], (
        "a satisfied Task must not stand in for an Action's recorded result"
    )
    # runtime_ref stays an opaque string on the atom.
    task = [a for a in trace[0].atoms if a.kind == "Task"][0]
    assert task.runtime_ref == "opaque-task-handle"


def _semantic_showcase_xml() -> str:
    return (
        '<Step id="S_01">'
        '<Goal id="G_01" scope="trace">Ship the fixture change.</Goal>'
        '<Effect id="Effect_01" kind="io_write"/>'
        '<Action id="A_01">Edited the fixture.'
        '<Finding id="F_01">The fixture compiles.</Finding></Action>'
        '<Map id="Map_inputs" value_type="string" '
        'entries="{&quot;format&quot;:&quot;xml&quot;,&quot;target&quot;:'
        '&quot;fixture&quot;}">Inputs to the declared task.</Map>'
        '<Map id="Map_counts" value_type="integer" '
        'entries="{&quot;retries&quot;:2}"/>'
        '<Task id="Task_review" status="open" input_map="Map_inputs" '
        'for_goal="G_01" runtime_ref="opaque-task-handle">'
        "Review the fixture output.</Task>"
        '<Event id="Event_reviewed" source="review-worker" '
        'occurrence_id="review-17" event_type="review.completed" '
        'for_task="Task_review" map_ref="Map_inputs" effect_ref="Effect_01" '
        'external_ref="ers://opaque" '
        'timestamp="2026-09-05T08:30:00+00:00">'
        "The review result was recorded.</Event>"
        '<Concluding id="C_01" for_goal="G_01" status="met">'
        "REFER:F_01 closes the goal.</Concluding>"
        "</Step>"
    )


def test_map_event_task_roundtrip_preserves_identity():
    trace = parse(_semantic_showcase_xml())
    assert validate(trace).ok
    failures = _RUNNER._roundtrip_failures("showcase", trace)
    assert failures == [], "\n".join(failures)
    # Canonical ids survive every wire, including XML re-emission.
    original = {
        a.id: a.canonical_id
        for s in trace
        for a in s.atoms
        if a.kind in SEMANTIC_KINDS
    }
    assert len(original) == 4
    reparsed = parse(_RUNNER._trace_to_xml(from_yaml(to_yaml(from_json(to_json(trace))))))
    roundtripped = {
        a.id: a.canonical_id
        for s in reparsed
        for a in s.atoms
        if a.kind in SEMANTIC_KINDS
    }
    assert roundtripped == original


def _forced_collision_pair(monkeypatch, kind: str):
    """Two structurally DIFFERENT atoms of ``kind`` sharing a truncated
    digest, found by shrinking the REAL truncation seam — the payloads
    and the hash path are unpatched."""
    monkeypatch.setattr(
        "scholialang.atoms.CANONICAL_ID_HEX_LENGTH", 1
    )

    def build(index: int) -> Atom:
        if kind == "Map":
            atom = Map(
                id=f"Map_{index}",
                value_type="string",
                entries={"slot": f"value-{index}"},
                content=f"Recorded mapping {index}.",
            )
        elif kind == "Event":
            atom = Event(
                id=f"Event_{index}",
                source="worker",
                occurrence_id=f"occ-{index}",
                event_type="unit.recorded",
                content=f"The occurrence {index} was recorded.",
            )
        else:
            atom = Task(
                id=f"Task_{index}",
                status="open",
                content=f"Review the fixture output {index}.",
            )
        atom.canonical_id = compute_canonical_id(atom)
        return atom

    first = build(0)
    for index in range(1, 64):
        second = build(index)
        if second.canonical_id == first.canonical_id:
            return first, second
    raise AssertionError("no truncated collision found within 64 candidates")


@pytest.mark.parametrize(
    "case_id", ["map-distinct-payloads", "event-distinct-payloads", "task-distinct-payloads"]
)
def test_forced_canonical_collision_does_not_overwrite(
    case_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kind = {"map": "Map", "event": "Event", "task": "Task"}[case_id.split("-")[0]]
    first, second = _forced_collision_pair(monkeypatch, kind)
    assert first.canonical_id == second.canonical_id
    from scholialang.atoms import canonical_payload

    assert canonical_payload(first) != canonical_payload(second)

    registry = Registry(tmp_path / "registry.json")
    assert registry.put(first) is True
    bytes_before = (tmp_path / "registry.json").read_bytes()

    with pytest.raises(CanonicalCollisionError) as excinfo:
        registry.put(second)
    assert first.canonical_id in str(excinfo.value)
    assert "collision" in str(excinfo.value)

    # No overwrite, no merge: bytes, indexes, and reloaded state intact.
    assert (tmp_path / "registry.json").read_bytes() == bytes_before
    registry.reload()
    record = registry.get(first.canonical_id)
    assert record is not None
    assert record.get("id") == first.id
    assert len(registry) == 1


# ── Obligation v07-runtime-no-io ─────────────────────────────────────

_NO_IO_CASES = [
    f"{kind}-{op}"
    for kind in ("map", "event", "task")
    for op in ("construct", "parse", "validate", "hash", "serialize")
]


def _fresh_semantic_atom(kind: str) -> Atom:
    if kind == "map":
        return Map(
            id="Map_01",
            value_type="string",
            entries={"format": "xml"},
            content="Inputs.",
        )
    if kind == "event":
        return Event(
            id="Event_01",
            source="worker",
            occurrence_id="occ-1",
            event_type="unit.recorded",
            content="The occurrence was recorded.",
        )
    return Task(id="Task_01", status="open", content="Review the fixture output.")


_SEMANTIC_XML = {
    "map": '<Step id="S_01"><Map id="Map_01" value_type="string" '
    'entries="{&quot;format&quot;:&quot;xml&quot;}">Inputs.</Map></Step>',
    "event": '<Step id="S_01"><Event id="Event_01" source="worker" '
    'occurrence_id="occ-1" event_type="unit.recorded">'
    "The occurrence was recorded.</Event></Step>",
    "task": '<Step id="S_01"><Task id="Task_01" status="open">'
    "Review the fixture output.</Task></Step>",
}


@pytest.mark.parametrize("case_id", _NO_IO_CASES)
def test_obligation_no_io(case_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Construction, parsing, validation, hashing, and serialization of
    each new kind run under filesystem-write/subprocess/network denial."""
    kind, op = case_id.split("-", 1)
    # Warm all lazy imports BEFORE the denial hooks land.
    parse(_SEMANTIC_XML[kind])
    to_yaml(trace_from_dict({"steps": []}))
    _denial(monkeypatch)
    if op == "construct":
        atom = _fresh_semantic_atom(kind)
        assert atom.kind in SEMANTIC_KINDS
    elif op == "parse":
        trace = parse(_SEMANTIC_XML[kind])
        assert trace[0].atoms[0].kind in SEMANTIC_KINDS
    elif op == "validate":
        result = validate(parse(_SEMANTIC_XML[kind]))
        assert result.ok
    elif op == "hash":
        cid = compute_canonical_id(_fresh_semantic_atom(kind))
        assert cid.startswith("sha256:")
    else:  # serialize
        trace = parse(_SEMANTIC_XML[kind])
        assert to_json(trace) and to_yaml(trace) and to_canonical_json(trace)
        assert _RUNNER._trace_to_xml(trace)


# ── Obligation v07-runtime-roundtrip-no-caller-mutation ──────────────

_ROUNDTRIP_CASES = [
    f"{kind}-{fmt}-{claim}"
    for kind in ("map", "event", "task")
    for fmt in ("xml", "json", "yaml", "dict")
    for claim in ("missing-claim", "explicit-mismatch")
]

_MISMATCHED_CID = "sha256:000000000000"


def _document_for(kind: str, fmt: str, canonical_id: str | None):
    atom = _fresh_semantic_atom(kind)
    if canonical_id is None:
        atom.canonical_id = None
    else:
        atom.canonical_id = canonical_id
    trace = [scholialang.Step(id="S_01", atoms=[atom])]
    if fmt == "xml":
        cid_attr = f' canonical_id="{canonical_id}"' if canonical_id else ""
        body = {
            "map": f'<Map id="Map_01"{cid_attr} value_type="string" '
            'entries="{&quot;format&quot;:&quot;xml&quot;}">Inputs.</Map>',
            "event": f'<Event id="Event_01"{cid_attr} source="worker" '
            'occurrence_id="occ-1" event_type="unit.recorded">'
            "The occurrence was recorded.</Event>",
            "task": f'<Task id="Task_01"{cid_attr} status="open">'
            "Review the fixture output.</Task>",
        }[kind]
        return f'<Step id="S_01">{body}</Step>'
    if fmt == "json":
        return to_json(trace)
    if fmt == "yaml":
        return to_yaml(trace)
    return json.loads(to_json(trace))


@pytest.mark.parametrize("case_id", _ROUNDTRIP_CASES)
def test_obligation_roundtrip_no_caller_mutation(case_id: str) -> None:
    kind, fmt, claim = case_id.split("-", 2)
    mismatched = claim == "explicit-mismatch"
    claimed = _MISMATCHED_CID if mismatched else None

    # 1. Serialization never mutates the caller's object.
    atom = _fresh_semantic_atom(kind)
    atom.canonical_id = claimed
    entries_ref = atom.entries if isinstance(atom, Map) else None
    operators_ref = atom.operators
    children_ref = atom.children
    snapshot = copy.deepcopy(atom)
    trace = [scholialang.Step(id="S_01", atoms=[atom])]
    to_json(trace)
    to_yaml(trace)
    _RUNNER._trace_to_xml(trace)
    assert atom == snapshot, "serialization mutated the caller's atom"
    assert atom.canonical_id == claimed, (
        "serialization repaired/stamped the caller's canonical_id claim"
    )
    assert atom.operators is operators_ref
    assert atom.children is children_ref
    if entries_ref is not None:
        assert atom.entries is entries_ref

    # 2. Decoding computes a missing claim on the RESULT only, and never
    #    repairs an explicit mismatch.
    document = _document_for(kind, fmt, claimed)
    if fmt == "xml":
        decoded = parse(document)
    elif fmt == "json":
        decoded = from_json(document)
    elif fmt == "yaml":
        decoded = from_yaml(document)
    else:
        before = copy.deepcopy(document)
        decoded = trace_from_dict(copy.deepcopy(document))
        assert document == before, "dict decoding mutated the input payload"
    decoded_atom = decoded[0].atoms[0]
    expected_cid = compute_canonical_id(decoded_atom)
    if mismatched:
        assert decoded_atom.canonical_id == _MISMATCHED_CID, (
            "an explicit mismatched claim must be preserved for the "
            "validator, never silently repaired"
        )
        result = validate(decoded)
        assert result.errors_by_rule[RULE_CANONICAL_ID_WELL_FORMED], (
            "the mismatched claim must fail canonical_id_well_formed"
        )
        # Re-serialization retains the claim verbatim.
        recoded = from_json(to_json(decoded))
        assert recoded[0].atoms[0].canonical_id == _MISMATCHED_CID
    else:
        assert decoded_atom.canonical_id == expected_cid
        assert validate(decoded).ok
        # Typed values and opaque strings survive repeated round trips.
        twice = from_yaml(to_yaml(from_json(to_json(decoded))))
        assert _RUNNER._trace_semantic_view(twice) == _RUNNER._trace_semantic_view(
            decoded
        )


# ── Obligations: registry idempotence + provenance controls ──────────


@pytest.mark.parametrize(
    "case_id", ["map-equal-payload", "task-equal-payload", "event-equal-payload-separate-traces"]
)
def test_obligation_identical_payload_registry(case_id: str, tmp_path: Path) -> None:
    """Equal full canonical payloads with distinct local references share
    identity; registration is idempotent, never a structural collision;
    the first record survives a disk reload."""
    kind = case_id.split("-")[0]
    first = _fresh_semantic_atom(kind)
    second = _fresh_semantic_atom(kind)
    second.id = f"{first.kind}_other_local_ref"
    first.canonical_id = compute_canonical_id(first)
    second.canonical_id = compute_canonical_id(second)
    assert first.canonical_id == second.canonical_id  # id is not identity

    registry = Registry(tmp_path / "registry.json")
    assert registry.put(first) is True
    bytes_before = (tmp_path / "registry.json").read_bytes()
    assert registry.put(second) is False  # idempotent, not a collision
    assert (tmp_path / "registry.json").read_bytes() == bytes_before
    registry.reload()
    record = registry.get(first.canonical_id)
    assert record is not None and record.get("id") == first.id

    if kind == "event":
        # Separate-trace registry controls do NOT waive the same-trace
        # occurrence-pair duplicate rule.
        xml = _SEMANTIC_XML["event"]
        one_trace = parse(
            '<Step id="S_01">'
            '<Event id="Event_a" source="worker" occurrence_id="occ-1" '
            'event_type="unit.recorded">The occurrence was recorded.</Event>'
            '<Event id="Event_b" source="worker" occurrence_id="occ-1" '
            'event_type="unit.recorded">The occurrence was recorded.</Event>'
            "</Step>"
        )
        result = validate(one_trace)
        assert result.errors_by_rule["event_occurrence_unique"], (
            "same-trace occurrence pair must still be rejected"
        )
        assert validate(parse(xml)).ok


@pytest.mark.parametrize("case_id", ["event-timestamp-only", "legacy-provenance-control"])
def test_obligation_provenance_registry(case_id: str, tmp_path: Path) -> None:
    """Timestamp-only differences are provenance: canonical identity is
    retained and the registry treats the re-put as idempotent — no
    global hash/provenance rule changed."""
    if case_id == "event-timestamp-only":
        first = _fresh_semantic_atom("event")
        first.timestamp = "2026-09-05T08:30:00+00:00"
        second = _fresh_semantic_atom("event")
        second.timestamp = "2026-09-05T09:45:00+00:00"
    else:
        first = scholialang.Observation(
            id="Obs_01", content="Recorded.", timestamp="2026-09-05T08:30:00Z"
        )
        second = scholialang.Observation(
            id="Obs_01", content="Recorded.", timestamp="2026-09-05T09:45:00Z"
        )
    first.canonical_id = compute_canonical_id(first)
    second.canonical_id = compute_canonical_id(second)
    assert first.canonical_id == second.canonical_id

    registry = Registry(tmp_path / "registry.json")
    assert registry.put(first) is True
    assert registry.put(second) is False  # provenance is not a collision
    registry.reload()
    record = registry.get(first.canonical_id)
    assert record is not None
    stored_attrs = record.get("attrs", {})
    assert stored_attrs.get("timestamp") == first.timestamp, (
        "the first record's provenance must be preserved, not replaced"
    )


# ── Obligation v07-runtime-in-memory-map-key-and-object-shapes ───────

_IN_MEMORY_CASES = [
    "map-integer-key",
    "map-boolean-key",
    "map-object-key",
    "map-arbitrary-value",
    "map-nan-value",
    "map-infinity-value",
    "map-negative-infinity-value",
    "map-bad-operators",
    "map-nonempty-children",
    "map-wrong-field-type",
    "event-bad-operators",
    "event-nonempty-children",
    "event-wrong-field-type",
    "task-bad-operators",
    "task-nonempty-children",
    "task-wrong-field-type",
]


@pytest.mark.parametrize("case_id", _IN_MEMORY_CASES)
def test_obligation_in_memory_shapes(case_id: str) -> None:
    kind = case_id.split("-")[0]
    atom = _fresh_semantic_atom(kind)

    if case_id.endswith("-key"):
        key = {"map-integer-key": 1, "map-boolean-key": True}.get(case_id, object())
        payload = json.loads(to_json([scholialang.Step(id="S_01", atoms=[atom])]))
        payload["steps"][0]["atoms"][0]["entries"] = {key: "value"}
        with pytest.raises(SemanticShapeError) as excinfo:
            trace_from_dict(payload)
        assert excinfo.value.rule == RULE_MAP_ENTRIES_SHAPE
        # The same true-nonstring-key atom also fails validate().
        assert isinstance(atom, Map)
        atom.entries = {key: "value"}
        result = validate([scholialang.Step(id="S_01", atoms=[atom])])
        assert result.errors_by_rule[RULE_MAP_ENTRIES_SHAPE]
        return

    if case_id == "map-arbitrary-value":
        assert isinstance(atom, Map)
        atom.entries = {"slot": object()}
        result = validate([scholialang.Step(id="S_01", atoms=[atom])])
        assert result.errors_by_rule[RULE_MAP_ENTRIES_TYPED], (
            "arbitrary objects must be rejected without coercion"
        )
        return

    if "-nan-" in case_id or "infinity" in case_id:
        value = {
            "map-nan-value": float("nan"),
            "map-infinity-value": float("inf"),
            "map-negative-infinity-value": float("-inf"),
        }[case_id]
        assert isinstance(atom, Map)
        atom.value_type = "integer"
        atom.entries = {"slot": value}
        result = validate([scholialang.Step(id="S_01", atoms=[atom])])
        assert result.errors_by_rule[RULE_MAP_ENTRIES_TYPED], (
            "nonfinite in-memory values are validate-phase typed failures"
        )
        return

    if case_id.endswith("-bad-operators"):
        atom.operators = [1, 2]  # type: ignore[list-item]
        result = validate([scholialang.Step(id="S_01", atoms=[atom])])
        assert result.errors_by_rule[RULE_SEMANTIC_OPERATORS_LIST]
        return

    if case_id.endswith("-nonempty-children"):
        atom.children = [scholialang.Thinking(content="nested")]
        result = validate([scholialang.Step(id="S_01", atoms=[atom])])
        assert result.errors_by_rule[RULE_SEMANTIC_CHILDREN_EMPTY]
        return

    # wrong-field-type: a structurally wrong scalar fails validation
    # with the owning kind's structural rule.
    if kind == "map":
        assert isinstance(atom, Map)
        atom.entries = "not-a-mapping"  # type: ignore[assignment]
        result = validate([scholialang.Step(id="S_01", atoms=[atom])])
        assert result.errors_by_rule[RULE_MAP_ENTRIES_SHAPE]
    elif kind == "event":
        assert isinstance(atom, Event)
        atom.source = 7  # type: ignore[assignment]
        result = validate([scholialang.Step(id="S_01", atoms=[atom])])
        assert result.errors_by_rule["event_required_fields"]
    else:
        assert isinstance(atom, Task)
        atom.status = 5  # type: ignore[assignment]
        result = validate([scholialang.Step(id="S_01", atoms=[atom])])
        assert result.errors_by_rule[RULE_TASK_STATUS_ENUM]


# ── Obligation v07-runtime-canonical-reference-resolution ────────────

_TYPED_PAIRS = [
    ("Event", "for_task", "Task"),
    ("Event", "for_action", "Action"),
    ("Event", "for_goal", "Goal"),
    ("Event", "effect_ref", "Effect"),
    ("Event", "map_ref", "Map"),
    ("Task", "for_goal", "Goal"),
    ("Task", "input_map", "Map"),
    ("Task", "output_map", "Map"),
    ("Task", "action_ref", "Action"),
    ("Task", "evidence_ref", "Observation"),
    ("Task", "evidence_ref", "Evidence"),
    ("Task", "evidence_ref", "Finding"),
    ("Task", "evidence_ref", "Concluding"),
]

_MAP_TARGET_KINDS = [k for k in ATOM_KINDS]  # all 35 kinds are legal targets

_CANONICAL_REF_CASES = [
    f"Map.entries:{kind}:canonical-{order}"
    for kind in _MAP_TARGET_KINDS
    for order in ("prior", "forward")
] + [
    f"{owner}.{field}:{target}:canonical-{order}"
    for owner, field, target in _TYPED_PAIRS
    for order in ("prior", "forward")
]

assert len(_CANONICAL_REF_CASES) == 96


def _target_atom(kind: str) -> Atom:
    """A minimal target atom of ``kind`` with its canonical_id stamped."""
    kwargs: dict = {}
    if kind == "Concluding":
        kwargs["for_goal"] = "G_target"
    if kind == "Map":
        kwargs.update(value_type="string", entries={"seed": "target"})
    if kind == "Event":
        kwargs.update(
            source="worker", occurrence_id="occ-target", event_type="unit.recorded"
        )
    if kind == "Task":
        kwargs.update(status="open")
    cls = atom_class_for_kind(kind)
    assert cls is not None
    atom = cls(**kwargs)
    atom.id = f"{kind}_target"
    atom.content = f"Target {kind} for the reference matrix."
    atom.canonical_id = compute_canonical_id(atom)
    return atom


@pytest.mark.parametrize("case_id", _CANONICAL_REF_CASES)
def test_obligation_canonical_reference(case_id: str) -> None:
    """Actual computed canonical IDs work as exact reference values for
    every permitted Map target kind and every typed field/target pair,
    in both prior and forward declaration order."""
    lhs, target_kind, order = case_id.split(":")
    owner_kind, field = lhs.split(".")
    target = _target_atom(target_kind)
    assert target.canonical_id is not None

    if owner_kind == "Map":
        referrer: Atom = Map(
            id="Map_ref",
            value_type="atom_ref",
            entries={"target": target.canonical_id},
            content="References the target by canonical id.",
        )
        checked_rule = RULE_MAP_REF_RESOLVES
    elif owner_kind == "Event":
        referrer = Event(
            id="Event_ref",
            source="worker",
            occurrence_id="occ-ref",
            event_type="unit.recorded",
            content="References the target by canonical id.",
            **{field: target.canonical_id},
        )
        checked_rule = RULE_SEMANTIC_REF_TARGET_KIND
    else:
        referrer = Task(
            id="Task_ref",
            status="open",
            content="References the target by canonical id.",
            **{field: target.canonical_id},
        )
        checked_rule = RULE_SEMANTIC_REF_TARGET_KIND

    atoms = [target, referrer] if order == "canonical-prior" else [referrer, target]
    trace = [scholialang.Step(id="S_01", atoms=atoms)]
    result = validate(trace)
    assert result.errors_by_rule[checked_rule] == [], (
        f"{case_id}: {[e.message for e in result.errors_by_rule[checked_rule]]}"
    )
    # Rejection is preserved: the same reference dangling fails.
    dangling = "sha256:ffffffffffff"
    if owner_kind == "Map":
        assert isinstance(referrer, Map)
        referrer.entries = {"target": dangling}
    else:
        setattr(referrer, field, dangling)
    result_bad = validate([scholialang.Step(id="S_01", atoms=atoms)])
    assert result_bad.errors_by_rule[checked_rule], (
        f"{case_id}: dangling canonical reference must be rejected"
    )


def test_canonical_reference_rejects_self_step_and_wrong_kind() -> None:
    """The matrix preserves self/Step/wrong-kind rejection and never
    resolves opaque correlators as references."""
    self_map = Map(
        id="Map_self", value_type="atom_ref", entries={}, content="Self ref."
    )
    self_map.canonical_id = compute_canonical_id(self_map)
    self_map.entries = {"me": self_map.canonical_id}
    result = validate([scholialang.Step(id="S_01", atoms=[self_map])])
    assert result.errors_by_rule[RULE_MAP_REF_RESOLVES]

    step_ref = Map(
        id="Map_stepref",
        value_type="atom_ref",
        entries={"s": "S_01"},
        content="Step ref.",
    )
    result = validate([scholialang.Step(id="S_01", atoms=[step_ref])])
    assert result.errors_by_rule[RULE_MAP_REF_RESOLVES]

    goal = _target_atom("Goal")
    event = Event(
        id="Event_wrong",
        source="worker",
        occurrence_id="occ-w",
        event_type="unit.recorded",
        content="Wrong-kind target.",
        for_task=goal.canonical_id,
    )
    result = validate([scholialang.Step(id="S_01", atoms=[goal, event])])
    assert result.errors_by_rule[RULE_SEMANTIC_REF_TARGET_KIND]

    # Opaque correlators are NOT references: a runtime_ref equal to a
    # canonical id resolves nothing and errors nothing.
    task = Task(
        id="Task_opaque",
        status="open",
        content="Opaque handle.",
        runtime_ref=goal.canonical_id,
    )
    result = validate([scholialang.Step(id="S_01", atoms=[goal, task])])
    assert result.errors_by_rule[RULE_SEMANTIC_REF_TARGET_KIND] == []


# ── Obligation v07-runtime-new-field-canonical-identity ──────────────

_IDENTITY_CASES = [
    "map-value-type",
    "map-key",
    "map-value",
    "map-content",
    "event-source",
    "event-occurrence-id",
    "event-event-type",
    "event-content",
    "event-for-task",
    "event-for-action",
    "event-for-goal",
    "event-effect-ref",
    "event-map-ref",
    "event-external-ref",
    "task-status",
    "task-content",
    "task-for-goal",
    "task-input-map",
    "task-output-map",
    "task-action-ref",
    "task-evidence-ref",
    "task-runtime-ref",
]


@pytest.mark.parametrize("case_id", _IDENTITY_CASES)
def test_obligation_new_field_canonical_identity(case_id: str) -> None:
    """Structural field/content changes change canonical identity."""
    kind, dashed = case_id.split("-", 1)
    base = _fresh_semantic_atom(kind)

    def mutate(atom: Atom) -> None:
        if case_id == "map-value-type":
            assert isinstance(atom, Map)
            atom.value_type = "boolean"
            atom.entries = {"format": True}
        elif case_id == "map-key":
            assert isinstance(atom, Map)
            atom.entries = {"other_key": "xml"}
        elif case_id == "map-value":
            assert isinstance(atom, Map)
            atom.entries = {"format": "yaml"}
        elif dashed == "content":
            atom.content = atom.content + " (changed)"
        elif case_id == "task-status":
            atom.status = "withdrawn"  # type: ignore[attr-defined]
        else:
            field = dashed.replace("-", "_")
            setattr(atom, field, "changed-structural-value")

    changed = _fresh_semantic_atom(kind)
    mutate(changed)
    assert compute_canonical_id(base) != compute_canonical_id(changed), (
        f"{case_id}: a structural change must change canonical identity"
    )

    if kind == "map":
        # Insertion order stays identity-neutral.
        left = Map(value_type="string", entries={"a": "1", "b": "2"})
        right = Map(value_type="string", entries={"b": "2", "a": "1"})
        assert compute_canonical_id(left) == compute_canonical_id(right)
    if kind == "event":
        # Timestamp remains excluded provenance.
        stamped = _fresh_semantic_atom("event")
        stamped.timestamp = "2026-09-05T08:30:00+00:00"  # type: ignore[attr-defined]
        assert compute_canonical_id(stamped) == compute_canonical_id(base)


# ── Obligation v07-runtime-opaque-correlators ────────────────────────

_OPAQUE_CASES = [
    "event-url",
    "event-local-id-like",
    "task-url",
    "task-local-id-like",
    "task-satisfied-no-execution",
]


@pytest.mark.parametrize("case_id", _OPAQUE_CASES)
def test_obligation_opaque_correlators(
    case_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """URL-like and id-like opaque correlators stay opaque under denial
    hooks; Event creation and satisfied-Task validation neither notify,
    start work, authorize transitions, nor replace legacy closure."""
    if case_id == "task-satisfied-no-execution":
        xml = (
            '<Step id="S_01">'
            '<Goal id="G_01" priority="required">Ship it.</Goal>'
            '<Observation id="Obs_01">Reviewed.</Observation>'
            '<Task id="Task_01" status="satisfied" evidence_ref="Obs_01" '
            'runtime_ref="https://runtime.invalid/tasks/42">Review.</Task>'
            "</Step>"
        )
        _denial(monkeypatch)
        trace = parse(xml)
        result = validate(trace)
        assert result.errors_by_rule["task_evidence_required"] == []
        assert result.errors_by_rule[RULE_GOAL_DECLARED], (
            "satisfied Task must not close the required Goal"
        )
        return

    kind, ref_shape = case_id.split("-", 1)
    opaque_value = (
        "https://external.invalid/events/17"
        if ref_shape == "url"
        else "Obs_01"  # looks exactly like a local id — still opaque
    )
    if kind == "event":
        xml = (
            '<Step id="S_01">'
            '<Observation id="Obs_01">Recorded.</Observation>'
            f'<Event id="Event_01" source="worker" occurrence_id="occ-1" '
            f'event_type="unit.recorded" external_ref="{opaque_value}">'
            "The occurrence was recorded.</Event>"
            "</Step>"
        )
        field = "external_ref"
    else:
        xml = (
            '<Step id="S_01">'
            '<Observation id="Obs_01">Recorded.</Observation>'
            f'<Task id="Task_01" status="open" runtime_ref="{opaque_value}">'
            "Review the fixture output.</Task>"
            "</Step>"
        )
        field = "runtime_ref"
    _denial(monkeypatch)
    trace = parse(xml)
    result = validate(trace)
    assert result.ok, [e.message for e in result.errors]
    holder = trace[0].atoms[1]
    assert getattr(holder, field) == opaque_value, (
        "the opaque correlator must be preserved verbatim, never "
        "interpreted or dereferenced"
    )


# ── Obligation v07-runtime-legacy-artifact-probe ─────────────────────

_LEGACY_PROBE_CASES = [
    "legacy-full-corpus",
    "old-parser-map",
    "old-parser-event",
    "old-parser-task",
    "new-legacy-profile",
    "new-unknown-profile",
]


@pytest.mark.parametrize("case_id", _LEGACY_PROBE_CASES)
def test_obligation_legacy_artifact_probe(case_id: str) -> None:
    if case_id == "new-legacy-profile":
        trace = parse(_SEMANTIC_XML["task"])
        errors = validate(trace, profile="0.6.2").errors_by_rule[
            RULE_GRAMMAR_PROFILE_UNSUPPORTED
        ]
        assert errors and "0.6.2" in errors[0].message
        return
    if case_id == "new-unknown-profile":
        errors = validate([], profile="0.9").errors_by_rule[
            RULE_GRAMMAR_PROFILE_UNSUPPORTED
        ]
        assert errors and "0.9" in errors[0].message
        return

    old_python = os.environ.get(_OLD_PY_ENV)
    if not old_python:
        if os.environ.get(_REQUIRE_OLD_ENV) == "1":
            pytest.fail(
                f"{_REQUIRE_OLD_ENV}=1 but {_OLD_PY_ENV} is not set"
            )
        pytest.skip(f"{_OLD_PY_ENV} not set (old-artifact env unavailable)")

    if case_id == "legacy-full-corpus":
        fixtures_root = _REPO_ROOT / "tests" / "fixtures" / "scholia"
        probe = (
            "import sys, json\n"
            "from pathlib import Path\n"
            "import scholialang\n"
            "from scholialang.parser import parse\n"
            "from scholialang.validator import validate\n"
            "root = Path(sys.argv[1])\n"
            "files = sorted(list((root/'v03_known_corpus').glob('*.xml'))"
            " + list((root/'v031_atoms').glob('*.xml')))\n"
            "assert files\n"
            "bad = []\n"
            "for f in files:\n"
            "    r = validate(parse(f.read_text(encoding='utf-8')))\n"
            "    if not r.ok:\n"
            "        bad.append(f.name)\n"
            "print(json.dumps({'version': scholialang.__version__,"
            " 'checked': len(files), 'bad': bad}))\n"
        )
        proc = subprocess.run(
            [old_python, "-c", probe, str(fixtures_root)],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "PYTHONPATH": ""},
        )
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["version"] == "0.7.2"
        assert out["bad"] == [], f"old artifact rejected legacy corpus: {out}"
        return

    kind = {"old-parser-map": "map", "old-parser-event": "event", "old-parser-task": "task"}[
        case_id
    ]
    kind_name = {"map": "Map", "event": "Event", "task": "Task"}[kind]
    probe = (
        "import json, scholialang\n"
        "from scholialang.parser import parse\n"
        "try:\n"
        f"    parse({_SEMANTIC_XML[kind]!r})\n"
        "    print(json.dumps({'version': scholialang.__version__, 'error': None}))\n"
        "except Exception as exc:\n"
        "    print(json.dumps({'version': scholialang.__version__,"
        " 'error': f'{type(exc).__name__}: {exc}'}))\n"
    )
    proc = subprocess.run(
        [old_python, "-c", probe],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PYTHONPATH": ""},
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["version"] == "0.7.2"
    assert out["error"] is not None, (
        f"the installed 0.7.2 artifact unexpectedly parsed <{kind_name}>"
    )
    assert kind_name in out["error"], (
        f"old unknown-kind error does not name the kind: {out['error']}"
    )


# ── Obligation v07-runtime-packaging-parity ──────────────────────────


def test_obligation_packaging_parity() -> None:
    """One executable parity node run per environment (source, then the
    wheel- and sdist-installed gate environments): versions, catalog,
    and import origin agree; installed runs prove a non-source origin
    via ``SCHOLIALANG_EXPECT_IMPORT_PREFIX``."""
    assert scholialang.__version__ == "0.7.3"
    assert len(ATOM_KINDS) == 35
    assert CANONICAL_ID_HEX_LENGTH == 12
    origin = Path(scholialang.__file__ or "").resolve()
    expected_prefix = os.environ.get(_IMPORT_PREFIX_ENV)
    if expected_prefix:
        assert str(origin).startswith(str(Path(expected_prefix).resolve())), (
            f"import origin {origin} is outside the expected environment "
            f"{expected_prefix}"
        )
        assert _REPO_ROOT / "src" not in origin.parents, (
            "installed-environment run leaked back to the source tree"
        )
    else:
        assert (_REPO_ROOT / "src") in origin.parents, (
            f"source run must import from the source tree; got {origin}"
        )


# ── Obligation inventory cross-check ─────────────────────────────────


@_corpus_skip
def test_runtime_obligation_case_ids_are_fully_bound():
    """Every obligation case id the accepted suite declares is bound to
    a concrete executable node in this module — the obligation set may
    not silently shrink."""
    declared = {
        o["id"]: list(o.get("required_case_ids", []))
        for o in _SUITE.get("runtime_obligations", [])
    }
    bound = {
        "v07-runtime-no-io": _NO_IO_CASES,
        "v07-runtime-roundtrip-no-caller-mutation": _ROUNDTRIP_CASES,
        "v07-runtime-forced-canonical-collision": [
            "map-distinct-payloads",
            "event-distinct-payloads",
            "task-distinct-payloads",
        ],
        "v07-runtime-identical-payload-registry": [
            "map-equal-payload",
            "task-equal-payload",
            "event-equal-payload-separate-traces",
        ],
        "v07-runtime-provenance-registry": [
            "event-timestamp-only",
            "legacy-provenance-control",
        ],
        "v07-runtime-in-memory-map-key-and-object-shapes": _IN_MEMORY_CASES,
        "v07-runtime-canonical-reference-resolution": _CANONICAL_REF_CASES,
        "v07-runtime-new-field-canonical-identity": _IDENTITY_CASES,
        "v07-runtime-opaque-correlators": _OPAQUE_CASES,
        "v07-runtime-legacy-artifact-probe": _LEGACY_PROBE_CASES,
        "v07-runtime-packaging-parity": ["source", "wheel-installed", "sdist-installed"],
    }
    assert set(declared) == set(bound), (
        f"obligation ids differ: declared {sorted(declared)}, bound {sorted(bound)}"
    )
    for obligation_id, declared_cases in declared.items():
        assert sorted(bound[obligation_id]) == sorted(declared_cases), (
            f"{obligation_id}: bound case ids do not match the declared "
            "required_case_ids"
        )
