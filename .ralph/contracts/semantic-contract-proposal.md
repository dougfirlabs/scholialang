# Proposed additive Map/Event/Task contract

Status: proposed candidate contract for review; no merge or publication implied. Package 0.7.3 and grammar 0.7.0 are distinct proposed axes. Preserve all valid legacy traces and EventRef. No runtime execution or authorization is introduced.

## 2. Common model and validation boundary

Use the existing pure dataclass style: subclasses of Atom, `kind: ClassVar[str]`, explicit fields, and no I/O or execution in constructors, parsing, validation, hashing, or serialization. Required semantic fields may default to None at the Python construction boundary, as existing dataclasses do; validation must reject incomplete instances. Parsers must reject malformed field shapes rather than silently discard them.

The common wire attributes for new kinds are `id` and optional `canonical_id`, plus the specific fields below. JSON/YAML retain the existing `kind`, `content`, `operators`, and `children` structural keys. `operators` must be a list of strings; no coercion from arbitrary objects. New kinds have **no nested child atoms** in this revision: reject nonempty children. This avoids claiming that child structure is covered by a canonical hash which historically excludes children. Relationships use explicit references instead.

Require a trace-local ID for each new kind. Its prefix must match its kind: `Map_`, `Event_`, or `Task_`, followed by one or more ASCII letters, digits, or underscores. Existing IDs such as Goal_01 retain their existing acceptance rules. An ID collision involving at least one new atom is an error anywhere in the trace, including against a Step or legacy atom ID. Do not retroactively change legacy-only duplicate handling in this slice.

Every named optional string field, when present, must be nonempty after checking whitespace; preserve its original bytes and case rather than silently normalize identity. Omitted and null optional fields are equivalent. Reject unknown fields on each new kind across XML, JSON, YAML, and dictionary input. Reject malformed Python-constructed new atoms in validate() using the same structural rules. Old parsing/serialization behavior is not globally tightened without an explicit regression justification.

Local reference fields contain an exact declared atom ID or canonical ID. Resolve against the complete trace, allowing forward references, and enforce the target kinds below. Opaque external references are nonempty strings: never interpret them as a local ID, dereference them, use them for execution, or treat them as proof of identity/authority. No new generic Edge enum values or legacy reference semantics are introduced.

## 3. Map: a typed mapping value, not a topology or arbitrary object bag

Map is a named-in-the-trace, homogeneous, finite mapping from nonempty string keys to one declared scalar/reference type. It is distinct from the existing inline MAP primitive and does not change primitive parsing.

| Field | Requirement | Contract |
| --- | --- | --- |
| `value_type` | Required | Exactly `string`, `integer`, `boolean`, or `atom_ref` |
| `entries` | Required | Object/mapping, possibly empty; unique, nonempty string keys |
| `content` | Optional body | Human explanation, not a second data payload |

Values must all match `value_type`. `string` permits strings including empty strings. `integer` requires a true integer (not bool), in the interoperable JSON exact-integer range `-(2^53-1)` through `2^53-1`. `boolean` requires bool exactly. `atom_ref` requires nonempty string references resolving to a declared atom of any kind other than Step; a Map must not refer to itself. Nested objects, arrays, nulls, floats, NaN, infinities, nonstring keys, and mixed types are rejected. Map does not imply evaluation, schema discovery, traversal, or network lookup.

XML represents entries as a JSON object in the escaped `entries` attribute. JSON/YAML represent entries as an actual mapping, never Python repr or a JSON-encoded string. XML output uses canonical JSON for this attribute: sorted string keys, compact separators, Unicode preserved before XML escaping. Reject duplicate keys when decoding the embedded JSON. JSON/YAML full-trace loaders must also detect duplicate mapping keys before they are silently overwritten. If a loader must reject duplicate keys for legacy documents too because duplicates have already destroyed information, document this narrowly as malformed-input rejection and prove valid legacy corpus parity.

Example:

```xml
<Map id="Map_inputs" value_type="string" entries="{&quot;format&quot;:&quot;xml&quot;,&quot;target&quot;:&quot;fixture&quot;}">Inputs to the declared task.</Map>
```

