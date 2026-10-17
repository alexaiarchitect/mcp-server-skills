#!/usr/bin/env python3
"""Discover an MCP server project, summarise every review band, and say which skill comes next.

One pass, read only. It builds the same inventory as `mcp-discover`, runs the
protocol review (`MCP`), the auth review (`AUT`) and — when the project has an
`addon.json` or the request is about Alexa+ — the Alexa+ overlay (`ALX`), plus
the CI check, and reports counts per band rather than every finding. Then it
ranks the next step:

1. no server found -> say so, nothing else;
2. errors in the protocol review -> `/mcp-server:mcp-migrate` (plan first);
3. errors in auth -> `/mcp-server:mcp-auth`;
4. an Alexa+ add-on with errors -> `/mcp-server:mcp-alexa`;
5. clean code -> `/mcp-server:mcp-verify` against the deployed endpoint;
6. no CI gate -> `/mcp-server:mcp-ci`.

`--intent alexa|auth|ci|upgrade|verify|review|migrate` biases the
recommendation toward what the user asked for without hiding the rest.

    route.py <project> [--intent name] [--target 2026-07-28] [--json]

The closing `_Summary:` line and the JSON `summary` add up the band table, so
they agree with the body; the band table itself is the per-band breakdown.

Exit codes: 0 routed, 2 no MCP server found.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from mcp_server_skills import SPEC_TARGET  # noqa: E402
from mcp_server_skills.alexa_rules import review_project  # noqa: E402
from mcp_server_skills.auth_rules import review_static  # noqa: E402
from mcp_server_skills.cli import add_output, emit, fail, parser  # noqa: E402
from mcp_server_skills.inventory import build  # noqa: E402
from mcp_server_skills.report import EXIT_OK, EXIT_USAGE, GapReport, Option  # noqa: E402
from mcp_server_skills.review_rules import review, unit_label  # noqa: E402

INTENTS = ("review", "migrate", "verify", "auth", "alexa", "ci", "upgrade", "discover")


def band_counts(report: GapReport) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter] = {}
    for f in report.findings:
        band = "".join(ch for ch in f.id if ch.isalpha())
        counts.setdefault(band, Counter())[f.severity] += 1
    return {band: {"errors": c["error"], "warnings": c["warn"], "notes": c["info"]} for band, c in sorted(counts.items())}


def main(argv: list[str] | None = None) -> int:
    p = parser(__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--intent", choices=INTENTS)
    p.add_argument("--target", default=SPEC_TARGET)
    add_output(p, strict=False)
    args = p.parse_args(argv)
    root = Path(args.project).expanduser()
    if not root.exists():
        return fail(f"{root} does not exist")
    inventory = build(root)
    out = GapReport(subject=str(inventory.root), skill="mcp-server")
    if not inventory.units:
        out.add("DSC001", f"no package under {root} imports or declares an MCP SDK", path=str(inventory.root))
        out.add_option(Option("1", "Point me at the server's directory", cost="free", recommended=True))
        return emit(out, args, code=EXIT_USAGE)

    scratch = GapReport(subject=str(inventory.root), skill="scratch")
    alexa = bool(inventory.layout.addon_files) or args.intent == "alexa"
    units = []
    for u in inventory.units:
        review(u, scratch, target=args.target)
        review_static(u, scratch)
        if alexa:
            review_project(u, scratch)
        units.append({"unit": unit_label(u, inventory.root), "language": u.unit.language,
                      "sdk": f"{u.sdk.get('package')} {u.sdk.get('resolved') or u.sdk.get('declared') or '?'}",
                      "era": u.era, "transports": ", ".join(u.transports) or "none", "tools": len(u.tools),
                      "hosting": ", ".join(u.hosting[:2]) or "unknown",
                      "auth": ", ".join(u.auth.get("authorization_server", []))})
    ci = inventory.ci()
    bands = band_counts(scratch)
    out.discovered = {"target": args.target, "units": units, "findings_by_band": bands, "ci": ci,
                      "addon_json": [str(a.relative_to(inventory.root)) for a in inventory.layout.addon_files]}
    # The closing summary counts what the band table shows (F01), not only the
    # router's own DSC notes.
    out.rollup = {"errors": sum(b["errors"] for b in bands.values()),
                  "warnings": sum(b["warnings"] for b in bands.values()),
                  "infos": sum(b["notes"] for b in bands.values())}
    if len(inventory.units) > 1:
        out.add("DSC002", f"{len(inventory.units)} servers; skills take --unit", path=str(inventory.root))

    errors = lambda band: bands.get(band, {}).get("errors", 0)  # noqa: E731
    candidates = [
        ("migrate", errors("MCP") > 0, "Plan the migration to dual-version", "/mcp-server:mcp-migrate", "free",
         f"{errors('MCP')} protocol error(s); a plan first, edits only after you confirm"),
        ("auth", errors("AUT") > 0, "Fix authorization", "/mcp-server:mcp-auth", "free",
         f"{errors('AUT')} auth error(s)"),
        ("alexa", alexa and (errors("ALX") > 0 or args.intent == "alexa"), "Alexa+ add-on readiness",
         "/mcp-server:mcp-alexa", "free", "manifest, voice-shaped tools, 500 ms budget, account linking"),
        ("verify", True, "Probe the deployed endpoint", "/mcp-server:mcp-verify", "probe",
         "both eras, headers, cache hints, 401, p50/p95"),
        ("ci", not ci["runs_mcp_review"], "Gate CI on review + probe", "/mcp-server:mcp-ci", "write",
         "writes .github/workflows/mcp-conformance.yml after you confirm"),
        ("upgrade", True, "Check whether the spec moved", "/mcp-server:mcp-upgrade", "network",
         "versioning page + SDK registries; writes a delta file only if asked"),
        ("review", True, "Full protocol review", "/mcp-server:mcp-review", "free", "every MCP finding with its fix"),
    ]
    chosen = None
    if args.intent:
        chosen = next((c for c in candidates if c[0] == args.intent and c[1]), None) or \
            next((c for c in candidates if c[0] == args.intent), None)
    if chosen is None:
        chosen = next(c for c in candidates if c[1])
    key = 1
    for name, applicable, label, skill, cost, detail in candidates:
        if not applicable and name != chosen[0]:
            continue
        out.add_option(Option(str(key), label, skill=skill, cost=cost, detail=detail,
                              recommended=name == chosen[0]))
        key += 1
    return emit(out, args, code=EXIT_OK)


if __name__ == "__main__":
    raise SystemExit(main())
