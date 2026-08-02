"""v0.6.x-proposed — fingerprint= attribute + ``fingerprint_well_formed`` rule.

Source-level audit for the additive ``fingerprint`` attribute on
location-bearing atoms (``docs/scholia/FINGERPRINT.md``). The attribute is a
``<algo>:<hex>`` content hash of the source span at ``location`` so a later
consumer can mechanically re-verify a code claim. This suite locks the
notation surface the reference validator owns:

* The attribute lands on ``<Observation>`` (the only location-bearing atom
  today), is parseable through the strict-closed-set posture, and round-trips
  through the serializer / single-atom XML.
* ``fingerprint_well_formed`` is a hard-fail rule that is **vacuous when
  absent** (the ignore-if-absent guarantee, §4), hard-fails a malformed value
  (§3.2), and hard-fails a fingerprint carried without a companion
  ``location`` (§3.3).
* The attribute is **strictly additive**: a fingerprint-less Observation
  validates byte-identically to pre-revision behavior, and ``fingerprint`` is
  excluded from the ``canonical_id`` hash (§8) so it is non-load-bearing —
  stripping it is lossless at the identity layer (§4.1).

The digest is NOT recomputed against source here — re-verification is a
consumer-side operation (§5), not a notation-validator rule (§3).
"""
from __future__ import annotations

from scholialang.atoms import (
    KIND_SPECIFIC_FIELDS,
    Observation,
    atom_to_xml,
    compute_canonical_id,
    is_valid_fingerprint,
)
from scholialang.parser import parse, parse_atom, ScholiaParseError
from scholialang.serializer import to_json, from_json
from scholialang.validator import (
    RULE_FINGERPRINT_WELL_FORMED,
    RULE_NAMES,
    validate,
)

import pytest


# ── Dataclass + catalog surface ──────────────────────────────────────


def test_observation_carries_fingerprint_field():
    obs = Observation(id="Obs_01", location="src/foo.py:8:10", fingerprint="sha256:8f4a9d2c1b3e")
    assert obs.fingerprint == "sha256:8f4a9d2c1b3e"


def test_fingerprint_defaults_to_none():
    assert Observation().fingerprint is None


def test_fingerprint_in_kind_specific_fields():
    assert "fingerprint" in KIND_SPECIFIC_FIELDS["Observation"]


def test_rule_names_include_fingerprint_well_formed():
    assert RULE_FINGERPRINT_WELL_FORMED in RULE_NAMES


# ── is_valid_fingerprint helper — <algo>:<hex> shape ─────────────────


@pytest.mark.parametrize(
    "value",
    ["sha256:8f4a9d2c1b3e", "sha256:00ff", "blake3:deadbeef", "md5:0"],
)
def test_well_formed_fingerprints_accepted(value):
    assert is_valid_fingerprint(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "sha256:NOTHEX",       # uppercase / non-hex after the colon
        "sha256:8f4a9d2c1b3e!",  # trailing non-hex
        "deadbeef",            # bare hash, no algo: prefix
        "sha256:",             # empty hex
        ":deadbeef",           # empty algo
        "SHA256:deadbeef",     # uppercase algo label
        "",                    # empty value
        None,                  # absent
    ],
)
def test_malformed_fingerprints_rejected(value):
    assert is_valid_fingerprint(value) is False


# ── Parser — strict-closed-set accepts fingerprint on Observation ────


def test_parser_accepts_fingerprint_on_observation():
    atom = parse_atom(
        '<Observation id="Obs_01" location="src/foo.py:8:10" '
        'fingerprint="sha256:8f4a9d2c1b3e">foo()</Observation>'
    )
    assert atom.fingerprint == "sha256:8f4a9d2c1b3e"


def test_parser_accepts_malformed_fingerprint_value():
    """The parser is not the well-formedness layer — it accepts the value
    verbatim (like ``canonical_id``); the validator rule flags the shape."""
    atom = parse_atom(
        '<Observation id="Obs_01" location="src/foo.py:8:10" '
        'fingerprint="sha256:NOTHEX!!">foo()</Observation>'
    )
    assert atom.fingerprint == "sha256:NOTHEX!!"


def test_fingerprint_still_rejected_on_non_location_atom():
    """``fingerprint`` follows ``location``; a kind without a location field
    (e.g. <Finding>) still trips the strict-closed-set parser."""
    with pytest.raises(ScholiaParseError):
        parse_atom('<Finding id="F_01" fingerprint="sha256:00ff">x</Finding>')


