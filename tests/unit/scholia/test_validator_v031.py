"""v0.3.1 — primitive-hook validator acceptance + rejection tests.

The validator added one rule in v0.3.1 (``RULE_V031_OPTIONAL_FIELDS``)
and ``ValidationResult`` gained a ``scholia_validator_version`` field.
Coverage here is field-by-field: each new optional attribute /
sub-element is exercised with at least one valid value, at least one
invalid value, and the absence-of-field case (which must validate
trivially as the v0.3 shape).

Parser-side rejection of malformed v0.3.1 values is also tested here
because the two layers form one closed-set contract; if the validator
re-validates AST-mediated traces, the parser must reject the same
values when input comes through XML-ish.
"""
from __future__ import annotations

import pytest

from scholialang.atoms import (
    SCHOLIA_VALIDATOR_VERSION,
    V031_EDGE_TYPES,
    V031_EFFECT_KINDS,
    V031_META_CRITICALITIES,
    V031_REF_TYPES,
    Edge,
    Effect,
    Finding,
    Goal,
    Meta,
    Observation,
    Ref,
    Step,
)
from scholialang.parser import ScholiaParseError, parse
from scholialang.validator import (
    RULE_V031_OPTIONAL_FIELDS,
    check_v031_optional_fields,
    validate,
)


def _idx(trace):
    from scholialang.validator import _build_id_index  # type: ignore

    return _build_id_index(trace)


def _wrap(*atoms) -> list[Step]:
    """Trivial single-Step wrapper for the small-AST cases.

    Each test that needs a required-Goal closure builds its own
    Goal+Finding pair; this helper just keeps the boilerplate tight.
    """
    return [Step(id="Step_01", name="t", atoms=list(atoms))]


# ── ValidationResult.scholia_validator_version ───────────────────────


def test_validation_result_reports_validator_version():
    """Rule-set ran → result carries the version string set on the module."""
    trace = _wrap(Observation(id="Obs_01"))
    result = validate(trace)
    assert result.scholia_validator_version == SCHOLIA_VALIDATOR_VERSION
    assert result.scholia_validator_version == "0.5.0"


# ── Backwards-compat: v0.3 atoms validate unchanged ──────────────────


def test_v0_3_atom_with_no_v031_fields_validates():
    """Absence of every v0.3.1 field MUST stay valid — the v0.3 shape."""
    goal = Goal(id="G_01", scope="trace", priority="required")
    obs = Observation(id="Obs_01", content="plain v0.3 observation.")
    finding = Finding(id="F_01", for_goal="G_01", status="met", content="met.")
    trace = _wrap(goal, obs, finding)
    result = validate(trace)
    assert result.ok, result.summary()


# ── <Observation location="..."> ─────────────────────────────────────


def test_v031_observation_location_valid():
    obs = Observation(id="Obs_01", location="src/foo.py:10:20")
    assert check_v031_optional_fields(_wrap(obs), _idx(_wrap(obs))) == []


def test_v031_observation_location_invalid_no_lines():
    obs = Observation(id="Obs_01", location="src/foo.py")  # missing :start:end
    errs = check_v031_optional_fields(_wrap(obs), _idx(_wrap(obs)))
    assert errs and errs[0].rule == RULE_V031_OPTIONAL_FIELDS
    assert "location" in errs[0].message


def test_v031_observation_location_invalid_non_numeric():
    obs = Observation(id="Obs_01", location="src/foo.py:start:end")
    errs = check_v031_optional_fields(_wrap(obs), _idx(_wrap(obs)))
    assert errs and errs[0].rule == RULE_V031_OPTIONAL_FIELDS


def test_v031_observation_location_absent_validates():
    obs = Observation(id="Obs_01")  # no location attr
    assert check_v031_optional_fields(_wrap(obs), _idx(_wrap(obs))) == []


# ── <Observation confidence="..."> ───────────────────────────────────


@pytest.mark.parametrize("value", ["0.0", "0.5", "1.0", "0.999"])
def test_v031_observation_confidence_valid_boundaries(value):
    obs = Observation(id="Obs_01", confidence=value)
    assert check_v031_optional_fields(_wrap(obs), _idx(_wrap(obs))) == []


@pytest.mark.parametrize("value", ["-0.1", "1.5", "2", "high", "nan_value"])
def test_v031_observation_confidence_invalid(value):
    obs = Observation(id="Obs_01", confidence=value)
    errs = check_v031_optional_fields(_wrap(obs), _idx(_wrap(obs)))
    assert errs and errs[0].rule == RULE_V031_OPTIONAL_FIELDS


# ── <Edge type="..." target="..."> ───────────────────────────────────


@pytest.mark.parametrize("edge_type", sorted(V031_EDGE_TYPES))
def test_v031_edge_type_closed_set_valid(edge_type):
    edge = Edge(edge_type=edge_type, target="src/foo.py")
    assert check_v031_optional_fields(_wrap(edge), _idx(_wrap(edge))) == []


