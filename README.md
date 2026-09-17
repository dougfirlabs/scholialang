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

The current package release is **0.7.2**, synchronized with
[`scholialang-mcp`](https://github.com/dougfirlabs/scholialang-mcp).
It implements the stable **Scholia v0.6.2 language grammar**, plus the
approved additive `fingerprint=` contract.

> Package and grammar versions are separate: `scholialang.__version__` and
> `SCHOLIA_VALIDATOR_VERSION` both report `0.7.2`. The grammar and shared
> conformance baseline remain `v0.6.2`; references to that grammar do not
> indicate an outdated Python package.

## Current scope

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

Host-runtime concerns such as session trace persistence, enrichment,
adjudication, and proof-graph bridging live outside this package. MCP/LSP
servers and harness plugins live in `scholialang-mcp`.

The language retains the 32-kind closed vocabulary and 11 operators, with
optional content-addressed `canonical_id` hashes, canonical-id-aware reference
resolution, a local DAG registry, and three core lazy-prelude modes:
`hash_only`, `hash_list` (default), and `inline`. The recovery modes
`hash_semantic_preview` and `selective_inline_plus_hash_only` remain
experimental and require `allow_experimental=True`.

Recent releases also provide:

- Optional `Concluding.status` values: `met`, `unmet`, and `partially_met`.
- Action-result validation that accepts explicitly linked results in later
  Steps while rejecting unrelated or order-only results.
- Optional `Observation.fingerprint` values (`<algo>:<hex>`) paired with a
  `location`. Validation checks their structure; consumers recheck the digest
  against source. Fingerprints do not change an atom's `canonical_id`.
- The **0.7.2 constraint-validation fix**: article-bearing phrases such as
  “Never a bare null” no longer treat `a` as a forbidden verb, and forbidden
  actions match complete tokens rather than substrings of unrelated words.

See the [changelog](CHANGELOG.md) and
[0.7.2 release notes](https://github.com/dougfirlabs/scholialang/releases/tag/v0.7.2).

## Install

Requires **Python 3.11 or newer**.

Install or upgrade to the latest published release:

```sh
python -m pip install --upgrade scholialang
```

To reproduce this release, use `python -m pip install 'scholialang==0.7.2'`.

## Quick start

```python
from scholialang import __version__, parse, validate

trace = parse('''
<Step id="Step_0001">
  <Goal id="Goal_0001">Check the documented package version.</Goal>
  <Observation id="Observation_0001">The package release is 0.7.2.</Observation>
  <Concluding id="Concluding_0001" for_goal="Goal_0001" status="met">
    REFER:Observation_0001 The documented release matches the package.
  </Concluding>
</Step>
''')
result = validate(trace)
assert result.ok, result.errors
print(__version__, result.scholia_validator_version)  # 0.7.2 0.7.2
```

For local development and the pinned spec-conformance checks, see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Related Repositories

- [`scholialang-spec`](https://github.com/dougfirlabs/scholialang-spec) -
  language specification and fixture corpus
- [`scholialang-mcp`](https://github.com/dougfirlabs/scholialang-mcp) -
  MCP, LSP, and host plugin tooling

The exact specification commit used by CI is recorded in
[`scholialang-spec-ref.txt`](scholialang-spec-ref.txt). Both implementation
repositories pin the same approved fingerprint contract and constraint
regression corpus, and consume their shared fixtures.

## License

The `scholialang` reference implementation is dual-licensed under either
MIT or Apache-2.0, at your option. See `LICENSE`, `LICENSE-MIT`, and
`LICENSE-APACHE`.

The normative specification prose lives in `scholialang-spec` and is licensed
separately under CC-BY-4.0.

## Specification and background

- [Language specification](https://scholialang.org/spec)
- [Approved fingerprint contract](https://github.com/dougfirlabs/scholialang-spec/blob/9c530ed71d19b0c407503b367472a4f8e7b8e151/docs/scholia/FINGERPRINT.md)
- [Historical v0.6 language introduction](https://scholialang.org/whats-new-in-v0.6)
