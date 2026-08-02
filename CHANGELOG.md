# Changelog

## 0.7.1

**First synchronized suite release.** scholialang and scholialang-mcp advance
together to 0.7.1; **scholialang 0.7.0 is skipped intentionally** so the two
packages share one version line going forward. No behavior change for existing
traces — the release is additive.

- **Additive `fingerprint=` attribute** (contract merged in scholialang-spec,
  `docs/scholia/FINGERPRINT.md`). An optional `<algo>:<hex>` content hash on
  location-bearing atoms (`<Observation>` today) so a later consumer can
  mechanically re-verify a code claim against source. This ships the
  reference-implementation half; the operator contract-approval gate is now
  satisfied (spec + reference validator merged). Ignore-if-absent per the
  `canonical_id` precedent; a single additive `fingerprint_well_formed` rule
  (hard-fail, vacuous when absent).
- `SCHOLIA_VALIDATOR_VERSION` advanced to `0.7.1` to track the package version.
  (Reviewer note: the fingerprint attribute is itself an additive extension;
  the constant is bumped for package-consistency, not to signal a breaking
  spec change — flag if you prefer to decouple a spec-conformance version.)

- **`<Observation fingerprint=...>`** — optional; strictly additive. A
  fingerprint-less Observation parses, validates, and hashes byte-identically
  to pre-revision behavior.
- **`fingerprint_well_formed`** — a new hard-fail validator rule, vacuous when
  absent (§4). When present the value must match `^[a-z0-9]+:[0-9a-f]+$` and
  the atom must also carry a `location` (a fingerprint binds a span). The rule
  is purely structural — it does NOT recompute the digest against source;
  re-verification is a consumer-side operation (§5).
- **canonical_id independence** — `fingerprint` is excluded from the
  `canonical_id` hash (§8): it is the identity of the *code the atom points
  at*, not of the *atom*. Stripping it is lossless at the identity layer.
- **Shared fixtures** — the positive/negative corpus is consumed from
  `scholialang-spec/tests/fixtures/fingerprint/` (single copy, no fork) by
  both the pytest suite and `scripts/run_spec_conformance.py`.

## v0.6.2

The recursive Action-result closure release. Rule 4 (`action_recorded`) now
recognizes an explicitly linked result emitted later in the trace, including
across Step boundaries, without weakening provenance requirements.

- **Later linked Finding** — a later `Finding` records an `Action` when it
  `REFER`s the Action directly, or when it `REFER`s an `Observation`/`Evidence`
  that itself `REFER`s the Action.
- **Goal-closing Concluding** — a later `Concluding` records an `Action` when it
  directly `REFER`s the Action and carries `for_goal`.
- **Graph projection compatibility** — callers may optionally pass a duck-typed
  graph exposing `has_edge(...)`; a `records_result` edge targeting the Action
  records its result. Existing `validate(trace)` calls are unchanged.
- **Strict ordering** — nested and immediate sibling conclusions remain valid,
  but chronological order alone does not qualify a non-immediate result.
- **Versions** — the package version and `SCHOLIA_VALIDATOR_VERSION` both move
  to `0.6.2`.

## v0.6.1

The `<Concluding>` status release. A `<Concluding>` may now carry an
**optional** `status` attribute recording the terminal disposition of the
Goal it closes, aligning the reference parser/validator with the ratified
v0.6.1 spec contract.

- **`<Concluding status=...>`** — `status` is an optional enum
  (`met|unmet|partially_met`) on the `Concluding` dataclass and in
  `KIND_SPECIFIC_FIELDS['Concluding']`. The parser accepts it, the
  serializer round-trips it, and `compute_canonical_id` folds it into the
  content hash only when present. A status-less `<Concluding>` parses and
  validates exactly as before (v0.5/v0.6.0 back-compat).
- **Validator** — when `status` is present it must be one of
  `met|unmet|partially_met`; an out-of-enum value is a hard validation
  error (under the `v031_optional_fields` rule). The `goal_declared` rule
  now reads `Concluding.status`: a required Goal is closed by a status-less
  Concluding (back-compat) or one carrying an in-enum status.
- **Versions** — the package version (`pyproject` + `__version__`) and
  `SCHOLIA_VALIDATOR_VERSION` both move to `0.6.1`. The registry format
  version stays `0.6` (it tracks the on-disk format, not the patch).
- **Publish hygiene** — internal references were scrubbed from `src/`,
  `tests/`, and fixtures, and a CI leak guard
  (`tests/unit/scholia/test_public_hygiene.py`) now hard-fails on the
  forbidden token set across `src/`, `tests/`, and `scripts/`.
