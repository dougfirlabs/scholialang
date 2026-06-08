# Changelog

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
  premise→conclusion DAG edges. Backed by the in-repo self-contained
  `_proofdag` shim — **no `opentalon` dependency** in the standalone package.
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
