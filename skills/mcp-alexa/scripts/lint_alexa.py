#!/usr/bin/env python3
"""Alexa+ add-on readiness of an MCP server: the overlay on top of the protocol and auth reviews.

Reads the server (never runs it) and, optionally, a saved probe report, and
adds what Alexa+ documents beyond plain MCP:

    ALX03x  latency: p95 from `probe.py --json` against the 500 ms round-trip budget;
            Lambda cold starts
    ALX04x  tools as voice: screen references, long descriptions, lists that can
            exceed 5 options, operation-shaped names, MCP App tools with no voice path
    ALX05x  account linking: WWW-Authenticate on 401 (Alexa+ lists it as unsupported,
            the MCP spec wants it — reported as a conflict to confirm), client_credentials,
            DCR / CIMD / OIDC reliance, methods served without a token
    ALX06x  protocol: a modern-only endpoint (Alexa+ speaks 2025-11-25), no Streamable HTTP
    ALX08x  tool signatures changed since `docs/alexa-tools.lock.json` (see tools_lock.py)

The manifest itself is checked with `validate_addon.py`; this script runs the
same checks when it finds an `addon.json` (pass `--no-addon` to skip).

Scope the review to what Alexa+ will actually list. A server that registers
different tools per deployment (an `ALEXA_PROFILE` switch, say) is read with
`--profile alexa`: tools inside `if (alexa)`, after `if (alexa) { ... return }`
(left out), in a `register*Alexa*` function or under an `alexa/` path are told
apart statically, and a `WWW-Authenticate` that only one branch sends is
reported as a conditional note. `--tools-from probe.json` (the `tools/list` a
live server returned, via `probe.py --json`) or `--tools a,b` is exact and wins
over the static reading; `--exclude-tools` drops names. The add-on manifest's
tool references and the lock comparison use the same scoped list.

Report only. It never edits.

    lint_alexa.py <project> [--unit name] [--probe-report probe.json] [--budget-ms 500]
                  [--profile alexa] [--tools a,b | --tools-from probe.json] [--exclude-tools a,b]
                  [--endpoint https://.../mcp] [--no-addon] [--json] [--strict]

Exit codes: 0 no errors, 1 errors (or warnings under --strict), 2 nothing to review.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from mcp_server_skills import ALEXA_LATENCY_BUDGET_MS  # noqa: E402
from mcp_server_skills.addon import load, validate  # noqa: E402
from mcp_server_skills.alexa_rules import (  # noqa: E402
    add_scope_arguments, compare_lock, find_addon, review_project, scope_from_args, signatures,
)
from mcp_server_skills.cli import add_output, emit, fail, parser  # noqa: E402
from mcp_server_skills.inventory import build, select  # noqa: E402
from mcp_server_skills.report import EXIT_USAGE, GapReport, Option  # noqa: E402
from mcp_server_skills.review_rules import unit_label  # noqa: E402

LOCK = Path("docs") / "alexa-tools.lock.json"


def main(argv: list[str] | None = None) -> int:
    p = parser(__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--unit")
    p.add_argument("--probe-report", help="JSON written by probe.py --json")
    p.add_argument("--budget-ms", type=float, default=ALEXA_LATENCY_BUDGET_MS)
    p.add_argument("--endpoint", help="the server's canonical MCP URI")
    p.add_argument("--no-addon", action="store_true", help="skip the addon.json checks")
    add_scope_arguments(p)
    add_output(p)
    args = p.parse_args(argv)
    root = Path(args.project).expanduser()
    if not root.exists():
        return fail(f"{root} does not exist")
    probe = None
    if args.probe_report:
        try:
            probe = json.loads(Path(args.probe_report).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return fail(f"cannot read {args.probe_report}: {exc}")
    inventory = build(root)
    units = select(inventory, args.unit)
    report = GapReport(subject=str(inventory.root), skill="mcp-alexa")
    if not units:
        report.add("DSC001", f"no MCP server under {root}", path=str(inventory.root))
        return emit(report, args, code=EXIT_USAGE)
    found = []
    scoped_names: list[str] = []
    for u in units:
        try:
            tools, scope = scope_from_args(args, u.tools)
        except (OSError, ValueError) as exc:
            return fail(str(exc))
        scoped_names += [t.name for t in tools]
        review_project(u, report, probe=probe, budget_ms=int(args.budget_ms), tools=tools, profile=args.profile)
        entry = {"unit": unit_label(u, inventory.root), "era": u.era, "transports": ", ".join(u.transports),
                 "tools": len(tools), "tools_registered": len(u.tools), "hosting": ", ".join(u.hosting[:2]),
                 "scope": scope}
        lock_path = inventory.root / LOCK
        if lock_path.is_file():
            try:
                changes = compare_lock(json.loads(lock_path.read_text(encoding="utf-8")), signatures(tools))
            except ValueError:
                changes = ["lock file is not valid JSON"]
            if changes:
                report.add("ALX080", "; ".join(changes[:6]), path=str(lock_path))
            entry["tools_lock"] = "changed" if changes else "unchanged"
        else:
            entry["tools_lock"] = "none recorded"
        found.append(entry)
    addon_path = None if args.no_addon else find_addon(inventory.root, units[0].path)
    addon_summary = None
    if not args.no_addon:
        if addon_path is None:
            report.add("ALX001", "no addon.json in the project", path=str(inventory.root))
        else:
            doc, error = load(addon_path)
            if doc is None:
                report.add("ALX002", error or "unreadable", path=str(addon_path))
            else:
                names = tuple(scoped_names)
                addon_summary = validate(doc, report, str(addon_path), tool_names=names)
    report.discovered = {"units": found, "addon": str(addon_path) if addon_path else None,
                         "addon_summary": addon_summary, "budget_ms": args.budget_ms,
                         "probe_report": args.probe_report}
    report.add_option(Option("1", "Measure latency against the 500 ms budget", skill="/mcp-server:mcp-verify",
                             cost="probe", recommended=probe is None,
                             runs=["probe.py <url> --profile alexa --json > probe.json"]))
    report.add_option(Option("2", "Reshape tool descriptions for voice", cost="write",
                             detail="intent-first, at most 5 options, no screen references"))
    report.add_option(Option("3", "Record the tool-signature lock", cost="write", writes=[str(LOCK)],
                             runs=["tools_lock.py <project> --write"
                                   + (f" --profile {args.profile}" if args.profile else "")
                                   + (f" --tools-from {args.tools_from}" if args.tools_from else "")]))
    report.add_option(Option("4", "Deploy and test in the web simulator", cost="deploy",
                             runs=["alexa-ai deploy"]))
    return emit(report, args)


if __name__ == "__main__":
    raise SystemExit(main())
