"""Argument and output conventions every script shares.

`--json` prints the gap report as JSON for a skill to branch on; the default
markdown is for the user. `--strict` turns warnings into a failing exit code,
which is what a CI gate wants. Scripts that write anything also take
`--dry-run`, which prints the write plan and touches nothing.
"""

from __future__ import annotations

import argparse
import sys

from .report import GapReport, exit_code_for


def parser(doc: str | None) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)


def add_output(p: argparse.ArgumentParser, *, strict: bool = True) -> None:
    p.add_argument("--format", choices=("json", "md"), default="md", help="output format (default md)")
    p.add_argument("--json", action="store_const", const="json", dest="format",
                   help="print the report as JSON (same as --format json)")
    if strict:
        p.add_argument("--strict", action="store_true", help="exit 1 on warnings too (for CI gates)")


def add_dry_run(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dry-run", action="store_true",
                   help="print what would be written and exit without touching any file")


def emit(report: GapReport, args: argparse.Namespace, *, inconclusive: bool = False,
         code: int | None = None) -> int:
    print(report.render(getattr(args, "format", "md")))
    if code is not None:
        return code
    return exit_code_for(report, strict=getattr(args, "strict", False), inconclusive=inconclusive)


def fail(message: str, code: int = 2) -> int:
    print(f"error: {message}", file=sys.stderr)
    return code