- **Registry DAG naming** — the registry's in-memory return type is now
  `VerificationDag` (a content-addressed DAG of verification relationships,
  not a linear chain), surfaced via `walk_dag` / `to_verification_dag` /
  `dag_to_dict` / `dag_from_dict` and backed by the
  `scholialang.verification_dag` shim. The default on-disk registry path
  becomes `~/.scholia/registry.verification_dag.json`. This settles the
  interim v0.6.0 DAG-shape naming before the v0.6.1 publish, so the
  registry's public surface debuts under the accurate `verification_dag`
  name rather than the inaccurate "chain" framing.

## v0.6.0

The content-addressable-IDs release. v0.6 makes the substrate's portability
claim operational: atoms address by a cross-implementation-stable content
hash, the registry persists them as a DAG, and the lazy prelude lets a later
session REFER prior atoms by hash instead of replaying their XML. Conforms to
the Scholia v0.6 golden-records compatibility manifest (2026-06-06). The
`canonical_id` hasher is **byte-identical** to the v0.6 reference
implementation — frozen golden vectors assert this in CI
(`tests/fixtures/canonical_id_golden.json`).

- **`canonical_id`** — every `Atom` gains a content-addressable
  `sha256:<12hex>` id, computed by `compute_canonical_id` over canonical
  JSON `{kind, content.strip(), attrs}` (`json.dumps` `sort_keys=True`,
  compact separators) with provenance (`timestamp`, `run_id`, `wall_clock`,
  `sequence`, `instance`) and base bookkeeping (`id`, `canonical_id`,
  `children`, `operators`) excluded. The parser stamps it at parse time; a
  mismatching claimed id is preserved in lazy mode for the validator to
  flag, and `CanonicalIdMismatch` is raised by strict callers. Emitted on
  parse, never required on read (v0.4/v0.5 traces parse unchanged).
- **`scholialang.registry`** — new DAG-backed, canonical_id-keyed store
  (`put`/`get`/`find_by_kind`/`ancestors`/`descendants`/`walk_chain`/
  `to_proof_chain`), on-disk `{"version": "0.6", "atoms", "edges"}` with
  `fcntl` locking; `REFER:`/`IMPLIES:` `sha256:` operators form
  premise→conclusion DAG edges. Backed by an in-repo self-contained
  DAG-shapes shim — **no external-orchestrator dependency** in the
  standalone package.
- **`scholialang.prelude`** — new canonical-prelude renderer. The three
  **core v0.6 modes** (`CORE_PRELUDE_MODES`) are `hash_only` (~30 c/atom),
  `hash_list` (~70-100 c/atom, the **default**), and `inline` (v0.5
  baseline) for cross-session compaction.
- **Validator** — adds the hard-fail `canonical_id_well_formed` rule
  (universal recompute-and-compare; flags tampered/stale ids) and the
  4-path `resolve_refer` resolver (local id → in-trace canonical_id →
  registry → none). `reference_complete` now resolves canonical_id-form
  targets. These ship alongside the 6 v0.5 Concluding-scoped rules as real
  `RULE_NAMES` entries, with a source-level audit in
  `tests/unit/scholia/test_validator_v06.py`.
- **Multi-track versioning** — the package version (`pyproject` +
  `__version__`) and `SCHOLIA_VALIDATOR_VERSION` are independent tracks;
  both read `0.6.0` for this release.
- **Back-compatible with v0.4/v0.5** — a trace carrying no `canonical_id`
  is vacuously well-formed; `REFER:local_id` still resolves; the existing
  rules are unchanged.

### Experimental (NOT v0.6 core)

- **Prelude recovery arms** — two additional render modes,
  `hash_semantic_preview` and `selective_inline_plus_hash_only`
  (`EXPERIMENTAL_PRELUDE_MODES`), post-date the 2026-06-06 manifest and ship
  as a **preview extension**. They are excluded from `CORE_PRELUDE_MODES`
  and are opt-in only via `build_canonical_prelude(..., allow_experimental=
  True)`. They are not part of the finalized v0.6 contract and may change.

## v0.5.0

- Adds the `Concluding` atom as the chain-level epistemic close.
- Makes `Finding.for_hyp` canonical while preserving `for_goal` as a
  v0.4 compatibility alias.
- Adds v0.5 Concluding validator rules for goal resolution, citations,
  criticality downgrades, duplicate active closes, action-modal warnings,
  and confidence ceilings.

## v0.4.0

- Initial standalone release of the language reference package.
- Includes the Scholia atom model, parser, validator, serializers,
  renderers, stable IDs, and v0.4 metadata helpers.
