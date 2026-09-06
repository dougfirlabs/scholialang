"""Cross-format canonical targets and byte-exact registry collision guards."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

import scholialang as api
import scholialang.atoms as atoms_module
from scholialang.registry import CanonicalCollisionError
from scholialang.serializer import (
    from_json, from_yaml, to_json, to_yaml, trace_from_dict, trace_to_dict,
)

FORMATS = ("xml", "json", "yaml", "dict")
TARGET_KINDS = (
    "Action", "Observation", "Thinking", "Concluding", "Contradiction",
    "Evidence", "Finding", "Hypothesis", "Retract", "Uncertainty",
    "Alternative", "Branch", "Deciding", "Loop", "Parallel", "Implication",
    "Map", "Print", "Reference", "Storing", "Handoff", "Question", "Review",
    "Budget", "Confidence", "Constraint", "Cost", "Event", "EventRef", "Goal",
    "Task", "Edge", "Effect", "Meta", "Ref",
)
TYPED_PAIRS = (
    ("Event", "for_task", "Task"), ("Event", "for_action", "Action"),
    ("Event", "for_goal", "Goal"), ("Event", "effect_ref", "Effect"),
    ("Event", "map_ref", "Map"), ("Task", "for_goal", "Goal"),
    ("Task", "input_map", "Map"), ("Task", "output_map", "Map"),
    ("Task", "action_ref", "Action"), ("Task", "evidence_ref", "Observation"),
    ("Task", "evidence_ref", "Evidence"), ("Task", "evidence_ref", "Finding"),
    ("Task", "evidence_ref", "Concluding"),
)
REFERENCE_CASES = [
    f"{owner}.{field}:{kind}:canonical-{order}"
    for owner, field, kind in [("Map", "entries", kind) for kind in TARGET_KINDS] + list(TYPED_PAIRS)
    for order in ("prior", "forward")
]
assert len(REFERENCE_CASES) == len(set(REFERENCE_CASES)) == 96


def _atom(kind, suffix="target", **kwargs):
    defaults = {"Map": {"value_type": "integer", "entries": {"n": 1}},
                "Event": {"source": "probe", "occurrence_id": suffix, "event_type": "review.done"},
                "Task": {"status": "open"}}.get(kind, {})
    return getattr(api, kind)(id=f"{kind}_{suffix}", content=f"Recorded {kind} {suffix}.", **(defaults | kwargs))


def _target(kind):
    support = []
    if kind == "Concluding":
        support = [_atom("Goal", "support"), _atom("Observation", "support")]
        target = api.Concluding(id="Concluding_target", for_goal=support[0].id,
                                content=f"REFER:{support[1].id} resolves the goal.")
    else:
        target = _atom(kind)
    if kind in {"Action", "Deciding", "Review"}:
        target.children = [_atom("Finding", "result")]
    if kind == "Hypothesis":
        support.append(_atom("Uncertainty", "support", on=target.id, confidence="low"))
    if kind == "Retract":
        support.append(_atom("Finding", "prior"))
        target.target = support[0].id
    if kind == "Effect":
        target.effect_kind = "pure"
    if kind == "Edge":
        target.edge_type, target.target = "depends_on", "src/example.py"
    if kind == "Ref":
        target.ref_type, target.target = "test_owner", "tests/test_example.py"
    if kind == "Alternative":
        roots = support + [_atom("Deciding", "owner", children=[target, _atom("Finding", "decision")])]
    else:
        roots = support + [target]
    for value in _walk(roots):
        value.canonical_id = api.compute_canonical_id(value)
    assert not api.validate([api.Step(id="Step_seed", atoms=roots)]).errors
    return target, roots


def _walk(values):
    for value in values:
        yield value
        yield from _walk(value.children)


def _roundtrip(trace, fmt):
    if fmt == "xml":
        return api.parse('<Step id="Step_matrix">' + "".join(api.atom_to_xml(value) for value in trace[0].atoms) + "</Step>")
    if fmt == "json":
        return from_json(to_json(trace))
    if fmt == "yaml":
        return from_yaml(to_yaml(trace))
    return trace_from_dict(trace_to_dict(trace))


@pytest.mark.parametrize("case_id", REFERENCE_CASES)
@pytest.mark.parametrize("fmt", FORMATS)
def test_current35_canonical_targets_survive_all_formats(case_id, fmt):
    assert set(TARGET_KINDS) == set(api.ATOM_KINDS)
    lhs, kind, order = case_id.split(":")
    owner, field = lhs.split(".")
    target, roots = _target(kind)
    source = _atom(owner, "source")
    if owner == "Map":
        source.value_type = "atom_ref"
        source.entries = {"target": target.canonical_id}
    else:
        setattr(source, field, target.canonical_id)
    source.canonical_id = api.compute_canonical_id(source)
    trace = [api.Step(id="Step_matrix", atoms=roots + [source] if order == "canonical-prior" else [source] + roots)]
    assert not api.validate(trace).errors
    original = copy.deepcopy(trace)
    restored = _roundtrip(trace, fmt)
    assert trace == original, "Serialization must not mutate caller-owned atoms"
    assert not api.validate(restored).errors
    by_id = {value.id: value for value in _walk(restored[0].atoms)}
    assert by_id[target.id].canonical_id == target.canonical_id
    assert by_id[source.id].canonical_id == source.canonical_id
    assert getattr(by_id[source.id], field) == getattr(source, field)


@pytest.mark.parametrize("fmt", ("json", "yaml", "dict"))
@pytest.mark.parametrize("claim", (None, "sha256:000000000000", "sha256:malformed"))
def test_legacy_decoder_preserves_claims_and_computes_only_missing_ids(fmt, claim):
    value = _atom("Observation")
    value.canonical_id = claim
    original = copy.deepcopy(value)
    back = _roundtrip([api.Step(id="Step_matrix", atoms=[value])], fmt)[0].atoms[0]
    assert value == original
    assert back.canonical_id == (claim if claim is not None else api.compute_canonical_id(value))
    errors = api.validate([api.Step(id="Step_matrix", atoms=[back])]).errors
    assert bool([error for error in errors if error.rule == "canonical_id_well_formed"]) == (claim is not None)


@pytest.mark.parametrize("kind", TARGET_KINDS)
def test_current35_reference_target_ids_survive_or_are_computed_without_claim_repair(kind):
    target, roots = _target(kind)
    document = trace_to_dict([api.Step(id="Step_matrix", atoms=roots)])
    def wire_atoms(values):
        for value in values:
            yield value
            yield from wire_atoms(value.get("children", []))
    target_payload = next(value for value in wire_atoms(document["steps"][0]["atoms"]) if value["id"] == target.id)
    del target_payload["canonical_id"]
    original = copy.deepcopy(document)
    restored = trace_from_dict(document)
    assert document == original
    actual = next(value for value in _walk(restored[0].atoms) if value.id == target.id)
    assert actual.canonical_id == target.canonical_id
    assert not api.validate(restored).errors
    target_payload["canonical_id"] = "sha256:000000000000"
    original = copy.deepcopy(document)
    restored = trace_from_dict(document)
    assert document == original
    actual = next(value for value in _walk(restored[0].atoms) if value.id == target.id)
    assert actual.canonical_id == "sha256:000000000000"
    assert any(error.rule == "canonical_id_well_formed" and error.atom_id == target.id
               for error in api.validate(restored).errors)


@pytest.mark.parametrize("left,right", [(-0.0, 0.0), (1, 1.0)], ids=["signed-zero", "integer-float"])
def test_registry_distinguishes_python_equal_canonical_json_numbers(left, right, monkeypatch, tmp_path):
    first = api.Cost(id="Cost_one", content="Recorded cost.", dollars=left)
    second = api.Cost(id="Cost_two", content="Recorded cost.", dollars=right)
    for value in (first, second):
        assert not api.validate([api.Step(id="Step_cost", atoms=[value])]).errors
    assert api.compute_canonical_id(first) != api.compute_canonical_id(second)
    payloads = [atoms_module.canonical_payload(value) for value in (first, second)]
    assert payloads[0] == payloads[1]
    encoded = [json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() for payload in payloads]
    assert encoded[0] != encoded[1]
    calls = []
    def sha256(data):
        calls.append(data)
        return SimpleNamespace(hexdigest=lambda: "a" * 64)
    monkeypatch.setattr(atoms_module, "hashlib", SimpleNamespace(sha256=sha256))
    for value in (first, second):
        value.canonical_id = api.compute_canonical_id(value)
        assert not api.validate([api.Step(id="Step_cost", atoms=[value])]).errors
    assert all(data in calls for data in encoded)
    registry = api.Registry(tmp_path / "registry.json")
    assert registry.put(first, sidecar={"writer": "first"})
    before = registry.path.read_bytes()
    record = copy.deepcopy(registry.get(first.canonical_id))
    with pytest.raises(CanonicalCollisionError):
        registry.put(second, sidecar={"writer": "second"})
    assert registry.path.read_bytes() == before
    assert registry.get(first.canonical_id) == record and len(registry) == 1
