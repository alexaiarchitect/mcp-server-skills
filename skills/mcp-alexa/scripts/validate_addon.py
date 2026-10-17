#!/usr/bin/env python3
"""Validate an Alexa+ add-on manifest (`addon.json`) before `alexa-ai deploy` does.

Checks the shape the MCP toolkit quickstart documents and the store-listing
rules from the functional requirements:

    ALX00x  file present, valid JSON, manifestVersion "1.0"
    ALX01x  distributionCountries; locale keys; name <= 30; shortDescription <= 123;
            fullDescription <= 4000; 3-4 distinct example phrases <= 200; HTTPS privacy
            policy and terms URLs; the six light icon sizes; carousel images
            (600x900, alt text <= 250, PNG/JPG/JPEG/WEBP over HTTPS)
    ALX02x  an MCP integration with an HTTPS endpoint; the endpoint matches the
            server's canonical URI (--endpoint); no developer jargon in customer text

A country outside the documented availability (United States) is a warning,
not an error: the docs say where the toolkit is available today, not what the
manifest may contain.

    validate_addon.py <addon.json | project-dir> [--endpoint https://.../mcp] [--json] [--strict]

Exit codes: 0 valid, 1 errors (or warnings under --strict), 2 no addon.json found.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from mcp_server_skills.addon import load, validate  # noqa: E402
from mcp_server_skills.alexa_rules import find_addon  # noqa: E402
from mcp_server_skills.auth_rules import _same_resource  # noqa: E402
from mcp_server_skills.cli import add_output, emit, fail, parser  # noqa: E402
from mcp_server_skills.report import EXIT_USAGE, GapReport, Option  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = parser(__doc__)
    p.add_argument("target", nargs="?", default=".", help="addon.json or a directory containing one")
    p.add_argument("--endpoint", help="the server's canonical MCP URI (PRM `resource`)")
    p.add_argument("--tool", action="append", default=[], help="a tool name to treat as jargon (repeatable)")
    add_output(p)
    args = p.parse_args(argv)
    target = Path(args.target).expanduser()
    if not target.exists():
        return fail(f"{target} does not exist")
    path = target if target.is_file() else find_addon(target, target)
    report = GapReport(subject=str(path or target), skill="mcp-alexa")
    if path is None:
        report.add("ALX001", f"no addon.json under {target}", path=str(target))
        report.add_option(Option("1", "Scaffold it with the Alexa AI CLI", cost="write", recommended=True,
                                 runs=['alexa-ai new mcp --name "<name>" --locale en-US --mcp-server-url <url>']))
        return emit(report, args, code=EXIT_USAGE)
    doc, error = load(path)
    if doc is None:
        report.add("ALX002", error or "unreadable", path=str(path))
        return emit(report, args)
    summary = validate(doc, report, str(path), tool_names=tuple(args.tool))
    if args.endpoint:
        for uri in summary["endpoints"]:
            if not _same_resource(uri, args.endpoint):
                report.add("ALX021", f"addon endpoint {uri} vs server {args.endpoint}", path=str(path),
                           locator="integrations")
    report.discovered = summary
    report.add_option(Option("1", "Fix the manifest", cost="write", recommended=report.has_errors(),
                             writes=[str(path)]))
    report.add_option(Option("2", "Deploy to the development stage", cost="deploy",
                             runs=["alexa-ai deploy"], detail="Alexa+ re-reads tools only on deploy"))
    return emit(report, args)


if __name__ == "__main__":
    raise SystemExit(main())
