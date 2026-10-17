#!/usr/bin/env python3
"""Review an MCP server as an OAuth 2.1 resource server, from its source.

Reads the server and the workspace packages it depends on (auth code usually
lives next door) and checks the MCP authorization profile of 2026-07-28:

    AUT00x  is there auth at all; Protected Resource Metadata (RFC 9728): route,
            `resource` + `authorization_servers`, path-inserted location
    AUT01x  401 challenges with `resource_metadata`; methods served anonymously;
            403 `insufficient_scope` for step-up
    AUT02x  token validation: audience / resource binding (RFC 8707), token
            passthrough, decode-without-verify, tokens in the query string
    AUT03x  client registration: Dynamic Client Registration (Deprecated) vs
            Client ID Metadata Documents
    AUT04x  self-hosted authorization server metadata: PKCE S256, `iss` (RFC 9207)
    AUT05x  per-tool scopes (`securitySchemes`), `offline_access`

Stdio servers are skipped: the spec says they take credentials from the
environment instead. For the live documents use `check_prm.py`.

Report only. It never edits.

    lint_auth.py <project> [--unit name] [--json] [--strict]

Exit codes: 0 no errors, 1 errors (or warnings under --strict), 2 nothing to review.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from mcp_server_skills.auth_rules import review_static  # noqa: E402
from mcp_server_skills.cli import add_output, emit, fail, parser  # noqa: E402
from mcp_server_skills.inventory import build, select  # noqa: E402
from mcp_server_skills.report import EXIT_USAGE, GapReport, Option  # noqa: E402
from mcp_server_skills.review_rules import unit_label  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = parser(__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--unit", help="only this server (package name or path suffix)")
    add_output(p)
    args = p.parse_args(argv)
    root = Path(args.project).expanduser()
    if not root.exists():
        return fail(f"{root} does not exist")
    inventory = build(root)
    units = select(inventory, args.unit)
    report = GapReport(subject=str(inventory.root), skill="mcp-auth")
    if not units:
        report.add("DSC001", f"no MCP server under {root}", path=str(inventory.root))
        return emit(report, args, code=EXIT_USAGE)
    report.discovered = {"units": []}
    for u in units:
        review_static(u, report)
        report.discovered["units"].append({"unit": unit_label(u, inventory.root),
                                           "transports": ", ".join(u.transports) or "none", **u.auth})
    report.add_option(Option("1", "Check the live metadata documents", skill="/mcp-server:mcp-auth",
                             cost="network", runs=["check_prm.py <mcp-url>"], recommended=True,
                             detail="fetches PRM and authorization server metadata; sends no token"))
    report.add_option(Option("2", "Probe 401 behaviour end to end", skill="/mcp-server:mcp-verify",
                             cost="probe", runs=["probe.py <url>"]))
    report.add_option(Option("3", "Apply the fixes after review", cost="write",
                             detail="smallest change per finding, then re-run this review"))
    return emit(report, args)


if __name__ == "__main__":
    raise SystemExit(main())
