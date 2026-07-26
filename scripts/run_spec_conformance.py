"""Run scholialang against scholialang-spec examples and rule fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scholialang.parser import parse
from scholialang.validator import validate


@dataclass(frozen=True)
class _FixtureGraph:
    edges: tuple[dict[str, str], ...]

    def has_edge(
        self,
        *,
        edge_type: str,
        source_id: str | None = None,
        target_id: str | None = None,
    ) -> bool:
        return any(
            edge.get("relation") == edge_type
            and (source_id is None or edge.get("source_id") == source_id)
            and (target_id is None or edge.get("target_id") == target_id)
            for edge in self.edges
        )


def _run_rule_manifest(path: Path) -> tuple[int, list[str]]:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return 0, [f"{path}: raised {exc!r}"]

    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list):
        return 0, [f"{path}: top-level 'cases' must be a list"]

    failures: list[str] = []
    checked = 0
    for case in cases:
        checked += 1
        if not isinstance(case, dict):
            failures.append(f"{path}: case #{checked} must be an object")
            continue
        case_id = str(case.get("id") or f"case-{checked}")
        expects = case.get("expects")
        if not isinstance(expects, dict):
            failures.append(f"{path}:{case_id}: missing expects object")
            continue
        rule = str(expects.get("rule") or "")
        expected_outcome = str(expects.get("outcome") or "")
        expected_count = expects.get("error_count")
        try:
            trace = parse(str(case.get("trace") or ""))
            raw_edges = case.get("graph_edges") or []
            if not isinstance(raw_edges, list) or not all(
                isinstance(edge, dict) for edge in raw_edges
            ):
                raise TypeError("graph_edges must be a list of objects")
            graph = _FixtureGraph(
                tuple(
                    {
                        "source_id": str(edge.get("source_id") or ""),
                        "target_id": str(edge.get("target_id") or ""),
                        "relation": str(edge.get("relation") or ""),
                    }
                    for edge in raw_edges
                )
            )
            result = validate(trace, graph=graph)
        except Exception as exc:  # pragma: no cover - surfaced as CLI output.
            failures.append(f"{path}:{case_id}: raised {exc!r}")
            continue

        if rule not in result.errors_by_rule:
            failures.append(f"{path}:{case_id}: unknown rule {rule!r}")
            continue
        rule_errors = result.errors_by_rule[rule]
        actual_outcome = "pass" if not rule_errors else "fail"
        if expected_outcome not in {"pass", "fail"}:
            failures.append(
                f"{path}:{case_id}: invalid expected outcome {expected_outcome!r}"
            )
        elif actual_outcome != expected_outcome:
            failures.append(
                f"{path}:{case_id}: expected {rule}={expected_outcome}, "
                f"got {actual_outcome}: {rule_errors}"
            )
        if not isinstance(expected_count, int):
            failures.append(
                f"{path}:{case_id}: expects.error_count must be an integer"
            )
        elif len(rule_errors) != expected_count:
            failures.append(
                f"{path}:{case_id}: expected {expected_count} {rule} errors, "
                f"got {len(rule_errors)}: {rule_errors}"
            )
        expected_atom_ids = expects.get("atom_ids")
        if expected_atom_ids is not None:
            actual_atom_ids = [error.atom_id for error in rule_errors]
            if actual_atom_ids != expected_atom_ids:
                failures.append(
                    f"{path}:{case_id}: expected atom_ids={expected_atom_ids!r}, "
                    f"got {actual_atom_ids!r}"
                )
    return checked, failures


def run(spec_dir: Path) -> int:
    examples = sorted((spec_dir / "examples").glob("**/*.xml"))
    if not examples:
        print(f"no XML examples found under {spec_dir / 'examples'}", file=sys.stderr)
        return 1

    failures: list[str] = []
    for path in examples:
        try:
            trace = parse(path.read_text(encoding="utf-8"))
            result = validate(trace)
        except Exception as exc:  # pragma: no cover - surfaced as CLI output.
            failures.append(f"{path}: raised {exc!r}")
            continue
        if not result.ok:
            failures.append(f"{path}: {result.errors}")

    fixture_count = 0
    manifests = sorted((spec_dir / "conformance").glob("**/*.json"))
    for manifest in manifests:
        checked, manifest_failures = _run_rule_manifest(manifest)
        fixture_count += checked
        failures.extend(manifest_failures)

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(
        f"validated {len(examples)} scholialang-spec examples "
        f"and {fixture_count} rule fixtures"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec_dir", type=Path)
    args = parser.parse_args(argv)
    return run(args.spec_dir.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
