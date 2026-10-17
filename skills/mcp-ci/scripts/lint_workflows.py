#!/usr/bin/env python3
"""Check a repository's GitHub workflows for an MCP gate that actually gates.

    CI001  no workflow runs the MCP review (lint_server.py)
    CI002  no workflow probes the deployed endpoint (probe.py)
    CI003  a bearer token or key written into a workflow instead of a secret
    CI004  the review or probe exit code is masked (`|| true`, `continue-on-error: true`)
    CI005  the plugin is cloned from an unpinned ref (main/master/HEAD or no --branch)

Read only; workflows are scanned as text, no YAML library needed.

    lint_workflows.py <repo> [--json] [--strict]

Exit codes: 0 no errors, 1 errors (or warnings under --strict), 2 not a directory.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from mcp_server_skills.cli import add_output, emit, fail, parser  # noqa: E402
from mcp_server_skills.report import GapReport, Option  # noqa: E402

SECRET_LITERAL = re.compile(r"(Bearer\s+[A-Za-z0-9._\-]{16,}|--token\s+['\"]?[A-Za-z0-9._\-]{16,}|"
                            r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,})")
MASKED = re.compile(r"(lint_server\.py|probe\.py)[^\n]*\|\|\s*true")


def main(argv: list[str] | None = None) -> int:
    p = parser(__doc__)
    p.add_argument("repo", nargs="?", default=".")
    add_output(p)
    args = p.parse_args(argv)
    root = Path(args.repo).expanduser()
    if not root.is_dir():
        return fail(f"{root} is not a directory")
    wf_dir = root / ".github" / "workflows"
    workflows = sorted(p for p in wf_dir.glob("*.y*ml")) if wf_dir.is_dir() else []
    report = GapReport(subject=str(root), skill="mcp-ci")
    runs_review = runs_probe = False
    for wf in workflows:
        text = wf.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        runs_review |= "lint_server.py" in text
        runs_probe |= "probe.py" in text
        for i, line in enumerate(lines, 1):
            if SECRET_LITERAL.search(line) and "${{" not in line:
                report.add("CI003", "a credential-looking literal", path=str(wf), locator=f"line {i}")
            if MASKED.search(line):
                report.add("CI004", "`|| true` after an MCP gate", path=str(wf), locator=f"line {i}")
            if "mcp-server-skills" in line and "git clone" in line:
                branch = re.search(r"--branch\s+\"?([^\s\"]+)", line)
                ref = branch.group(1) if branch else None
                if ref in (None, "main", "master", "HEAD"):
                    report.add("CI005", f"cloned from {ref or 'the default branch'}", path=str(wf), locator=f"line {i}")
        for match in re.finditer(r"continue-on-error:\s*true", text):
            line_no = text[:match.start()].count("\n") + 1
            window = "\n".join(lines[max(0, line_no - 8):line_no + 8])
            if "lint_server.py" in window or "probe.py" in window:
                report.add("CI004", "continue-on-error on an MCP gate", path=str(wf), locator=f"line {line_no}")
    if not runs_review:
        report.add("CI001", f"{len(workflows)} workflow(s), none runs lint_server.py", path=str(wf_dir))
    if not runs_probe:
        report.add("CI002", "nothing probes the deployed endpoint", path=str(wf_dir))
    report.discovered = {"workflows": [str(w.relative_to(root)) for w in workflows],
                         "runs_review": runs_review, "runs_probe": runs_probe}
    if not runs_review or not runs_probe:
        report.add_option(Option("1", "Generate the conformance workflow", skill="/mcp-server:mcp-ci",
                                 cost="write", recommended=True, writes=[".github/workflows/mcp-conformance.yml"],
                                 runs=["gen_workflow.py <repo> --dry-run", "gen_workflow.py <repo>"]))
    return emit(report, args)


if __name__ == "__main__":
    raise SystemExit(main())
