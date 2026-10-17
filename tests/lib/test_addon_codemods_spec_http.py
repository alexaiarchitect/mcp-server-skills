"""addon.json validation, the codemod engine, the versioning-page parser and the HTTP client."""

from __future__ import annotations

import json
from pathlib import Path

from mcp_server_skills import addon, codemods, inventory, jsonrpc, specpage
from mcp_server_skills.report import GapReport


# -- addon.json ------------------------------------------------------------------

def validate(path: Path, **kw) -> set[str]:
    report = GapReport(subject=str(path), skill="mcp-alexa")
    doc, err = addon.load(path)
    assert err is None
    addon.validate(doc, report, str(path), **kw)
    return set(report.ids())


def test_a_good_manifest_passes(project):
    assert validate(project("addon_good") / "addon.json") == set()


def test_a_broken_manifest_fails_on_every_planted_defect(project):
    ids = validate(project("addon_broken") / "addon.json")
    assert ids == {"ALX003", "ALX011", "ALX012", "ALX013", "ALX015", "ALX016", "ALX017", "ALX018",
                   "ALX019", "ALX020", "ALX022"}


def test_tool_names_count_as_jargon(project, tmp_path):
    doc = json.loads((project("addon_good") / "addon.json").read_text())
    doc["storeListing"]["locales"]["en-US"]["examplePhrases"][0] = "run reserve_book now"
    path = tmp_path / "addon.json"
    path.write_text(json.dumps(doc))
    assert "ALX022" in validate(path, tool_names=("reserve_book",))


def test_invalid_json_is_reported_with_a_position(tmp_path):
    path = tmp_path / "addon.json"
    path.write_text("{\n  \"manifestVersion\": \"1.0\",\n}")
    doc, err = addon.load(path)
    assert doc is None and err.startswith("line ") and " column " in err  # position differs by Python version


# -- codemods ------------------------------------------------------------------------

def test_a_plan_records_hashes_and_marks_auto_and_guided(project):
    unit = inventory.build(project("ts_v1_lambda")).units[0]
    plan = codemods.build_plan(unit, project("ts_v1_lambda").resolve(), {"MCP001", "MCP011"})
    ids = [s["id"] for s in plan["steps"]]
    assert ids[:4] == ["TS00", "TS01", "TS02", "TS03"]
    assert ids[-1] == "VERIFY"
    auto = {s["id"] for s in plan["steps"] if s["auto"]}
    assert auto == {"TS01", "TS02", "TS06"}
    assert set(plan["files"]) >= {"pnpm-workspace.yaml", "apps/mcp-server/package.json"}
    assert plan["mode"] == "dual"


def test_modern_only_plans_legacy_reject(project):
    unit = inventory.build(project("ts_v1_lambda")).units[0]
    plan = codemods.build_plan(unit, project("ts_v1_lambda").resolve(), set(), modern_only=True)
    ts03 = next(s for s in plan["steps"] if s["id"] == "TS03")
    assert "legacy: 'reject'" in ts03["after"] and "Alexa+" in ts03["why"]


def test_apply_writes_only_when_asked_and_refuses_changed_files(tmp_project):
    root = tmp_project("ts_v1_lambda").resolve()
    plan = codemods.build_plan(inventory.build(root).units[0], root, {"MCP001"})
    dry = codemods.apply_plan(plan, root, write=False)
    assert dry["written"] == [] and "pnpm-workspace.yaml" in dry["diffs"]
    assert "@modelcontextprotocol/server: 2.3.1" in dry["diffs"]["pnpm-workspace.yaml"].replace('"', "")
    (root / "apps/mcp-server/package.json").write_text((root / "apps/mcp-server/package.json").read_text() + "\n")
    wet = codemods.apply_plan(plan, root, write=True)
    assert {r["path"] for r in wet["refused"]} == {"apps/mcp-server/package.json"}
    assert "pnpm-workspace.yaml" in wet["written"]
    assert "@modelcontextprotocol/server" in (root / "pnpm-workspace.yaml").read_text()


def test_python_plan_rewrites_requirements_and_imports(tmp_project):
    root = tmp_project("py_v1_fastmcp").resolve()
    plan = codemods.build_plan(inventory.build(root).units[0], root, {"MCP001"})
    assert [s["id"] for s in plan["steps"] if s["auto"]] == ["PY01", "PY02", "PY06"]
    out = codemods.apply_plan(plan, root, write=True)
    assert sorted(out["written"]) == ["requirements.txt", "server.py"]
    server = (root / "server.py").read_text()
    assert "from mcp.server.mcpserver import Context, MCPServer" in server
    assert "MCPServer(\"library-desk\"" in server and "-32602" in server
    assert (root / "requirements.txt").read_text().splitlines()[0] == "mcp[cli]>=2.3,<3"


# -- versioning page --------------------------------------------------------------------

def test_current_revision_from_markdown_and_html(fixtures):
    assert specpage.current_revision((fixtures / "spec/versioning-2026-07-28.md").read_text()) == "2026-07-28"
    assert specpage.current_revision((fixtures / "spec/versioning-synthetic-newer.html").read_text()) == "2027-03-30"
    assert specpage.current_revision((fixtures / "spec/versioning-unparseable.html").read_text()) is None


def test_newer_versions_and_the_delta_text():
    newer = specpage.newer_versions({"@modelcontextprotocol/server": "2.4.0", "mcp": "2.3.0"})
    assert newer == {"@modelcontextprotocol/server": ("2.3.1", "2.4.0")}
    text = specpage.delta_markdown(pinned="2026-07-28", live="2027-03-30", newer=newer, source="x",
                                   today="2027-04-01")
    assert "2026-07-28 -> 2027-03-30" in text and "--target 2027-03-30" in text
    assert "/specification/2027-03-30/changelog" in text and "2.3.1 -> 2.4.0" in text
    same = specpage.delta_markdown(pinned="2026-07-28", live="2026-07-28", newer={}, source="x")
    assert "no change" in same


# -- HTTP client ------------------------------------------------------------------------

def test_modern_request_shape_and_sse_parsing(fake_server):
    url = fake_server("dual")
    reply = jsonrpc.modern_request(url, "server/discover")
    assert reply.status == 200 and reply.result["resultType"] == "complete"
    sse = jsonrpc.Reply(200, {}, 'event: message\ndata: {"jsonrpc":"2.0","method":"notifications/progress"}\n\n'
                        'data: {"jsonrpc":"2.0","id":5,"result":{"ok":true}}\n\n', 1.0,
                        content_type="text/event-stream")
    jsonrpc._parse_message(sse, 5)
    assert sse.sse and sse.result == {"ok": True}


def test_www_authenticate_parsing_and_percentiles():
    parsed = jsonrpc.parse_www_authenticate('Bearer resource_metadata="https://x/.well-known/p", scope="a b"')
    assert parsed == {"scheme": "Bearer", "resource_metadata": "https://x/.well-known/p", "scope": "a b"}
    assert jsonrpc.percentile([5, 1, 3, 2, 4], 50) == 3
    assert jsonrpc.percentile([float(i) for i in range(1, 21)], 95) == 19
    assert jsonrpc.percentile([], 95) is None


def test_unreachable_urls_are_errors_not_exceptions():
    reply = jsonrpc.http("http://127.0.0.1:9/mcp", timeout=2)
    assert reply.status == 0 and reply.error
