#!/usr/bin/env python3
"""Turn review findings into an ordered, dual-version migration plan. Reads only.

Runs the `MCP0xx` review, then maps what it found to steps for the server's
language:

    TypeScript  TS00 official codemod (command)   TS01 dependencies (auto)
                TS02 imports (auto)               TS03 per-request transport -> createMcpHandler
                TS04 raw shapes / variadic tools  TS05 sessions and event store
                TS06 -32002 -> -32602 (auto)      TS07 cache hints
                TS08 server-initiated -> inputRequired   TS09 custom router in front of the SDK
    Python      PY01 dependency (auto)            PY02 FastMCP -> MCPServer imports (auto)
                PY03 transport settings move      PY04 get_context() -> injected ctx
                PY05 McpError -> MCPError         PY06 -32002 -> -32602 (auto)
                PY07 elicitation -> InputRequiredResult  PY08 low-level decorators
    both        VERIFY build, test, re-review against a baseline, probe both eras

TS01 also reads the target release's `peerDependencies`: moving
`@modelcontextprotocol/ext-apps` to 2.x adds its non-optional peers
(`@modelcontextprotocol/client`, `@modelcontextprotocol/core`) in the same
place the dependency lives (pnpm catalog or package.json), and the plan says
when `.npmrc` / `pnpm-workspace.yaml` turns on strict peer dependencies (MIG004).

*auto* steps are mechanical edits `apply_codemod.py` can show as a diff and
apply after confirmation; *guided* steps carry a before/after and a reference
section, because they need judgement. Each file a step touches is recorded with
its SHA-256 so the codemod refuses to edit anything that changed after planning.

Dual-version is the default: 2026-07-28 per request, 2025-era clients still
answered. `--modern-only` plans `legacy: 'reject'` and says what that drops.

With `--out plan.json` the plan is also saved for `apply_codemod.py`; with
`--dry-run` nothing is saved and the path is only named.

    plan_migration.py <project> [--target 2026-07-28] [--unit name] [--modern-only]
                      [--out plan.json] [--dry-run] [--json]

Exit codes: 0 plan produced, 2 nothing to migrate from (no server).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from mcp_server_skills import SPEC_TARGET  # noqa: E402
from mcp_server_skills.cli import add_dry_run, add_output, emit, fail, parser  # noqa: E402
from mcp_server_skills.codemods import build_plan  # noqa: E402
from mcp_server_skills.inventory import build, select  # noqa: E402
from mcp_server_skills.report import EXIT_OK, EXIT_USAGE, GapReport, Option  # noqa: E402
from mcp_server_skills.review_rules import review  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = parser(__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--target", default=SPEC_TARGET)
    p.add_argument("--unit", help="only this server (package name or path suffix)")
    p.add_argument("--modern-only", action="store_true",
                   help="plan legacy: 'reject' (drops 2025-11-25 clients, Alexa+ included)")
    p.add_argument("--out", help="also save the plan JSON here, for apply_codemod.py")
    add_dry_run(p)
    add_output(p, strict=False)
    args = p.parse_args(argv)

    root = Path(args.project).expanduser()
    if not root.exists():
        return fail(f"{root} does not exist")
    inventory = build(root)
    units = select(inventory, args.unit)
    report = GapReport(subject=str(inventory.root), skill="mcp-migrate")
    if not units:
        report.add("DSC001", f"no MCP server under {root}", path=str(inventory.root))
        return emit(report, args, code=EXIT_USAGE)
    if len(units) > 1 and not args.unit:
        report.add("DSC002", "plan one server at a time; pass --unit", path=str(inventory.root))
        return emit(report, args, code=EXIT_USAGE)
    unit = units[0]
    findings = GapReport(subject=str(inventory.root), skill="mcp-review")
    review(unit, findings, target=args.target)
    plan = build_plan(unit, inventory.root, set(findings.ids()), target=args.target,
                      modern_only=args.modern_only)
    real_steps = [s for s in plan["steps"] if s["id"] != "VERIFY"]
    if not any(s["kind"] in ("deps", "imports", "transport") for s in real_steps) and \
            not findings.has_errors():
        report.add("MIG003", f"the review found no blocking finding for {args.target}", path=str(unit.path))
    for step in real_steps:
        peers = (step.get("detail") or {}).get("peers")
        if peers and (peers.get("missing") or peers.get("strict_peer_dependencies")):
            strict = peers.get("strict_peer_dependencies")
            missing = ", ".join(peers.get("missing") or []) or "none missing"
            report.add("MIG004", f"{step['id']}: {peers.get('package', 'a dependency bump')} peers to add: {missing}"
                       + ("; strict-peer-dependencies is on, so an install without them fails" if strict else ""),
                       severity="warn" if strict and peers.get("missing") else None,
                       path=peers.get("strict_source") or str(unit.path))
        if not step["auto"]:
            report.add("MIG001", f"{step['id']} {step['title']}", path=", ".join(step["files"]) or str(unit.path),
                       locator=step["reference"] or None)
    report.discovered = {
        "unit": plan["unit"], "language": plan["language"], "target": plan["target"], "mode": plan["mode"],
        "review": findings.summary, "review_ids": sorted(set(findings.ids())),
        "steps": [{"id": s["id"], "auto": s["auto"], "title": s["title"],
                   "files": ", ".join(s["files"]) or "-", **({"notes": s["notes"]} if s.get("notes") else {})}
                  for s in plan["steps"]],
        "write_plan": sorted({e["path"] for s in plan["steps"] if s["auto"] for e in s["edits"]}),
    }
    if args.out and not args.dry_run:
        Path(args.out).write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        report.discovered["saved"] = args.out
    elif args.out:
        report.discovered["would_save"] = args.out
    report.add_option(Option("1", "Show the diff of the auto steps", cost="free", recommended=True,
                             runs=[f"apply_codemod.py {root} --plan {args.out or 'plan.json'} --dry-run"]))
    report.add_option(Option("2", "Apply the auto steps after reading the diff", cost="write",
                             writes=report.discovered["write_plan"],
                             runs=[f"apply_codemod.py {root} --plan {args.out or 'plan.json'} --apply"]))
    report.add_option(Option("3", "Walk the guided steps one by one", cost="write",
                             detail="before/after per step; re-run the review after each"))
    if args.format == "json" and args.out is None:
        # A skill that wants the full plan without saving it reads it from here.
        report.discovered["plan"] = plan
    return emit(report, args, code=EXIT_OK)


if __name__ == "__main__":
    raise SystemExit(main())