Map canonical identity includes value_type, entries, and content under the unchanged existing hash algorithm. Entry insertion order is not identity; key/value changes are. The four value types deliberately avoid speculative heterogeneous or recursively typed syntax. A later schema revision can extend this closed set explicitly.

## 4. Event: a recorded occurrence, not a delivered notification

| Field | Requirement | Contract |
| --- | --- | --- |
| `source` | Required | Opaque producer namespace; not authentication evidence |
| `occurrence_id` | Required | Opaque ID unique within source for this occurrence |
| `event_type` | Required | Nonempty classification token matching `[A-Za-z][A-Za-z0-9_.-]*`; producer-defined vocabulary, not a new atom kind |
| `timestamp` | Optional | RFC3339-shaped timestamp with explicit timezone; reject naive or impossible date/time values; exclude from canonical identity as existing timestamp provenance is excluded |
| `for_task` | Optional local ref | Task only |
| `for_action` | Optional local ref | Action only |
| `for_goal` | Optional local ref | Goal only |
| `effect_ref` | Optional local ref | Effect only; does not execute the effect |
| `map_ref` | Optional local ref | Map only |
| `external_ref` | Optional opaque string | External event/resource correlation, no dereference |
| `content` | Required body | Nonempty description of what was recorded |

The pair `(source, occurrence_id)` identifies an occurrence. Two Event atoms with the same pair in one trace are rejected, even if their bodies match; transport deduplication belongs upstream of semantic insertion. Distinct occurrence_id values produce distinct canonical IDs even for otherwise identical prose. Reusing a pair with contradictory content is therefore not silent last-write-wins. The canonical hash remains a structural content address, not a replacement for this occurrence key.

Existing EventRef remains the external-event reference kind with instance/run_id/sequence/for/wall_clock unchanged. EventRef may point to an Event using its existing local `for` relationship where legacy reference resolution already permits it; it never changes kind or gains a new automatic interpretation. Event is neither an MCP notification envelope nor the authoritative runtime event database.

Example:

```xml
<Event id="Event_reviewed" source="review-worker" occurrence_id="review-17" event_type="review.completed" for_task="Task_review" map_ref="Map_inputs">The review result was recorded.</Event>
```

## 5. Task: declarative work semantics, not a runtime task handle

| Field | Requirement | Contract |
| --- | --- | --- |
| `status` | Required | Exactly `open`, `satisfied`, `unsatisfied`, or `withdrawn` |
| `for_goal` | Optional local ref | Goal only |
| `input_map` | Optional local ref | Map only |
| `output_map` | Optional local ref | Map only |
| `action_ref` | Optional local ref | Action only |
| `evidence_ref` | Optional local ref | Observation, Evidence, Finding, or Concluding only |
| `runtime_ref` | Optional opaque string | Correlates a separately authorized runtime task, never creates or controls one |
| `content` | Required body | Nonempty description of the work obligation |

`open` means the recorded obligation has no semantic verdict; `satisfied` is an author's assertion that it was met; `unsatisfied` asserts it was not met; `withdrawn` records that the obligation was withdrawn. These are descriptive claims, not enforcement, authorization, acceptance of proof, or runtime execution states. A satisfied Task does **not** close a required Goal, substitute for a Finding/Concluding, excuse an Action without a recorded result, or declare a runtime task completed. Existing closure rules remain authoritative. Runtime states such as queued, working, input_required, cancelled, expired, and paused stay in the MCP task contract and are never inferred from this enum.

Require `evidence_ref` when status is satisfied or unsatisfied, so the verdict has an explicit reference; validation checks shape/resolution/target kind, not the truth of the evidence. No evidence reference is required for open or withdrawn. A status change creates a new immutable Task atom/local ID and new canonical identity rather than mutating an accepted historical atom in place. No new persistent task-entity key, transition machine, dependency graph, retry model, or scheduler is introduced in core.

Example:

```xml
<Task id="Task_review" status="open" input_map="Map_inputs" runtime_ref="opaque-task-handle">Review the fixture output.</Task>
```

This compact verdict model intentionally differs from MCP task status. Adapters must maintain explicit correlations; a one-to-one enum translation is not implied.

## 6. Canonical identity, round trips, and collisions