def test_v031_edge_type_outside_closed_set_rejected():
    edge = Edge(edge_type="invokes", target="src/foo.py")  # not in closed set
    errs = check_v031_optional_fields(_wrap(edge), _idx(_wrap(edge)))
    assert errs and errs[0].rule == RULE_V031_OPTIONAL_FIELDS


def test_v031_edge_target_not_resolved_as_atom_id():
    """Edge.target is a file path, NOT a Scholia atom id; rule 2 must skip."""
    edge = Edge(edge_type="depends_on", target="src/never/declared.py")
    trace = _wrap(
        Goal(id="G_01", scope="trace", priority="required"),
        edge,
        Finding(id="F_01", for_goal="G_01", status="met"),
    )
    result = validate(trace)
    # If the reference-completeness rule incorrectly tried to resolve
    # ``src/never/declared.py``, this trace would fail. It must pass.
    assert result.ok, result.summary()


# ── <Effect kind="..."> ──────────────────────────────────────────────


@pytest.mark.parametrize("effect_kind", sorted(V031_EFFECT_KINDS))
def test_v031_effect_kind_closed_set_valid(effect_kind):
    eff = Effect(effect_kind=effect_kind)
    assert check_v031_optional_fields(_wrap(eff), _idx(_wrap(eff))) == []


def test_v031_effect_kind_outside_closed_set_rejected():
    eff = Effect(effect_kind="prints")  # not in closed set
    errs = check_v031_optional_fields(_wrap(eff), _idx(_wrap(eff)))
    assert errs and errs[0].rule == RULE_V031_OPTIONAL_FIELDS


# ── <Ref type="..." target="..."> ────────────────────────────────────


@pytest.mark.parametrize("ref_type", sorted(V031_REF_TYPES))
def test_v031_ref_type_closed_set_valid(ref_type):
    ref = Ref(ref_type=ref_type, target="tests/foo.py")
    assert check_v031_optional_fields(_wrap(ref), _idx(_wrap(ref))) == []


def test_v031_ref_type_outside_closed_set_rejected():
    ref = Ref(ref_type="approver", target="tests/foo.py")  # not closed set
    errs = check_v031_optional_fields(_wrap(ref), _idx(_wrap(ref)))
    assert errs and errs[0].rule == RULE_V031_OPTIONAL_FIELDS


# ── <Meta criticality="..."> ─────────────────────────────────────────


@pytest.mark.parametrize("criticality", sorted(V031_META_CRITICALITIES))
def test_v031_meta_criticality_closed_set_valid(criticality):
    meta = Meta(criticality=criticality)
    assert check_v031_optional_fields(_wrap(meta), _idx(_wrap(meta))) == []


def test_v031_meta_criticality_outside_closed_set_rejected():
    meta = Meta(criticality="dangerous")  # not closed set
    errs = check_v031_optional_fields(_wrap(meta), _idx(_wrap(meta)))
    assert errs and errs[0].rule == RULE_V031_OPTIONAL_FIELDS


# ── Parser-side rejection mirror ─────────────────────────────────────


def test_parser_rejects_invalid_observation_confidence():
    bad = (
        '<Step id="S"><Observation id="O" confidence="1.5">x</Observation></Step>'
    )
    with pytest.raises(ScholiaParseError, match="confidence"):
        parse(bad)


def test_parser_rejects_invalid_observation_location():
    bad = (
        '<Step id="S"><Observation id="O" location="foo">x</Observation></Step>'
    )
    with pytest.raises(ScholiaParseError, match="location"):
        parse(bad)


def test_parser_rejects_unknown_edge_type():
    bad = (
        '<Step id="S">'
        '<Observation id="O"><Edge type="invokes" target="x"/></Observation>'
        "</Step>"
    )
    with pytest.raises(ScholiaParseError, match="Edge"):
        parse(bad)


def test_parser_rejects_unknown_effect_kind():
    bad = (
        '<Step id="S">'
        '<Observation id="O"><Effect kind="prints"/></Observation>'
        "</Step>"
    )
    with pytest.raises(ScholiaParseError, match="Effect"):
        parse(bad)


def test_parser_rejects_unknown_ref_type():
    bad = (
        '<Step id="S">'
        '<Observation id="O"><Ref type="approver" target="x"/></Observation>'
        "</Step>"
    )
    with pytest.raises(ScholiaParseError, match="Ref"):
        parse(bad)


def test_parser_rejects_unknown_meta_criticality():
    bad = '<Step id="S"><Meta criticality="dangerous"/></Step>'
    with pytest.raises(ScholiaParseError, match="Meta"):
        parse(bad)


# ── Parser-side acceptance (round-trip through validator) ────────────