# ── fingerprint_well_formed rule ─────────────────────────────────────


def _errs(trace):
    return validate(trace).errors_by_rule[RULE_FINGERPRINT_WELL_FORMED]


def test_absent_fingerprint_is_vacuous():
    trace = parse(
        '<Step id="s1"><Observation id="Obs_01" location="src/foo.py:8:10">'
        "foo()</Observation></Step>"
    )
    assert _errs(trace) == []


def test_present_well_formed_fingerprint_passes():
    trace = parse(
        '<Step id="s1"><Observation id="Obs_01" location="src/foo.py:8:10" '
        'fingerprint="sha256:8f4a9d2c1b3e">foo()</Observation></Step>'
    )
    assert _errs(trace) == []


def test_malformed_fingerprint_hard_fails():
    trace = parse(
        '<Step id="s1"><Observation id="Obs_01" location="src/foo.py:8:10" '
        'fingerprint="sha256:NOTHEX!!">foo()</Observation></Step>'
    )
    errs = _errs(trace)
    assert len(errs) == 1
    assert errs[0].atom_id == "Obs_01"
    assert not validate(trace).ok


def test_fingerprint_without_location_hard_fails():
    trace = parse(
        '<Step id="s1"><Observation id="Obs_01" '
        'fingerprint="sha256:8f4a9d2c1b3e">foo()</Observation></Step>'
    )
    errs = _errs(trace)
    assert len(errs) == 1
    assert "location" in errs[0].message
    assert not validate(trace).ok


# ── Additive / non-load-bearing guarantees (§4, §4.1, §8) ────────────


def test_fingerprintless_observation_byte_identical_to_pre_change():
    """The exact pre-revision shape validates with zero fingerprint errors
    and the same canonical_id it always had."""
    plain = Observation(id="Obs_01", content="foo()", location="src/foo.py:8:10")
    trace = parse(
        '<Step id="s1"><Observation id="Obs_01" location="src/foo.py:8:10">'
        "foo()</Observation></Step>"
    )
    result = validate(trace)
    assert result.errors_by_rule[RULE_FINGERPRINT_WELL_FORMED] == []
    assert trace[0].atoms[0].canonical_id == compute_canonical_id(plain)


def test_fingerprint_excluded_from_canonical_id():
    """§8 — canonical_id is the identity of the atom, not of the code it
    points at; the two must not fold together."""
    plain = Observation(id="Obs_01", content="foo()", location="src/foo.py:8:10")
    fingerprinted = Observation(
        id="Obs_01",
        content="foo()",
        location="src/foo.py:8:10",
        fingerprint="sha256:8f4a9d2c1b3e",
    )
    assert compute_canonical_id(plain) == compute_canonical_id(fingerprinted)


def test_stripping_fingerprint_is_lossless_at_identity_layer():
    """§4.1 — dropping fingerprint yields an atom that addresses to the same
    canonical_id, so the attribute is non-load-bearing."""
    with_fp = parse(
        '<Step id="s1"><Observation id="Obs_01" location="src/foo.py:8:10" '
        'fingerprint="sha256:8f4a9d2c1b3e">foo()</Observation></Step>'
    )
    without_fp = parse(
        '<Step id="s1"><Observation id="Obs_01" location="src/foo.py:8:10">'
        "foo()</Observation></Step>"
    )
    assert with_fp[0].atoms[0].canonical_id == without_fp[0].atoms[0].canonical_id


# ── Round-trip through serializer + single-atom XML ──────────────────


def test_fingerprint_survives_json_roundtrip():
    trace = parse(
        '<Step id="s1"><Observation id="Obs_01" location="src/foo.py:8:10" '
        'fingerprint="sha256:8f4a9d2c1b3e">foo()</Observation></Step>'
    )
    restored = from_json(to_json(trace))
    assert restored[0].atoms[0].fingerprint == "sha256:8f4a9d2c1b3e"


def test_fingerprint_emitted_in_single_atom_xml():
    obs = Observation(
        id="Obs_01",
        content="foo()",
        location="src/foo.py:8:10",
        fingerprint="sha256:8f4a9d2c1b3e",
    )
    xml = atom_to_xml(obs)
    assert 'fingerprint="sha256:8f4a9d2c1b3e"' in xml