Keep `compute_canonical_id` byte-identical for legacy atoms: `sha256:` plus the first 12 lowercase hex digits of the existing canonical JSON hash. Keep stable local IDs as the independent `<Kind>_<8hex>` text-derived convenience format; do not rename canonical IDs to Map_/Event_/Task_. New kinds participate through their explicit dataclass fields and the existing kind discriminator. Do not make global changes to provenance exclusions or empty-value handling.

For new kinds, XML/JSON/YAML decoding validates field shapes before hashing. Compute a missing canonical_id after all fields are populated. Preserve an explicit claimed ID long enough for existing canonical-ID validation to report mismatches; do not silently replace a tampered claim. Serializers must retain canonical_id for new atoms and preserve it across all supported formats. Use a shared pure normalization helper that returns a validated copy with a missing canonical_id computed; deserializers return this normalized value and serializers encode this normalized copy. Serialization must never mutate the caller's object. An explicit mismatched canonical_id remains a validation failure, not an opportunity to repair the claim silently.

Collision handling must be explicit: when a new atom's canonical_id equals an existing atom's ID but the full canonical structural payload differs, report a canonical collision and do not overwrite or merge the records. Identical payloads may share canonical identity across distinct local references, except Event occurrence-pair duplicate rules still apply. Test a forced truncated-hash collision using a test seam; do not claim the 48-bit prefix makes collisions impossible. Scope any registry collision hardening to preventing contradictory overwrites, with existing registry tests preserved.

Round-trip acceptance means equal semantic field values, operators, IDs, canonical IDs, and children (empty for these new kinds), plus stable canonical JSON on repeated encode/decode. Do not promise identical original whitespace, YAML quoting, or XML attribute order. Existing legacy golden canonical identities must remain byte-identical.

## 7. Versions and unsupported consumers

Proposed package/validator release metadata is 0.7.3, matching current parity rules across pyproject, `__version__`, and `SCHOLIA_VALIDATOR_VERSION`. No tags, uploads, or release are authorized.

Proposed grammar revision is **0.7.0**, distinct from package 0.7.3 and the separately pinned MCP protocol. The reason is the closed atom catalog grows from 32 to 35; claiming this remains the unchanged 0.6.2 grammar is misleading. Preserve the historical 0.6.2 spec and frozen corpus; add a normative 0.7 document/catalog projection and migration note, and make consistency tests version-aware rather than editing historical expectations to 35 blindly.

New consumers accept existing legacy traces unchanged. Provide an explicit grammar-profile validation entry point that rejects new kinds under a selected legacy 0.6.2 profile and rejects an unknown future profile with a structured unsupported-version diagnostic. The normal 0.7.3 parser can default to current supported grammar for unversioned local input; callers crossing a negotiated boundary must pass/check the profile explicitly.

An already-released 0.7.2 consumer cannot be retrofitted by this change: its unknown-kind parse failure is the observed fallback. Adapters must negotiate the advertised kind/grammar contract first and surface unsupported capability/version rather than down-convert Map to Storing, Event to EventRef, or Task to Action. Test the actual installed old artifact and report its real exception separately from the adapter's structured unsupported diagnostic.

Public `__all__`, `_ATOM_CLASSES`, ATOM_KINDS, KNOWN_KINDS, KIND_SPECIFIC_FIELDS, schema/index/reference, and installed artifacts must agree on the 35-kind current catalog. Keep a separately named immutable legacy catalog/profile if needed. Export the new classes and only the deliberate public contract constants/helpers; no runtime transport classes enter core.

## 8. Positive and negative fixture matrix

Create shared self-describing fixtures in the spec, with exact stable IDs, expected parser/validator outcome and rule code, and consumption by core source/wheel/sdist and downstream MCP artifacts. Every row below is required; record actual parametrized node IDs and counts after implementation, with zero required skips.

