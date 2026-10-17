"""`route.py`, `discover.py` and `lint_server.py`, as a skill runs them.

Findings are asserted by id, because an id is what a skill branches on and what
a user quotes back.
"""

from __future__ import annotations

import json

import pytest

from mcp_server_skills.report import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE

ROUTE = "skills/mcp-server/scripts/route.py"
DISCOVER = "skills/mcp-discover/scripts/discover.py"
LINT = "skills/mcp-review/scripts/lint_server.py"


# -- router -----------------------------------------------------------------------

def test_the_router_counts_bands_and_recommends_migration_for_a_v1_server(run_script, project):
    result = run_script(ROUTE, project("ts_v1_lambda"), "--json")
    assert result.returncode == EXIT_OK
    data = result.json()
    assert data["discovered"]["findings_by_band"]["MCP"]["errors"] >= 3
    recommended = [o for o in data["options"] if o["recommended"]]
    assert [o["skill"] for o in recommended] == ["/mcp-server:mcp-migrate"]


def test_the_router_honours_an_intent(run_script, project):
    data = run_script(ROUTE, project("ts_v1_lambda"), "--intent", "alexa", "--json").json()
    assert "ALX" in data["discovered"]["findings_by_band"]
    assert [o["skill"] for o in data["options"] if o["recommended"]] == ["/mcp-server:mcp-alexa"]


def test_the_router_recommends_verifying_a_clean_v2_server(run_script, project):
    data = run_script(ROUTE, project("ts_v2"), "--json").json()
    assert [o["skill"] for o in data["options"] if o["recommended"]] == ["/mcp-server:mcp-verify"]


def test_the_router_says_when_there_is_nothing(run_script, tmp_path):
    result = run_script(ROUTE, tmp_path, "--json")
    assert result.returncode == EXIT_USAGE
    assert result.ids() == {"DSC001"}


# -- discover ------------------------------------------------------------------------

def test_discover_reports_the_inventory(run_script, project):
    result = run_script(DISCOVER, project("ts_v1_lambda"), "--json")
    assert result.returncode == EXIT_OK
    unit = result.json()["discovered"]["units"][0]
    assert unit["path"] == "apps/mcp-server"
    assert unit["sdk"]["resolved"] == "1.29.0" and unit["sdk"]["declared"] == "catalog:"
    assert unit["era"] == "handshake" and "initialize" in unit["era_meaning"]
    assert unit["auth"]["authorization_server"] == ["unknown"] or unit["auth"]["token_verification"]
    assert {t["name"] for t in unit["tools"]} == {"search_books", "get_book", "prepare_loan"}
    assert unit["extensions"]["apps"] is True
    ci = result.json()["discovered"]["ci"]
    assert ci["workflows"] and ci["runs_mcp_review"] is False
    assert any(g["id"] == "GAP-CI-REVIEW" for g in result.json()["gaps"])


def test_discover_markdown_explains_the_era(run_script, project):
    out = run_script(DISCOVER, project("py_v2")).stdout
    assert "era=dual" in out and "## Options" in out


def test_discover_flags_unresolvable_versions_and_several_servers(run_script, tmp_path):
    for name in ("a", "b"):
        d = tmp_path / name
        d.mkdir()
        (d / "package.json").write_text('{"name": "%s", "dependencies": {"@modelcontextprotocol/sdk": "catalog:"}}' % name)
        (d / "index.ts").write_text("import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';\n")
    result = run_script(DISCOVER, tmp_path, "--json")
    assert {"DSC002", "DSC003"} <= result.ids()
    assert len(result.json()["discovered"]["units"]) == 2
    only = run_script(DISCOVER, tmp_path, "--unit", "b", "--json").json()
    assert [u["name"] for u in only["discovered"]["units"]] == ["b"]


def test_discover_reports_parse_errors(run_script, tmp_path):
    (tmp_path / "requirements.txt").write_text("mcp>=2.3\n")
    (tmp_path / "server.py").write_text("from mcp.server.mcpserver import MCPServer\ndef broken(:\n")
    result = run_script(DISCOVER, tmp_path, "--json")
    assert "DSC010" in result.ids() and result.returncode == EXIT_OK


def test_discover_with_no_server_exits_2(run_script, tmp_path):
    assert run_script(DISCOVER, tmp_path, "--json").returncode == EXIT_USAGE


# -- review ----------------------------------------------------------------------------

