# scholialang

`scholialang` is the Python reference implementation for Scholia, a
structured reasoning notation for agent traces.

It contains the language-level pieces only:

- atom dataclasses
- parser
- validator
- stable atom IDs
- metadata helpers
- JSON/YAML serializers
- Markdown/XML renderers

Host-runtime concerns such as trace persistence, enrichment,
adjudication, and proof-graph bridging live outside this package.

## Install

```sh
pip install scholialang
```

For local development:

```sh
pip install -e '.[dev]'
pytest
```

## Spec

The language contract and fixture corpus live in
[`scholialang-spec`](https://github.com/dougfirlabs/scholialang-spec).
This package tracks Scholia language version `v0.5.0`.
