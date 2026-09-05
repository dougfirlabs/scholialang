<p align="center">
  <img src="assets/scholialang-banner.png" alt="Scholialang" width="100%" />
</p>

<p align="center">
  <a href="https://scholialang.org">Website</a> ·
  <a href="https://github.com/dougfirlabs/scholialang-spec">Spec</a> ·
  <a href="https://github.com/dougfirlabs/scholialang-mcp">MCP</a> ·
  <strong>Python</strong> ·
  <a href="https://github.com/dougfirlabs">Doug Fir Labs</a>
</p>

# scholialang

Scholia helps agentic systems preserve reasoning state, use tools without
quality loss, and reduce context cost across long-horizon work. `scholialang`
is the Python reference implementation of the language: the parser, validator,
and core primitives that make Scholia traces portable, inspectable, and
reusable across sessions.

Scholia v0.6 builds on content-addressed reasoning traces. The v0.6 language
keeps the v0.5 closed vocabulary and adds the content-addressed substrate:
optional `canonical_id` hashes, a canonical-id-keyed DAG registry, and the
three core lazy-prelude modes `hash_only`, `hash_list`, and `inline`.

It contains the language-level pieces only:

- atom dataclasses
- parser
- validator
- canonical_id hashing
- DAG registry primitives
- lazy prelude rendering
- stable atom IDs
- metadata helpers
- JSON/YAML serializers
- Markdown/XML renderers

Host-runtime concerns such as trace persistence, enrichment,
adjudication, and proof-graph bridging live outside this package.

## Current Scope

`scholialang` owns the language runtime: the closed atom vocabulary,
optional `canonical_id` computation and validation, canonical-id-aware
reference resolution, the local DAG registry primitive, and the three
finalized lazy-prelude modes. MCP servers, editor clients, host plugins,
and public launch pages live in sibling repositories.

The 0.7.3 candidate implements the PROPOSED additive Map/Event/Task
semantic contract (grammar `0.7.0`, a separate axis from the package
version): the closed catalog grows from 32 to 35 kinds, every valid
legacy trace keeps its meaning, and `validate(..., profile="0.6.2")`
rejects the new kinds with a structured unsupported-version diagnostic
instead of silently rewriting them. The frozen 32-kind projection stays
available as `LEGACY_ATOM_KINDS`. Parsing or validating a `Task` never
executes work; `runtime_ref` / `external_ref` are opaque correlators,
never dereferenced and never authority. See
`docs/scholia/SCHOLIA_v0.7_SPEC.md` and
`docs/scholia/v06.2-to-v07-migration.md` in `scholialang-spec` for the
normative contract and migration notes.

## Install

```sh
pip install scholialang
```

For local development:

```sh
pip install -e '.[dev]'
pytest
```

## Related Repositories

- [`scholialang-spec`](https://github.com/dougfirlabs/scholialang-spec) -
  language specification and fixture corpus
- [`scholialang-mcp`](https://github.com/dougfirlabs/scholialang-mcp) -
  MCP, LSP, and host plugin tooling

This package tracks Scholia grammar `0.6.2` for released behavior; the
`0.7.3` candidate additionally implements the proposed grammar `0.7.0`
(Map/Event/Task) pending ratification. No `0.7.3` release or tag exists
yet.

## License

The `scholialang` reference implementation is dual-licensed under either
MIT or Apache-2.0, at your option. See `LICENSE`, `LICENSE-MIT`, and
`LICENSE-APACHE`.

The normative specification prose lives in `scholialang-spec` and is licensed
separately under CC-BY-4.0.

Useful launch links:

- Spec: https://scholialang.org/spec
- What's new in v0.6: https://scholialang.org/whats-new-in-v0.6
- Eval summary: https://scholialang.org/eval-summary
