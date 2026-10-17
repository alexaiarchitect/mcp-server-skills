#!/usr/bin/env python3
"""Review an MCP server's source against a pinned protocol revision, without running it.

TypeScript and JavaScript are read with a comment- and string-aware scanner,
Python with `ast`; nothing is imported, built or executed, so the review works
on a project that does not compile — which is when a migration needs it.

The `MCP0xx` band, by decade:

    MCP00x  SDK: major behind the target, mixed majors, ext-apps / zod / Node mismatches
    MCP01x  era: sessions, handshake-only transport, no server/discover, modern-only, custom routing
    MCP02x  Mcp-Method / Mcp-Name validation, x-mcp-header
    MCP03x  resultType, ttlMs / cacheScope, public caches on authenticated servers
    MCP04x  deprecated (Roots, Sampling, Logging) and removed methods, SSE resumability
    MCP05x  error codes: -32002, draft numbering, the reserved range
    MCP06x  tools: inputSchema, raw shapes, order, per-caller lists, names, duplicates, descriptions
    MCP07x  server-initiated requests that need MRTR, unsolicited list_changed
    MCP08x  transport hygiene: stdout in stdio servers, 0.0.0.0, HTTP+SSE
    MCP09x  extensions: 2025-11-25 experimental tasks, MCP Apps resources

`--target 2025-11-25` reviews against the handshake era instead: modern-only
rules are skipped. `--baseline previous.json` adds which findings are new and
which were resolved since that report — the "migrate the delta" step of the
upgrade loop.

Report only. It never edits.

    lint_server.py <project> [--target 2026-07-28] [--unit name] [--baseline report.json]
                   [--json] [--strict]

Exit codes: 0 no errors, 1 errors (or warnings under --strict), 2 nothing to review.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from mcp_server_skills import KNOWN_REVISIONS, SPEC_TARGET  # noqa: E402
from mcp_server_skills.cli import add_output, emit, fail, parser  # noqa: E402
from mcp_server_skills.inventory import build, select  # noqa: E402
from mcp_server_skills.report import EXIT_USAGE, GapReport, Option, diff_findings, load_findings  # noqa: E402
from mcp_server_skills.review_rules import review, unit_label  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = parser(__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--target", default=SPEC_TARGET, help=f"protocol revision to review against (default {SPEC_TARGET})")
    p.add_argument("--unit", help="only this server (package name or path suffix)")
    p.add_argument("--baseline", help="a previous --json report; adds new / resolved findings")
    add_output(p)
    args = p.parse_args(argv)

    root = Path(args.project).expanduser()
    if not root.exists():
        return fail(f"{root} does not exist")
    if args.target not in KNOWN_REVISIONS and not __import__("re").fullmatch(r"\d{4}-\d{2}-\d{2}", args.target):
        return fail(f"--target must be a revision date such as {SPEC_TARGET}")
    inventory = build(root)
    units = select(inventory, args.unit)
    report = GapReport(subject=str(inventory.root), skill="mcp-review")
    if not units:
        report.add("DSC001", f"no MCP server under {root}", path=str(inventory.root))
        return emit(report, args, code=EXIT_USAGE)

    unknown_target = args.target not in KNOWN_REVISIONS
    target = SPEC_TARGET if unknown_target or args.target > SPEC_TARGET else args.target
    summary = []
    for u in units:
        review(u, report, target=target)
        summary.append({
            "unit": unit_label(u, inventory.root),
            "sdk": f"{u.sdk.get('package')} {u.sdk.get('resolved') or u.sdk.get('declared') or '?'}",
            "era": u.era,
            "transports": ", ".join(u.transports) or "none",
            "tools": len(u.tools),
            "hosting": ", ".join(u.hosting[:2]) or "unknown",
        })
    report.discovered = {"target": args.target, "rules_for": target, "units": summary}
    if unknown_target or args.target != target:
        report.discovered["note"] = (f"{args.target} is newer than the revisions these rules know; reviewed "
                                     f"against {target}. Read the changelog for what else changed.")

    if args.baseline:
        try:
            before = load_findings(args.baseline)
        except (OSError, ValueError, KeyError) as exc:
            return fail(f"cannot read baseline {args.baseline}: {exc}")
        report.discovered["delta"] = diff_findings(before, report.findings, relative_to=str(inventory.root))

    ids = set(report.ids())
    migrate = bool(ids & {"MCP001", "MCP011", "MCP012", "MCP010", "MCP050", "MCP061", "MCP067", "MCP070"})
    report.add_option(Option("1", "Plan the migration (dual-version)", skill="/mcp-server:mcp-migrate",
                             recommended=migrate, cost="free", runs=["plan_migration.py --json"],
                             detail="a plan first; edits only after you confirm, with a diff"))
    report.add_option(Option("2", "Verify a running endpoint", skill="/mcp-server:mcp-verify", cost="probe",
                             recommended=not migrate, runs=["probe.py <url> --legacy"]))
    report.add_option(Option("3", "Review authorization", skill="/mcp-server:mcp-auth", cost="free",
                             runs=["lint_auth.py"]))
    report.add_option(Option("4", "Gate CI on this review", skill="/mcp-server:mcp-ci", cost="write",
                             writes=[".github/workflows/mcp-conformance.yml"]))
    return emit(report, args)


if __name__ == "__main__":
    raise SystemExit(main())
