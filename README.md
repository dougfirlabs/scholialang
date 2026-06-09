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

`scholialang` is the Python reference implementation for Scholia, a
structured reasoning notation for agent traces.

Scholia v0.6 makes agent reasoning portable, inspectable, and reusable
across sessions using content-addressed reasoning traces. The v0.6 language
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

## Current v0.6 Scope

`scholialang` owns the language runtime for the v0.6 scope: the 32-kind
closed vocabulary inherited from v0.5, optional `canonical_id` computation and
validation, canonical-id-aware reference resolution, the local DAG registry
primitive, and the three finalized lazy-prelude modes. MCP servers, editor
clients, host plugins, and public launch pages live in sibling repositories.

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

This package tracks Scholia language version `v0.6.0`.

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
