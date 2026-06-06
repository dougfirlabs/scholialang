# Changelog

## v0.6.0

- Mirrors the OpenTalon in-tree `scholialang` package for the v0.6
  content-addressable atom migration.
- Adds canonical atom IDs plus compact prior-atom prelude rendering for
  `REFER:sha256:<id>` workflows.
- Adds a canonical-ID registry surface for lazy reference lookup.

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
