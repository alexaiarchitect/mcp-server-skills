#!/usr/bin/env python3
"""Record or compare the tool signatures an Alexa+ add-on was deployed with.

Alexa+ re-reads a server's tools only when the add-on is redeployed
(`alexa-ai deploy`), and a certified add-on's behaviour is what was reviewed.
So a change to a tool's name, parameters, schema or description is something to
notice *before* it ships. This script hashes each tool's parameters, schema
source and description (read statically, like the review) into
`docs/alexa-tools.lock.json`, and compares the current code against it.

Lock exactly what Alexa+ sees: `--tools-from probe.json` (the `tools/list` a
deployed server returned, via `probe.py --json`), `--tools a,b`, or
`--profile alexa` (the static reading `lint_alexa.py` uses) scope the lock to
those tools; the lock records the scope it was taken with.

Without `--write` it only compares (`ALX080` when anything changed). `--write`
records the lock — run it right after a deploy, after the user confirmed;
`--dry-run` prints the document it would write.

    tools_lock.py <project> [--unit name] [--profile alexa] [--tools a,b | --tools-from probe.json]
                  [--exclude-tools a,b] [--write] [--dry-run] [--json]

Exit codes: 0 unchanged or written, 1 changed (compare mode), 2 nothing to read.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from mcp_server_skills.alexa_rules import (  # noqa: E402
    add_scope_arguments, compare_lock, lock_document, scope_from_args, signatures,
)
from mcp_server_skills.cli import add_dry_run, add_output, emit, fail, parser  # noqa: E402
from mcp_server_skills.inventory import build, select  # noqa: E402
from mcp_server_skills.report import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, GapReport, Option  # noqa: E402

LOCK = Path("docs") / "alexa-tools.lock.json"


def main(argv: list[str] | None = None) -> int:
    p = parser(__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--unit")
    p.add_argument("--write", action="store_true", help="record the current signatures")
    add_scope_arguments(p)
    add_dry_run(p)
    add_output(p)
    args = p.parse_args(argv)
    root = Path(args.project).expanduser()
    if not root.exists():
        return fail(f"{root} does not exist")
    inventory = build(root)
    units = select(inventory, args.unit)
    report = GapReport(subject=str(inventory.root), skill="mcp-alexa")
    if not units:
        report.add("DSC001", f"no MCP server under {root}", path=str(inventory.root))
        return emit(report, args, code=EXIT_USAGE)
    try:
        tools, scope = scope_from_args(args, [t for u in units for t in u.tools])
    except (OSError, ValueError) as exc:
        return fail(str(exc))
    lock_path = inventory.root / LOCK
    current = signatures(tools)
    report.discovered = {"lock": str(lock_path), "tools": sorted(current), "scope": scope}
    if args.write or args.dry_run:
        document = lock_document(tools, date=date.today().isoformat(),
                                 scope={k: scope[k] for k in ("profile", "selected_by")})
        if args.dry_run:
            report.discovered["would_write"] = str(lock_path)
            report.discovered["document"] = json.loads(document)
            return emit(report, args, code=EXIT_OK)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(document, encoding="utf-8")
        report.discovered["written"] = str(lock_path)
        return emit(report, args, code=EXIT_OK)
    if not lock_path.is_file():
        report.discovered["status"] = "no lock recorded yet"
        report.add_option(Option("1", "Record the lock now", cost="write", writes=[str(LOCK)],
                                 runs=["tools_lock.py <project> --write"]))
        return emit(report, args)
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return fail(f"{lock_path}: {exc}")
    changes = compare_lock(lock, current)
    report.discovered["status"] = "changed" if changes else "unchanged"
    report.discovered["changes"] = changes
    if changes:
        report.add("ALX080", "; ".join(changes[:8]), path=str(lock_path))
        report.add_option(Option("1", "Redeploy so Alexa+ sees the new tools", cost="deploy",
                                 runs=["alexa-ai deploy"]))
        report.add_option(Option("2", "Re-record the lock after the deploy", cost="write", writes=[str(LOCK)]))
        return emit(report, args, code=EXIT_FINDINGS)
    return emit(report, args)


if __name__ == "__main__":
    raise SystemExit(main())
