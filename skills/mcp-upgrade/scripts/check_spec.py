#!/usr/bin/env python3
"""Is the pinned MCP revision still current? Compare it with the live versioning page and write the delta.

The first step of the upgrade loop — refresh, delta, re-review, migrate the
delta, verify. It reads the "current protocol version" sentence from
https://modelcontextprotocol.io/specification/versioning (or a saved copy), and
optionally the newest releases of the TypeScript and Python SDKs from npm and
PyPI, and compares them with:

- the pinned revision: `--pinned`, else the project's `.mcp-spec-pin` file,
  else the revision this plugin's rules target;
- the SDK versions this plugin was last checked against.

    UPG001  a newer revision is current: re-review with --target <new>
    UPG002  the versioning page could not be read (exit 3, nothing assumed)
    UPG003  an SDK has a release newer than the plugin's checked version
    UPG004  the pinned revision is not a published revision

With `--write-delta DIR` it writes `DIR/delta-<date>.md`: the change, the
changelog link, and the exact commands for the rest of the loop. `--dry-run`
prints that file instead of writing it.

    check_spec.py [project] [--pinned 2026-07-28] [--page-file versioning.md] [--sdk]
                  [--sdk-file versions.json] [--write-delta DIR] [--dry-run] [--json]

Exit codes: 0 up to date, 1 a newer revision is current, 2 usage, 3 inconclusive.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from mcp_server_skills import KNOWN_REVISIONS, LATEST_VERSIONS, SPEC_TARGET, SPEC_VERSIONING_URL  # noqa: E402
from mcp_server_skills.cli import add_dry_run, add_output, emit, fail, parser  # noqa: E402
from mcp_server_skills.report import EXIT_FINDINGS, EXIT_INCONCLUSIVE, GapReport, Option  # noqa: E402
from mcp_server_skills.specpage import (  # noqa: E402
    current_revision, delta_markdown, fetch_latest_versions, fetch_versioning, newer_versions,
)

PIN_FILE = ".mcp-spec-pin"


def main(argv: list[str] | None = None) -> int:
    p = parser(__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--pinned", help=f"the revision you target (default: {PIN_FILE}, else {SPEC_TARGET})")
    p.add_argument("--page-file", help="a saved copy of the versioning page (offline)")
    p.add_argument("--url", default=SPEC_VERSIONING_URL)
    p.add_argument("--sdk", action="store_true", help="also check npm and PyPI for newer SDK releases")
    p.add_argument("--sdk-file", help="a JSON object {package: version} instead of the registries (offline)")
    p.add_argument("--write-delta", metavar="DIR", help="write DIR/delta-<date>.md")
    p.add_argument("--date", default=date.today().isoformat(), help=argparse_hidden())
    add_dry_run(p)
    add_output(p)
    args = p.parse_args(argv)

    project = Path(args.project).expanduser()
    pinned = args.pinned
    pin_source = "--pinned"
    if not pinned and (project / PIN_FILE).is_file():
        pinned = (project / PIN_FILE).read_text(encoding="utf-8").strip()
        pin_source = str(project / PIN_FILE)
    if not pinned:
        pinned, pin_source = SPEC_TARGET, "plugin default"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", pinned):
        return fail(f"pinned revision {pinned!r} is not a YYYY-MM-DD date")

    report = GapReport(subject=str(project), skill="mcp-upgrade")
    if pinned not in KNOWN_REVISIONS:
        report.add("UPG004", f"{pinned} (from {pin_source}) is not one of {', '.join(KNOWN_REVISIONS)}",
                   path=pin_source)

    if args.page_file:
        try:
            page, error, source = Path(args.page_file).read_text(encoding="utf-8"), None, args.page_file
        except OSError as exc:
            return fail(str(exc))
    else:
        page, error = fetch_versioning(args.url)
        source = args.url
    live = current_revision(page) if page else None
    inconclusive = live is None
    if live is None:
        report.add("UPG002", error or "no revision found on the page", path=source)
    elif live > pinned:
        report.add("UPG001", f"{live} is current; you pin {pinned}", path=source)

    observed: dict[str, str] = {}
    sdk_errors: list[str] = []
    if args.sdk_file:
        try:
            observed = json.loads(Path(args.sdk_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return fail(f"cannot read {args.sdk_file}: {exc}")
    elif args.sdk:
        observed, sdk_errors = fetch_latest_versions()
    newer = newer_versions(observed)
    for pkg, (old, new) in sorted(newer.items()):
        report.add("UPG003", f"{pkg} {new} (checked against {old})", path="registry", locator=pkg)

    delta = delta_markdown(pinned=pinned, live=live, newer=newer, source=source, today=args.date)
    report.discovered = {
        "pinned": pinned, "pin_source": pin_source, "live": live, "source": source,
        "sdk_checked_against": LATEST_VERSIONS, "sdk_observed": observed or "not checked",
        "sdk_errors": sdk_errors,
    }
    if args.write_delta:
        out = Path(args.write_delta) / f"delta-{args.date}.md"
        if args.dry_run:
            report.discovered["would_write"] = str(out)
            report.discovered["delta"] = delta
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(delta, encoding="utf-8")
            report.discovered["written"] = str(out)
    target = live if live and live > pinned else pinned
    report.add_option(Option("1", f"Re-review against {target} with the last report as baseline",
                             skill="/mcp-server:mcp-review", cost="free", recommended=bool(live and live > pinned),
                             runs=[f"lint_server.py <project> --target {target} --baseline review.json"]))
    report.add_option(Option("2", "Plan the migration of the delta", skill="/mcp-server:mcp-migrate", cost="free",
                             runs=[f"plan_migration.py <project> --target {target}"]))
    report.add_option(Option("3", "Verify the deployed endpoint", skill="/mcp-server:mcp-verify", cost="probe",
                             runs=["probe.py <url> --legacy"]))
    code = None
    if not inconclusive and live and live > pinned:
        code = EXIT_FINDINGS
    elif inconclusive:
        code = EXIT_INCONCLUSIVE
    return emit(report, args, code=code)


def argparse_hidden() -> str:
    import argparse

    return argparse.SUPPRESS


if __name__ == "__main__":
    raise SystemExit(main())
