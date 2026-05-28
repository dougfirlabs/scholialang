"""Run scholialang parser/validator against scholialang-spec examples."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scholialang.parser import parse
from scholialang.validator import validate


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

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"validated {len(examples)} scholialang-spec examples")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec_dir", type=Path)
    args = parser.parse_args(argv)
    return run(args.spec_dir.resolve())


if __name__ == "__main__":
    raise SystemExit(main())

