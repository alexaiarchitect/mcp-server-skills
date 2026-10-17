"""Reports, the catalog contract, baselines and the frontmatter reader."""

from __future__ import annotations

import json

import pytest

from mcp_server_skills import catalog, frontmatter
from mcp_server_skills.report import (
    EXIT_FINDINGS, EXIT_INCONCLUSIVE, EXIT_OK, GapReport, Option, diff_findings, exit_code_for, load_findings,
)


def test_add_takes_severity_fix_and_source_from_the_catalog():
    report = GapReport(subject="/p", skill="mcp-review")
    finding = report.add("MCP011", "handshake only", path="/p/a.ts", locator="line 3")
    entry = catalog.lookup("MCP011")
    assert (finding.severity, finding.fix, finding.source) == (entry.severity, entry.fix, entry.source)
    assert report.add("MCP031", "x", severity="info").severity == "info"


def test_unknown_ids_are_refused():
    with pytest.raises(KeyError):
        GapReport(subject="/p", skill="x").add("MCP999", "nope")


def test_duplicates_are_dropped_and_ordering_is_by_severity():
    report = GapReport(subject="/p", skill="x")
    report.add("MCP002", "note")
    report.add("MCP011", "error")
    report.add("MCP011", "error")
    assert [f["id"] for f in report.to_dict()["findings"]] == ["MCP011", "MCP002"]


def test_exit_codes():
    report = GapReport(subject="/p", skill="x")
    assert exit_code_for(report) == EXIT_OK
    assert exit_code_for(report, inconclusive=True) == EXIT_INCONCLUSIVE
    report.add("MCP010", "w")
    assert exit_code_for(report) == EXIT_OK
    assert exit_code_for(report, strict=True) == EXIT_FINDINGS
    report.add("MCP011", "e")
    assert exit_code_for(report) == EXIT_FINDINGS


def test_markdown_has_found_findings_options_and_summary():
    report = GapReport(subject="/p", skill="mcp-review", discovered={"units": [{"unit": "a", "sdk": {"major": 1}}]})
    report.add("MCP011", "handshake only", path="/p/src/a.ts", locator="line 3")
    report.add_option(Option("1", "Plan", recommended=True, cost="free", skill="/mcp-server:mcp-migrate"))
    md = report.to_md()
    for part in ("## Found", "## Errors", "`MCP011` src/a.ts line 3", "## Options", "(recommended)",
                 "cost: free", "_Summary: 1 error(s)"):
        assert part in md
    assert "major" in md, "nested values in list items are rendered"


def test_baseline_diff(tmp_path):
    before = GapReport(subject=str(tmp_path), skill="x")
    before.add("MCP011", "a", path=str(tmp_path / "h.ts"), locator="line 1")
    before.add("MCP050", "b", path=str(tmp_path / "s.ts"), locator="line 9")
    saved = tmp_path / "before.json"
    saved.write_text(before.to_json())
    after = GapReport(subject=str(tmp_path), skill="x")
    after.add("MCP050", "b", path=str(tmp_path / "s.ts"), locator="line 9")
    after.add("MCP031", "c", path=str(tmp_path / "package.json"))
    delta = diff_findings(load_findings(str(saved)), after.findings, relative_to=str(tmp_path))
    assert delta["new"] == ["MCP031 package.json"]
    assert delta["resolved"] == ["MCP011 h.ts line 1"]
    assert delta["unchanged"] == ["MCP050 s.ts line 9"]


def test_catalog_bands_are_complete_and_ids_well_formed():
    assert set(catalog.BANDS) == {i.rstrip("0123456789") for i in catalog.CATALOG}
    for fid in catalog.CATALOG:
        assert fid[-3:].isdigit()


def test_frontmatter_reads_folded_descriptions_lists_and_scalars():
    doc = frontmatter.parse("---\nname: x\ndescription: >-\n  one\n  two\nmax_turns: 12\n"
                            "tools: [Read, \"Bash(python3 *)\"]\nlist:\n  - a\n  - b\n---\nbody\n")
    assert doc.meta == {"name": "x", "description": "one two", "max_turns": 12,
                        "tools": ["Read", "Bash(python3 *)"], "list": ["a", "b"]}
    assert doc.body == "body"


def test_frontmatter_rejects_what_it_cannot_read():
    with pytest.raises(frontmatter.FrontmatterError):
        frontmatter.parse("---\nkey: {a: 1}\n---\n")
    with pytest.raises(frontmatter.FrontmatterError):
        frontmatter.parse("---\nname: x\n")


def test_report_json_round_trips():
    report = GapReport(subject="/p", skill="x")
    report.add("ALX016", "phrases")
    data = json.loads(report.to_json())
    assert data["schema"] == "mcp-server-skills.gap-report/1"
    assert data["summary"] == {"errors": 1, "warnings": 0, "infos": 0}