| Family | Required positive cases | Required negative/adversarial cases |
| --- | --- | --- |
| Catalog | All three public exports; 35 current/32 legacy kinds; MAP and EventRef unchanged | Unknown kind; unknown per-kind field in XML/JSON/YAML/dict; new kind in explicit legacy profile |
| Map types | Empty map for each of 4 types; populated string/integer/boolean/ref maps; integer bounds; Unicode/escaping; key-order permutation | Missing entries/type; invalid enum; nonstring/empty key; duplicate keys; mixed types; bool-as-integer; out-of-range integer; float/null/list/object values; dangling/self ref |
| Event identity | Same prose/different occurrence IDs; same occurrence ID/different source; optional links absent/present; valid timezone timestamp | Missing source/occurrence/type/content; invalid type token; same occurrence pair duplicate or contradictory; naive/impossible timestamp |
| Task declaration | All four statuses; open without runtime handle; terminal verdict with valid evidence; each optional reference | Missing status/content; runtime status substituted for semantic status; satisfied/unsatisfied without evidence; wrong evidence kind |
| Relation legality | Each declared field resolves to each permitted target kind; forward and canonical-ID references | Every declared field dangling; every field wrong-kind target; opaque runtime/external refs incorrectly treated as local (must remain accepted opaque strings) |
| Local IDs | Kind-matching IDs; text-derived IDs; existing legacy IDs unchanged | Missing new ID; wrong prefix; illegal characters; duplicate between new/new, new/legacy, new/Step |
| Canonical IDs | Legacy goldens unchanged; new field changes change ID; Map insertion order does not; Event timestamp does not | Claimed mismatch; malformed canonical ID; forced same digest/different payload collision; contradictory registry overwrite |
| Serialization | XML→JSON→YAML→XML semantic equality; repeated canonical JSON stable; all IDs and typed values retained | New children nonempty; string encoded where mapping required; arbitrary object coercion; duplicate-key loss; canonical-ID loss |
| No side effects | Constructor/parse/validate/roundtrip under subprocess/network/filesystem-write denial; runtime_ref stays opaque | Task parsing attempts execution or network; satisfied Task alone used to close Goal; Task used instead of required Action result |
| Compatibility | All old source fixtures, 13 action, 6 constraint, 6 fingerprint, frozen goldens; genuine old artifact accepts old fixtures | Old artifact encounters new kinds and fails explicitly; adapter surfaces unsupported profile, never silent rewrite |
| Packaging | Clean source, wheel, and sdist installs each report same versions/kinds and pass exact shared corpus | Import origin outside installed environment; stale spec pin; missing corpus; required skip; generated reference drift |

## 9. Implementation/test plan and evidence

Core files: atoms.py, __init__.py, parser.py, serializer.py, validator.py, registry.py only where collision protection requires it, version metadata, spec pin, and dedicated semantic contract tests. Keep stable_ids.py algorithm unchanged unless tests reveal only catalog-aware validation is necessary.

Spec files: new normative grammar/migration document, version-aware catalog/reference generation, shared conformance fixture suite registered in the compatibility manifest, and consistency/hygiene tests. Source-derived generation must explicitly select the candidate core path; existing sibling-import discovery can silently use stale shared core. Assert imported `scholialang.__file__` in proof receipts. Do not insert private paths or coordination terms into public documentation/tests.

Required baseline command families (substitute exact isolated paths):

```text
PYTHONPATH=src python -m pytest tests -q
python scripts/run_spec_conformance.py <accepted-spec-export>
SCHOLIALANG_SPEC_DIR=<accepted-spec-export> SCHOLIALANG_REQUIRE_FINGERPRINT_FIXTURES=1 python -m pytest tests/integration/scholia/test_fingerprint_fixtures.py tests/unit/scholia/test_fingerprint.py -q
python -m build
python -m pytest tests -q                         # spec suite, pinned core source
python scripts/atoms_to_spec.py --scholialang-src <candidate-core>/src --check <current-normative-spec>
python scripts/notation_reference_gen.py --check reference/notation-reference.md
```

Build wheel and sdist in isolation, install each in a separate environment, and run the shared corpus outside source roots. Run the old 0.7.2 artifact in its own environment. Bind evidence to both full candidate SHAs, exact spec pin, artifact SHA256 values, executed commands/exit codes, import origins, required scenario counts, and independent review. A joint spec/core candidate can be tested before either is merged; acceptance must record that this is a paired candidate receipt, not a previously accepted producer receipt.
