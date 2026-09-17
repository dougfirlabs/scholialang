# Contributing

Scholia language changes start in `scholialang-spec`. Update the spec
and fixture corpus first, then update this reference implementation and
its conformance tests.

Use Python 3.11 or newer. From the repository root:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
```

Before opening a PR, also run the shared spec-conformance checks. For a new
sibling spec checkout, use the same exact revision as CI:

```sh
git clone https://github.com/dougfirlabs/scholialang-spec.git ../scholialang-spec
ref="$(tr -d '[:space:]' < scholialang-spec-ref.txt)"
git -C ../scholialang-spec fetch --depth 1 origin "$ref"
git -C ../scholialang-spec checkout --detach "$ref"
python scripts/run_spec_conformance.py ../scholialang-spec
SCHOLIALANG_SPEC_DIR="$PWD/../scholialang-spec" \
  SCHOLIALANG_REQUIRE_FINGERPRINT_FIXTURES=1 python -m pytest
```

If you already have a spec checkout with work in progress, use a separate
checkout or worktree at the pinned revision and pass that path to both the
script and `SCHOLIALANG_SPEC_DIR`. Requiring fingerprint fixtures prevents a
missing corpus from silently skipping those integration checks.

The current package and validator release is **0.7.2**; the stable grammar
baseline is **v0.6.2**, with the approved additive fingerprint contract. Keep
historical grammar and registry-format versions distinct from package versions.
For a release, update `pyproject.toml`, `scholialang.__version__`,
`SCHOLIA_VALIDATOR_VERSION`, the release-version tests, README, and changelog
together. Coordinate the package version and dependency floor with
`scholialang-mcp`; publish the core package first.

Check release artifacts locally before publishing:

```sh
python -m pip install build twine
python -m build
python -m twine check dist/*
```
