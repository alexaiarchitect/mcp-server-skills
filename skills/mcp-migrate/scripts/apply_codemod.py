#!/usr/bin/env python3
"""Apply the *auto* steps of a migration plan — as a diff by default, as edits only with --apply.

Reads a plan saved by `plan_migration.py --out plan.json` and, for every step
marked `auto`, performs its literal or regex edits in memory and prints the
unified diff. Nothing is written unless `--apply` is given, and even then:

- a file whose SHA-256 differs from the one recorded in the plan is refused
  (`MIG002`) — re-plan instead of editing something you have not reviewed;
- guided steps are never touched, only listed (`MIG001`);
- an edit that no longer matches is skipped and reported, not forced.

`--dry-run` is the default behaviour and is accepted for symmetry with the
other writers. `--step TS01 --step TS02` limits the run to named steps.

    apply_codemod.py <project> --plan plan.json [--dry-run | --apply] [--step ID ...] [--json]

Exit codes: 0 diff shown or applied, 1 a file was refused, 2 bad plan or path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from mcp_server_skills.cli import add_dry_run, add_output, fail, parser  # noqa: E402
from mcp_server_skills.codemods import apply_plan, load_plan  # noqa: E402
from mcp_server_skills.report import EXIT_FINDINGS, EXIT_OK, GapReport, Option  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = parser(__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--plan", required=True, help="plan JSON from plan_migration.py --out")
    p.add_argument("--apply", action="store_true", help="write the edits (only after the user confirmed)")
    p.add_argument("--step", action="append", help="limit to these step ids")
    add_dry_run(p)
    add_output(p, strict=False)
    args = p.parse_args(argv)
    root = Path(args.project).expanduser().resolve()
    if not root.is_dir():
        return fail(f"{root} is not a directory")
    try:
        plan = load_plan(Path(args.plan))
    except (OSError, ValueError) as exc:
        return fail(str(exc))
    if Path(plan.get("project", root)).resolve() != root:
        return fail(f"the plan was made for {plan.get('project')}, not {root}")
    write = args.apply and not args.dry_run
    outcome = apply_plan(plan, root, write=write, only=set(args.step) if args.step else None)

    report = GapReport(subject=str(root), skill="mcp-migrate")
    for item in outcome["refused"]:
        report.add("MIG002", f"{item['step']}: {item['reason']}", path=str(root / item["path"]))
    for item in outcome["skipped"]:
        if item.get("reason") == "guided":
            step = next(s for s in plan["steps"] if s["id"] == item["step"])
            report.add("MIG001", f"{step['id']} {step['title']}", path=", ".join(step["files"]) or str(root),
                       locator=step.get("reference") or None)
    report.discovered = {
        "mode": "applied" if write else "dry-run (nothing written)",
        "steps_applied" if write else "steps_with_changes": outcome["applied"],
        "written": outcome["written"],
        "no_match": [f"{s['step']} {s['path']}: {s['reason']}" for s in outcome["skipped"] if s.get("path")],
    }
    if not write and outcome["diffs"]:
        report.add_option(Option("1", "Apply these edits", cost="write", writes=sorted(outcome["diffs"]),
                                 runs=[f"apply_codemod.py {root} --plan {args.plan} --apply"]))
    if args.format == "json":
        data = report.to_dict()
        data["diffs"] = outcome["diffs"]
        print(json.dumps(data, indent=2))
    else:
        print(report.to_md())
        for diff in outcome["diffs"].values():
            print(f"\n```diff\n{diff}```")
    return EXIT_FINDINGS if outcome["refused"] else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