def test_parser_accepts_v031_observation_attributes():
    text = (
        '<Step id="S" name="t">'
        '<Goal id="G_01" scope="trace" priority="required">go</Goal>'
        '<Observation id="O_01" location="src/foo.py:1:10" confidence="0.9">'
        "data"
        "</Observation>"
        '<Finding id="F_01" for_goal="G_01" status="met">done</Finding>'
        "</Step>"
    )
    trace = parse(text)
    assert validate(trace).ok
    obs = trace[0].atoms[1]
    assert isinstance(obs, Observation)
    assert obs.location == "src/foo.py:1:10"
    assert obs.confidence == "0.9"


def test_parser_accepts_v031_edge_effect_ref_meta_subelements():
    text = (
        '<Step id="S" name="t">'
        '<Meta criticality="kernel"/>'
        '<Goal id="G_01" scope="trace" priority="required">go</Goal>'
        '<Observation id="O_01" location="src/foo.py:1:10">'
        "  <Edge type=\"depends_on\" target=\"src/bar.py\"/>"
        '  <Effect kind="network"/>'
        '  <Ref type="test_owner" target="tests/foo.py"/>'
        "</Observation>"
        '<Finding id="F_01" for_goal="G_01" status="met">done</Finding>'
        "</Step>"
    )
    trace = parse(text)
    result = validate(trace)
    assert result.ok, result.summary()

    obs = trace[0].atoms[2]
    assert isinstance(obs, Observation)
    sub_kinds = {child.kind for child in obs.children}
    assert {"Edge", "Effect", "Ref"} <= sub_kinds


def test_effect_instance_kind_does_not_shadow_classvar():
    """Regression — wire ``kind="..."`` on <Effect> MUST route to
    ``effect_kind`` so the ClassVar discriminator stays intact.
    """
    text = (
        '<Step id="S">'
        '<Observation id="O"><Effect kind="pure"/></Observation>'
        "</Step>"
    )
    trace = parse(text)
    obs = trace[0].atoms[0]
    effect = obs.children[0]
    assert isinstance(effect, Effect)
    assert effect.kind == "Effect"  # ClassVar discriminator preserved
    assert effect.effect_kind == "pure"  # wire ``kind`` landed on field


# ── Strict closed-set rejection of unknown wire attributes ───────────


def test_parser_rejects_unknown_wire_attribute_on_observation():
    """v0.3.1 PRD acceptance criterion #3 — ``<Observation foo="bar">``
    must be invalid because ``foo`` is not in the closed set for
    Observation. Pre-fix the parser silently dropped unknown attrs.
    """
    text = '<Step id="S"><Observation foo="bar"/></Step>'
    with pytest.raises(ScholiaParseError, match="unknown attribute"):
        parse(text)


def test_parser_rejects_unknown_wire_attribute_on_finding():
    text = '<Step id="S"><Finding bogus="value"/></Step>'
    with pytest.raises(ScholiaParseError, match="unknown attribute"):
        parse(text)


def test_parser_rejects_typo_in_v031_attribute():
    """Typos in v0.3.1 attribute names (``locaton`` for ``location``)
    must surface as the strict-closed-set error rather than being
    silently dropped — that was the original miss.
    """
    text = '<Step id="S"><Observation locaton="path.py:1-10"/></Step>'
    with pytest.raises(ScholiaParseError, match="unknown attribute"):
        parse(text)


def test_parser_allows_known_attribute_on_known_kind():
    """Sanity — the strict check must not reject legitimate attrs."""
    text = '<Step id="S"><Observation confidence="0.9"/></Step>'
    parse(text)  # must not raise


def test_parser_open_namespace_storing_accepts_arbitrary_keys():
    """``<Storing>`` is in the open-namespace set; operator-defined
    keys MUST pass the closed-set check.
    """
    text = '<Step id="S"><Storing user_defined_key="x"/></Step>'
    parse(text)  # must not raise


def test_parser_open_namespace_print_accepts_arbitrary_keys():
    text = '<Step id="S"><Print arbitrary_attr="hello"/></Step>'
    parse(text)  # must not raise


def test_parser_universal_value_sidecar_allowed_everywhere():
    """``value`` is produced by paren-arg shorthand on any atom kind
    (``<Print("hi")/>`` → ``<Print value="hi"/>``); the closed-set
    check must permit it universally.
    """
    text = '<Step id="S"><Print("hi")/></Step>'
    parse(text)  # must not raise — paren-arg desugars to value=


def test_parser_rejects_unknown_attribute_after_v031_validation():
    """Ordering check — v0.3.1 specific errors (e.g. unknown edge_type)
    must keep firing with their precise messages before the generic
    closed-set sweep, so callers/tests that key on the specific text
    don't regress.
    """
    # Use a known v0.3.1 attr with an invalid value; we want the
    # precise v0.3.1 error, not the generic closed-set one.
    text = '<Step id="S"><Edge type="not_a_real_type" to="O"/></Step>'
    with pytest.raises(ScholiaParseError) as excinfo:
        parse(text)
    # Must NOT be the generic closed-set message — specific msg wins.
    assert "unknown attribute" not in str(excinfo.value)
