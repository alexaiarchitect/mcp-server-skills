#!/usr/bin/env python3
"""Inventory the MCP server(s) in a project without building or running anything.

Answers the questions every later step depends on, from files alone:

- language, SDK package, declared and resolved version (pnpm `catalog:` and
  `workspace:*` included), and which major that is;
- transports (Streamable HTTP, stdio, HTTP+SSE) and the protocol *era* the code
  actually implements: `handshake` (answers only `initialize`), `stateless`
  (2026-07-28 only), `dual`, or `unknown`;
- auth: Protected Resource Metadata, `WWW-Authenticate`, token verification,
  audience checks, authorization server type, DCR, per-tool scopes;
- tools, resources and prompts with their schemas; MCP Apps and tasks usage;
- hosting hints (Lambda handler, Express, Hono, FastAPI, Terraform, SAM, ...),
  CI workflows, and any Alexa+ `addon.json`.

Workspace packages the server depends on are read for auth and hosting signals
but are not counted as servers.

    discover.py <project> [--unit name] [--json] [--strict]

Exit codes: 0 found, 1 errors (an unparseable file), 2 no MCP server found.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from mcp_server_skills import SPEC_TARGET  # noqa: E402
from mcp_server_skills.cli import add_output, emit, fail, parser  # noqa: E402
from mcp_server_skills.inventory import build, select  # noqa: E402
from mcp_server_skills.report import EXIT_USAGE, GapReport, Option  # noqa: E402

ERA_MEANING = {
    "handshake": "answers `initialize` only: 2025-era clients work, 2026-07-28 clients do not",
    "stateless": "serves 2026-07-28 only: 2025-era clients (Alexa+ included) are turned away",
    "dual": "serves 2026-07-28 per request and still answers 2025-era `initialize`",
    "unknown": "no serving entry point recognised",
}


def main(argv: list[str] | None = None) -> int:
    p = parser(__doc__)
    p.add_argument("project", nargs="?", default=".", help="project root, monorepo root or server package")
    p.add_argument("--unit", help="only this server (package name or path suffix)")
    add_output(p)
    args = p.parse_args(argv)

    root = Path(args.project).expanduser()
    if not root.exists():
        return fail(f"{root} does not exist")
    inventory = build(root)
    units = select(inventory, args.unit)
    report = GapReport(subject=str(inventory.root), skill="mcp-discover")
    report.discovered = {
        "root": str(inventory.root),
        "servers": len(units),
        "units": [u.to_dict(inventory.root) for u in units],
        "ci": inventory.ci(),
        "addon_json": [str(p.relative_to(inventory.root)) for p in inventory.layout.addon_files],
        "node_version": inventory.layout.node_version,
    }
    if not units:
        report.add("DSC001", f"no package under {root} imports or declares an MCP SDK"
                   + (f" matching --unit {args.unit}" if args.unit else ""), path=str(inventory.root))
        return emit(report, args, code=EXIT_USAGE)
    if len(units) > 1:
        report.add("DSC002", f"{len(units)} servers: " + ", ".join(u.to_dict(inventory.root)["path"] for u in units),
                   path=str(inventory.root))
    for u in units:
        manifest = str(u.path / u.unit.manifest)
        if u.sdk.get("package") and u.sdk.get("major") is None:
            report.add("DSC003", f"{u.sdk.get('package')} declared as {u.sdk.get('declared')!r}", path=manifest)
        if "fastmcp-thirdparty" in u.py_apis:
            report.add("DSC004", "imports the third-party `fastmcp` package", path=manifest)
        for f in u.files:
            if f.error:
                report.add("DSC010", f.error, path=str(f.path))
        u_dict = report.discovered["units"][units.index(u)]
        u_dict["era_meaning"] = ERA_MEANING.get(u.era, "")

    ci = report.discovered["ci"]
    if not ci["workflows"]:
        report.add_gap("GAP-CI", "no CI workflow", "nothing re-checks the server when the code or the spec moves",
                       "`/mcp-server:mcp-ci` generates a review + probe workflow")
    elif not ci["runs_mcp_review"]:
        report.add_gap("GAP-CI-REVIEW", "CI does not run the MCP review",
                       "a regression to a handshake-only transport would merge unnoticed",
                       "`/mcp-server:mcp-ci` adds a step that gates on lint_server.py's exit code")
    if any(not u.unit.test_sources for u in units):
        report.add_gap("GAP-TESTS", "no tests next to the server", "a migration has nothing to prove it kept "
                       "behaviour", "add a tools/list + one tools/call test before migrating")

    eras = {u.era for u in units}
    report.add_option(Option("1", f"Review against {SPEC_TARGET}", skill="/mcp-server:mcp-review",
                             recommended="handshake" in eras or "unknown" in eras, cost="free",
                             runs=["lint_server.py"], detail="static; nothing is written"))
    report.add_option(Option("2", "Probe a deployed endpoint", skill="/mcp-server:mcp-verify", cost="probe",
                             recommended=eras <= {"dual", "stateless"},
                             runs=["probe.py <url>"], detail="sends requests to your server, with your token"))
    report.add_option(Option("3", "Review authorization", skill="/mcp-server:mcp-auth", cost="free",
                             runs=["lint_auth.py"]))
    if inventory.layout.addon_files or any("lambda" in " ".join(u.hosting) for u in units):
        report.add_option(Option("4", "Alexa+ add-on readiness", skill="/mcp-server:mcp-alexa", cost="free",
                                 runs=["lint_alexa.py", "validate_addon.py"]))
    return emit(report, args)


if __name__ == "__main__":
    raise SystemExit(main())
