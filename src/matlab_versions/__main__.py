"""Command line: ``matlab-versions R2024a 9.14 v51 v914``, ``lmstat -a | matlab-versions``."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import List, Optional

from . import Release, __version__, data, lookup, parse_lmstat, releases

_KIND = {"name": "release", "matlab": "MATLAB version", "runtime": "Runtime", "license": "licence version"}


def _describe(rel: Release) -> str:
    def cell(value, key):
        if value is None:
            return "-"
        return f"{value}*" if rel.evidence.get(key) == "extrapolated" else str(value)

    runtime = cell(rel.runtime, "runtime")
    if rel.runtime_folder:
        runtime += f" ({rel.runtime_folder})"
    license = cell(f"v{rel.license}" if rel.license is not None else None, "license")
    return f"{rel.name}\tmatlab {cell(rel.matlab, 'matlab')}\truntime {runtime}\tlicense {license}"


def main(argv: Optional[List[str]] = None) -> int:
    try:
        return _main(argv)
    except BrokenPipeError:
        # the reader stopped early (`| head`, `| cmp`): not an error worth a traceback
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 1


def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="matlab-versions",
        description="Translate between MATLAB release names (R2024a), MATLAB versions (24.1), "
        "MATLAB Runtime versions and folders (9.14, v914) and FlexLM licence versions (lmstat '(v51)'). "
        "With no arguments, reads 'lmutil lmstat -a' output from stdin and lists each checkout's release. "
        "Values marked * are extrapolated.",
    )
    parser.add_argument("terms", nargs="*", metavar="TERM", help="e.g. R2024a, 24.1, 9.14, v914, v51, 51")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--table", action="store_true", help="print the bundled table")
    group.add_argument("--json", action="store_true", help="print the bundled table as JSON, with sources")
    parser.add_argument("--summary", action="store_true", help="with stdin: count checkouts per feature and release")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    if args.json:
        json.dump(data(), sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0
    if args.table:
        for rel in releases():
            print(_describe(rel))
        return 0
    if args.terms:
        status = 0
        for term in args.terms:
            matches = lookup(term)
            if not matches:
                print(f"matlab-versions: nothing matches {term!r}", file=sys.stderr)
                status = 2
            # "9.14" reads as both MATLAB and Runtime version of R2023a: one line, both kinds
            kinds_by_release = {}
            for kind, rel in matches:
                kinds_by_release.setdefault(rel, []).append(_KIND[kind])
            for rel, kinds in kinds_by_release.items():
                print(f"{term} ({', '.join(kinds)})\t{_describe(rel)}")
        return status

    if sys.stdin.isatty():
        parser.print_usage(sys.stderr)
        return 2
    checkouts = list(parse_lmstat(sys.stdin))
    if args.summary:
        counts = Counter((c.feature or "?", c.release.name if c.release else f"v{c.version}") for c in checkouts)
        for (feature, name), n in sorted(counts.items()):
            print(f"{feature}\t{name}\t{n}")
    else:
        for c in checkouts:
            name = c.release.name if c.release else "?"
            print(f"{c.feature or '?'}\t{c.user}\t{c.host}\tv{c.version}\t{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
