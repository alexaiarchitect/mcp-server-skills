#!/usr/bin/env python3
"""Append one structured row to the project's friction log (`docs/FRICTION-LOG.md`).

A migration or an Alexa+ onboarding produces small surprises — a doc that says
one thing and a simulator that does another, a CLI flag that moved, a latency
spike nobody predicted. Written down as they happen, with what was expected and
what happened, they become the evidence for a bug report, a write-up, or the
next person's shortcut. Written down later, they are gone.

Each row: date, area, step, expected, actual, severity (`blocker`, `major`,
`minor`, `note`), workaround, and a link (doc, issue, commit). The file is
created with its header the first time. Pipes and newlines in values are
escaped so a row is always one table row.

`--dry-run` prints the row and the file it would go to, and writes nothing.

    friction_log.py <project> --area alexa --step "account linking" --expected "..." --actual "..."
                    [--severity minor] [--workaround "..."] [--link URL] [--dry-run] [--json]

Exit codes: 0 appended (or would be), 2 usage error.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from mcp_server_skills.cli import add_dry_run, fail, parser  # noqa: E402

LOG = Path("docs") / "FRICTION-LOG.md"
HEADER = """# Friction log

Every surprise met while building, migrating or certifying this MCP server: what
was expected, what happened, and what got us past it. One row per event, newest
last. Appended by `friction_log.py` (mcp-server plugin); edit freely.

| Date | Area | Step | Expected | Actual | Severity | Workaround | Link |
|---|---|---|---|---|---|---|---|
"""
SEVERITIES = ("blocker", "major", "minor", "note")


def cell(value: str | None) -> str:
    text = (value or "").strip().replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")
    return text or "-"


def main(argv: list[str] | None = None) -> int:
    p = parser(__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--area", required=True, help="e.g. alexa, auth, migrate, deploy, latency")
    p.add_argument("--step", required=True, help="what was being done")
    p.add_argument("--expected", required=True)
    p.add_argument("--actual", required=True)
    p.add_argument("--severity", choices=SEVERITIES, default="minor")
    p.add_argument("--workaround")
    p.add_argument("--link")
    p.add_argument("--date", default=date.today().isoformat())
    p.add_argument("--json", action="store_true", help="print the row as JSON")
    add_dry_run(p)
    args = p.parse_args(argv)
    root = Path(args.project).expanduser()
    if not root.is_dir():
        return fail(f"{root} is not a directory")
    path = root / LOG
    row = "| " + " | ".join(cell(v) for v in (args.date, args.area, args.step, args.expected, args.actual,
                                               args.severity, args.workaround, args.link)) + " |"
    created = not path.is_file()
    if not args.dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.is_file() else HEADER
        if not existing.endswith("\n"):
            existing += "\n"
        path.write_text(existing + row + "\n", encoding="utf-8")
    result = {"path": str(path), "row": row, "created": created, "written": not args.dry_run}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        verb = "would append to" if args.dry_run else "appended to"
        print(f"{verb} {path}{' (new file)' if created else ''}:\n{row}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