@pytest.mark.parametrize("fixture,expected", [
    ("ts_v1_lambda", {"MCP001", "MCP002", "MCP011", "MCP012", "MCP015", "MCP020", "MCP031", "MCP050"}),
    ("py_v1_fastmcp", {"MCP001", "MCP011", "MCP012", "MCP020", "MCP040", "MCP050", "MCP060", "MCP070"}),
    ("ts_stdio", {"MCP001", "MCP011", "MCP012", "MCP040", "MCP041", "MCP061", "MCP062", "MCP064",
                  "MCP065", "MCP066", "MCP067", "MCP070", "MCP080"}),
])
def test_each_fixture_reports_the_findings_it_was_built_for(run_script, project, fixture, expected):
    result = run_script(LINT, project(fixture), "--json")
    found = result.ids()
    assert expected <= found, f"missing {sorted(expected - found)}"
    assert result.returncode == EXIT_FINDINGS


@pytest.mark.parametrize("fixture", ["ts_v2", "py_v2"])
def test_v2_servers_have_no_errors(run_script, project, fixture):
    result = run_script(LINT, project(fixture), "--json")
    assert result.json()["summary"]["errors"] == 0
    assert result.returncode == EXIT_OK
    assert not result.ids() & {"MCP001", "MCP011", "MCP012", "MCP020"}


def test_a_handshake_server_is_fine_against_2025_11_25(run_script, project):
    found = run_script(LINT, project("ts_v1_lambda"), "--target", "2025-11-25", "--json").ids()
    assert not found & {"MCP001", "MCP011", "MCP012", "MCP020", "MCP031", "MCP050"}


def test_strict_fails_on_warnings(run_script, project):
    assert run_script(LINT, project("py_v2"), "--json").returncode == EXIT_OK
    review = run_script(LINT, project("ts_v1_lambda"), "--target", "2025-11-25", "--json")
    if review.json()["summary"]["warnings"]:
        assert run_script(LINT, project("ts_v1_lambda"), "--target", "2025-11-25", "--strict",
                          "--json").returncode == EXIT_FINDINGS


def test_modern_only_and_reserved_codes_and_public_cache(run_script, tmp_path):
    (tmp_path / "package.json").write_text('{"name": "m", "dependencies": {"@modelcontextprotocol/server": "^2.3.1"}}')
    (tmp_path / "index.ts").write_text(
        "import { createMcpHandler, McpServer } from '@modelcontextprotocol/server';\n"
        "import { jwtVerify } from 'jose';\n"
        "const f = () => new McpServer({ name: 'x', version: '1' }, { cacheHints: { cacheScope: 'public' } });\n"
        "export default createMcpHandler(f, { legacy: 'reject' });\n"
        "const HeaderMismatch = -32001; // HeaderMismatch with the draft number\n"
        "throw new Error(String(-32042));\n"
        "await jwtVerify(t, k, { audience: 'https://x/mcp' });\n")
    found = run_script(LINT, tmp_path, "--json").ids()
    assert {"MCP013", "MCP032", "MCP051", "MCP052"} <= found


def test_the_baseline_reports_new_and_resolved(run_script, project, tmp_path):
    before = run_script(LINT, project("ts_v1_lambda"), "--json")
    saved = tmp_path / "before.json"
    saved.write_text(before.stdout)
    after = run_script(LINT, project("ts_v1_lambda"), "--baseline", saved, "--json").json()
    delta = after["discovered"]["delta"]
    assert delta["new"] == [] and delta["resolved"] == [] and len(delta["unchanged"]) == len(after["findings"])


def test_a_future_target_is_reviewed_with_the_newest_rules_and_says_so(run_script, project):
    data = run_script(LINT, project("ts_v2"), "--target", "2027-03-30", "--json").json()
    assert data["discovered"]["rules_for"] == "2026-07-28"
    assert "newer than the revisions these rules know" in data["discovered"]["note"]


def test_bad_target_and_missing_path(run_script, project, tmp_path):
    assert run_script(LINT, project("ts_v2"), "--target", "latest").returncode == EXIT_USAGE
    assert run_script(LINT, tmp_path / "missing").returncode == EXIT_USAGE
    assert run_script(LINT, tmp_path, "--json").returncode == EXIT_USAGE


def test_findings_carry_a_source_and_a_location(run_script, project):
    data = run_script(LINT, project("ts_v1_lambda"), "--json").json()
    mcp011 = next(f for f in data["findings"] if f["id"] == "MCP011")
    assert mcp011["path"].endswith("handler.ts") and mcp011["locator"].startswith("line ")
    assert all(f["source"].startswith("https://") for f in data["findings"])
    json.dumps(data)  # serialisable
