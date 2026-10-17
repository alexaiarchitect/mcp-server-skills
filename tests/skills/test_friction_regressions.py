"""Regression tests for the frictions logged on the plugin's first real-world use (0.1.0 -> 0.2.0).

Each test names the friction id from that project's friction log. The
`vault_alexa` fixture is an anonymized copy of that MCP server (sources,
workspace files, `.npmrc`, `addon.json`), so these tests replay the exact
situations that produced the frictions.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mcp_server_skills.report import EXIT_OK, GapReport

ROUTE = "skills/mcp-server/scripts/route.py"
DISCOVER = "skills/mcp-discover/scripts/discover.py"
LINT_SERVER = "skills/mcp-review/scripts/lint_server.py"
LINT_AUTH = "skills/mcp-auth/scripts/lint_auth.py"
CHECK_PRM = "skills/mcp-auth/scripts/check_prm.py"
LINT_ALEXA = "skills/mcp-alexa/scripts/lint_alexa.py"
TOOLS_LOCK = "skills/mcp-alexa/scripts/tools_lock.py"
PLAN = "skills/mcp-migrate/scripts/plan_migration.py"
APPLY = "skills/mcp-migrate/scripts/apply_codemod.py"
PROBE = "skills/mcp-verify/scripts/probe.py"

ALEXA_TOOLS = {"find_categories", "describe_category", "log_entry", "confirm_entry", "recent_entries",
               "vault_usage"}


def by_id(doc: dict, fid: str) -> list[dict]:
    return [f for f in doc["findings"] if f["id"] == fid]


# -- F01: the closing summary agrees with the body --------------------------------

def test_f01_router_summary_adds_up_the_band_table(run_script, project):
    doc = run_script(ROUTE, project("vault_alexa"), "--json").json()
    bands = doc["discovered"]["findings_by_band"]
    assert bands, "the vault fixture has review findings"
    assert doc["summary"]["warnings"] == sum(b["warnings"] for b in bands.values())
    assert doc["summary"]["infos"] >= sum(b["notes"] for b in bands.values())
    text = run_script(ROUTE, project("vault_alexa")).stdout
    last = text.strip().splitlines()[-1]
    assert last.startswith(f"_Summary: {doc['summary']['errors']} error(s), {doc['summary']['warnings']} warning(s)")
    assert "0 warning(s), 0 note(s)" not in last


def test_f01_gaps_count_in_the_summary():
    report = GapReport(subject=".", skill="x")
    report.add_gap("G1", "a", "b", "c")
    report.add_gap("G2", "a", "b", "c")
    assert report.summary["gaps"] == 2
    assert report.to_md().strip().endswith("2 gap(s)._")
    assert "gaps" not in GapReport(subject=".", skill="x").summary


# -- F02: findings point at file:line ---------------------------------------------

def test_f02_every_located_finding_has_file_and_line(run_script, project):
    for script in (LINT_AUTH, LINT_ALEXA):
        doc = run_script(script, project("vault_alexa"), "--json").json()
        located = [f for f in doc["findings"] if re.search(r"\bline \d+", f.get("locator", ""))]
        assert located, script
        for finding in located:
            assert finding["file"] == finding["path"]
            assert isinstance(finding["line"], int) and finding["line"] > 0


def test_f02_dependency_findings_point_at_the_manifest_line(run_script, project):
    doc = run_script(LINT_SERVER, project("ts_v1_lambda"), "--json").json()
    for fid in ("MCP001", "MCP002"):
        finding = by_id(doc, fid)[0]
        lines = Path(finding["file"]).read_text().splitlines()
        assert "@modelcontextprotocol/sdk" in lines[finding["line"] - 1]


# -- F03: running a script leaves the plugin tree clean -----------------------------

def test_f03_scripts_write_no_bytecode_into_the_plugin(tmp_path, plugin_root, fixtures):
    copy = tmp_path / "plugin"
    shutil.copytree(plugin_root, copy, ignore=shutil.ignore_patterns("tests", "__pycache__", ".pytest_cache"))
    env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
    for script, args in ((ROUTE, [fixtures / "projects" / "ts_v1_lambda"]), (LINT_ALEXA, ["--help"]),
                         (PLAN, ["--help"])):
        subprocess.run([sys.executable, str(copy / script), *map(str, args)], capture_output=True, env=env,
                       timeout=120, check=False)
    assert list(copy.rglob("__pycache__")) == []


# -- F04: TS01 brings ext-apps 2.x peers, and sees strict-peer-dependencies ----------

def test_f04_catalog_plan_adds_the_ext_apps_peers_and_flags_strict_peers(run_script, tmp_project):
    root = tmp_project("ts_v1_lambda")
    (root / ".npmrc").write_text("engine-strict=true\nstrict-peer-dependencies=true\n")
    plan_file = root / "plan.json"
    result = run_script(PLAN, root, "--unit", "apps/mcp-server", "--out", plan_file, "--json")
    assert result.returncode == EXIT_OK
    doc = result.json()
    mig = by_id(doc, "MIG004")
    assert mig and mig[0]["severity"] == "warn" and "strict-peer-dependencies" in mig[0]["message"]
    plan = json.loads(plan_file.read_text())
    ts01 = next(s for s in plan["steps"] if s["id"] == "TS01")
    peers = ts01["detail"]["peers"]
    assert peers["missing"] == ["@modelcontextprotocol/client", "@modelcontextprotocol/core"]
    assert peers["strict_peer_dependencies"] is True
    assert any("non-optional peers" in n for n in ts01["notes"])
    applied = run_script(APPLY, root, "--plan", plan_file, "--apply", "--step", "TS01", "--json")
    assert applied.returncode == EXIT_OK, applied.combined
    catalog = (root / "pnpm-workspace.yaml").read_text()
    assert '"@modelcontextprotocol/client": 2.3.1' in catalog and '"@modelcontextprotocol/core": 2.3.1' in catalog
    assert re.search(r"@modelcontextprotocol/ext-apps['\"]?\s*:\s*2\.0\.3", catalog)
    manifest = json.loads((root / "apps/mcp-server/package.json").read_text())
    assert manifest["dependencies"]["@modelcontextprotocol/client"] == "catalog:"
    assert manifest["dependencies"]["@modelcontextprotocol/core"] == "catalog:"


def test_f04_plain_package_json_gets_peer_ranges(run_script, tmp_path):
    root = tmp_path / "plain"
    (root / "src").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"name": "plain", "type": "module", "dependencies": {
        "@modelcontextprotocol/sdk": "^1.29.0", "@modelcontextprotocol/ext-apps": "^1.7.4", "zod": "^4.3.6"}},
        indent=2) + "\n")
    (root / "src/index.ts").write_text(
        'import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";\n'
        'import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";\n'
        'const server = new McpServer({ name: "p", version: "1" });\n'
        'const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });\n')
    plan_file = root / "plan.json"
    assert run_script(PLAN, root, "--out", plan_file, "--json").returncode == EXIT_OK
    applied = run_script(APPLY, root, "--plan", plan_file, "--apply", "--step", "TS01", "--json")
    assert applied.returncode == EXIT_OK, applied.combined
    deps = json.loads((root / "package.json").read_text())["dependencies"]
    assert deps["@modelcontextprotocol/ext-apps"] == "^2.0.3"
    assert deps["@modelcontextprotocol/client"] == "^2.3.1" and deps["@modelcontextprotocol/core"] == "^2.3.1"


def test_f04_the_vault_npmrc_is_read_as_strict(project):
    from mcp_server_skills.codemods import package_manager_settings, strict_peers

    root = project("vault_alexa")
    strict = strict_peers(package_manager_settings(root / "apps" / "mcp-server", root))
    assert strict and strict["source"].endswith(".npmrc")


# -- F05 / F06: cache hints shape and the legacy leg's content type ------------------

def test_f05_ts07_emits_the_verified_cache_hint_shape(run_script, project):
    doc = run_script(PLAN, project("ts_v1_lambda"), "--unit", "apps/mcp-server", "--json").json()
    ts07 = next(s for s in doc["discovered"]["plan"]["steps"] if s["id"] == "TS07")
    assert "'server/discover': { ttlMs: 300_000, cacheScope: 'public' }" in ts07["after"]
    assert "Partial<Record<'tools/list'" in ts07["why"]


def test_f05_the_fact_is_promoted_with_its_source(plugin_root):
    path = plugin_root / ".dev" / "VERIFIED-FACTS.md"
    if not path.is_file():
        pytest.skip("the verified-facts ledger is maintainer working notes, not shipped")
    facts = path.read_text()
    row = next(line for line in facts.splitlines() if line.startswith("| TS: exact object shape of `cacheHints`"))
    assert "| V (source) |" in row and "resultCacheHints.ts" in row


def test_f06_ts03_states_the_legacy_content_type_and_the_json_composition(run_script, project):
    doc = run_script(PLAN, project("ts_v1_lambda"), "--unit", "apps/mcp-server", "--json").json()
    ts03 = next(s for s in doc["discovered"]["plan"]["steps"] if s["id"] == "TS03")
    assert "text/event-stream" in ts03["why"]
    assert "isLegacyRequest" in ts03["after"] and "enableJsonResponse: true" in ts03["after"]


def test_f06_the_reference_documents_it(plugin_root):
    text = (plugin_root / "skills/mcp-migrate/references/ts-v1-to-v2.md").read_text()
    assert "text/event-stream" in text and "enableJsonResponse: true" in text


# -- F07 / F08: probe under the Alexa profile, and the GET check -----------------------

def test_f07_a_bare_401_is_a_note_under_the_alexa_profile(run_script, fake_server):
    url = fake_server("dual", token="t", challenge=False)
    alexa = run_script(PROBE, url, "--token", "t", "--n", "1", "--profile", "alexa", "--budget-ms", "5000",
                       "--json").json()
    note = by_id(alexa, "PRB041")[0]
    assert note["severity"] == "info" and "ALX050" in note["message"]
    generic = run_script(PROBE, url, "--token", "t", "--n", "1", "--json").json()
    assert by_id(generic, "PRB041")[0]["severity"] == "warn"


def test_f08_the_get_check_sends_the_token(run_script, fake_server):
    url = fake_server("dual", token="t", auth_get=True)
    with_token = run_script(PROBE, url, "--token", "t", "--n", "1", "--json").json()
    assert "PRB051" not in {f["id"] for f in with_token["findings"]}
    get = next(c for c in with_token["discovered"]["checks"] if c["check"] == "GET on the endpoint")
    assert get["ok"] and get["detail"].startswith("405")
    anonymous = run_script(PROBE, url, "--n", "1", "--json").json()
    assert "PRB051" not in {f["id"] for f in anonymous["findings"]}
    get = next(c for c in anonymous["discovered"]["checks"] if c["check"] == "GET on the endpoint")
    assert "auth before method" in get["detail"]


def test_probe_reports_the_tool_names_it_saw(run_script, fake_server):
    doc = run_script(PROBE, fake_server("dual"), "--n", "1", "--json").json()
    assert doc["discovered"]["tool_names"] == ["search_books", "reserve_book"]


# -- F09 / F10 / F22: scope the Alexa review and lock to what Alexa+ sees -------------

def test_f09_profile_alexa_reviews_only_the_alexa_tools(run_script, project):
    doc = run_script(LINT_ALEXA, project("vault_alexa"), "--profile", "alexa", "--json").json()
    scope = doc["discovered"]["units"][0]["scope"]
    assert set(scope["tools_reviewed"]) == ALEXA_TOOLS
    assert len(scope["tools_left_out"]) == 16
    ids = {f["id"] for f in doc["findings"]}
    assert not ids & {"ALX041", "ALX042", "ALX043"}
    alx050 = by_id(doc, "ALX050")[0]
    assert alx050["severity"] == "info" and "profile.challenge" in alx050["message"]


def test_f09_without_a_scope_every_registration_is_reviewed(run_script, project):
    doc = run_script(LINT_ALEXA, project("vault_alexa"), "--json").json()
    assert {"ALX041", "ALX043"} <= {f["id"] for f in doc["findings"]}
    assert doc["discovered"]["units"][0]["tools"] == 22


def test_f09_tools_from_a_probe_report_win(run_script, project, tmp_path):
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps({"discovered": {"tool_names": [f"vault___{n}" for n in sorted(ALEXA_TOOLS)]}}))
    doc = run_script(LINT_ALEXA, project("vault_alexa"), "--tools-from", probe, "--exclude-tools", "vault_usage",
                     "--json").json()
    scope = doc["discovered"]["units"][0]["scope"]
    assert set(scope["tools_reviewed"]) == ALEXA_TOOLS - {"vault_usage"}
    assert "--tools-from" in scope["selected_by"]
    bad = run_script(LINT_ALEXA, project("vault_alexa"), "--tools-from", tmp_path / "missing.json", "--json")
    assert bad.returncode == 2


def test_f10_a_server_side_page_of_five_passes(project):
    from mcp_server_skills.alexa_rules import voice_page_cap
    from mcp_server_skills.inventory import build

    unit = build(project("vault_alexa")).units[0]
    tools = {t.name: t for t in unit.tools}
    assert voice_page_cap(unit, tools["find_categories"]) == (True, "server-side page size MAX_VOICE_OPTIONS = 5")
    assert voice_page_cap(unit, tools["list_categories"])[0] is False


def test_f10_page_caps_and_tokens(run_script, tmp_path):
    root = tmp_path / "voice"
    (root / "src").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"name": "voice", "dependencies": {
        "@modelcontextprotocol/server": "2.3.1", "zod": "4.3.6"}}))
    (root / "src/server.ts").write_text('''import { McpServer, createMcpHandler } from "@modelcontextprotocol/server";
import { z } from "zod";
const PAGE = 10;
export const mcp = createMcpHandler(() => {
  const server = new McpServer({ name: "v", version: "1" });
  server.registerTool("list_rooms", { description: "Say the rooms.", inputSchema: z.object({}) },
    async () => store.rooms({ limit: PAGE }));
  server.registerTool("search_songs", { description: "Find songs.", inputSchema: z.object({ cursor: z.string().optional() }) },
    async ({ cursor }) => store.songs({ cursor }));
  return server;
});
''')
    doc = run_script(LINT_ALEXA, root, "--no-addon", "--json").json()
    flagged = {f["locator"].split()[-1] for f in by_id(doc, "ALX041")}
    assert flagged == {"list_rooms"}
    assert "PAGE = 10" in by_id(doc, "ALX041")[0]["message"]


def test_f22_tools_lock_records_the_scoped_tools(run_script, tmp_project):
    root = tmp_project("vault_alexa")
    doc = run_script(TOOLS_LOCK, root, "--profile", "alexa", "--write", "--json").json()
    lock = json.loads((root / "docs/alexa-tools.lock.json").read_text())
    assert set(lock["tools"]) == ALEXA_TOOLS and lock["scope"]["profile"] == "alexa"
    assert doc["discovered"]["scope"]["tools_left_out"]
    same = run_script(TOOLS_LOCK, root, "--profile", "alexa", "--json")
    assert same.returncode == EXIT_OK and same.json()["discovered"]["status"] == "unchanged"


# -- F11: AUT021 tells client authentication from bearer passthrough -------------------

FACADE = '''import { McpServer, createMcpHandler } from "@modelcontextprotocol/server";
import { CognitoJwtVerifier } from "./auth.js";
const verifier = new CognitoJwtVerifier({ resource: "https://mcp.example.test/mcp" });
const mcp = createMcpHandler(() => new McpServer({ name: "f", version: "1" }));
export async function handler(request: Request & { headers: Record<string, string>; path: string }) {
  if (request.path === "/.well-known/oauth-protected-resource") return json(200, { authorization_servers: [] });
  if (request.path === "/oauth2/token") {
    const tokenEndpoint = process.env.TOKEN_ENDPOINT!;
    %s
    const relayed = await fetch(tokenEndpoint, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded", authorization: request.headers.authorization }, body: "x" });
    return relayed;
  }
  if (!request.headers.authorization) return json(401, {});
  await verifier.verifyAuthorizationHeader(request.headers.authorization);
  return mcp.fetch(request);
}
'''


def _facade(tmp_path: Path, guard: str) -> Path:
    root = tmp_path / ("guarded" if guard else "open")
    (root / "src").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"name": "f", "dependencies": {"@modelcontextprotocol/server": "2.3.1"}}))
    (root / "src/handler.ts").write_text(FACADE % guard)
    return root


def test_f11_basic_client_auth_to_a_token_endpoint_is_not_an_error(run_script, tmp_path):
    guarded = _facade(tmp_path, 'if (!/^Basic [A-Za-z0-9+/=]+$/.test(request.headers.authorization ?? "")) return json(401, {});')
    doc = run_script(LINT_AUTH, guarded, "--json").json()
    finding = by_id(doc, "AUT021")[0]
    assert finding["severity"] == "info" and "Basic" in finding["message"]
    assert doc["summary"]["errors"] == 0


def test_f11_an_unchecked_relay_to_a_token_endpoint_is_a_qualified_warning(run_script, tmp_path):
    doc = run_script(LINT_AUTH, _facade(tmp_path, ""), "--json").json()
    finding = by_id(doc, "AUT021")[0]
    assert finding["severity"] == "warn" and "^Basic " in finding["message"]


def test_f11_bearer_passthrough_is_still_an_error(run_script, tmp_path):
    root = tmp_path / "relay"
    (root / "src").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"name": "r", "dependencies": {"@modelcontextprotocol/server": "2.3.1"}}))
    (root / "src/handler.ts").write_text(
        "import { createMcpHandler } from '@modelcontextprotocol/server';\n"
        "import { jwtVerify } from 'jose';\n"
        "const h = createMcpHandler(f);\n"
        "export async function handle(request: Request & { headers: Record<string, string> }) {\n"
        "  await jwtVerify(request.headers.authorization, keys, { audience: 'x' });\n"
        "  await fetch('https://downstream.example/api', { headers: { authorization: request.headers.authorization } });\n"
        "  if (!request.headers.authorization) return new Response(null, { status: 401 });\n"
        "  return h.fetch(request);\n"
        "}\n")
    doc = run_script(LINT_AUTH, root, "--json").json()
    finding = by_id(doc, "AUT021")[0]
    assert finding["severity"] == "error" and "bearer access token" in finding["message"]


# -- F12: a public cache hint on server/discover ---------------------------------------

def test_f12_public_server_discover_is_not_mcp032(run_script, tmp_path):
    root = tmp_path / "hints"
    (root / "src").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"name": "h", "dependencies": {"@modelcontextprotocol/server": "2.3.1"}}))
    (root / "src/server.ts").write_text('''import { McpServer, createMcpHandler } from "@modelcontextprotocol/server";
import { CognitoJwtVerifier } from "./auth.js";
const v = new CognitoJwtVerifier({ resource: "x" });
const cacheHints = {
  "server/discover": { ttlMs: 300000, cacheScope: "public" },
  "tools/list": {
    ttlMs: 60000,
    cacheScope: "public",
  },
};
export const mcp = createMcpHandler(() => new McpServer({ name: "h", version: "1" }, { cacheHints }));
''')
    doc = run_script(LINT_SERVER, root, "--json").json()
    lines = [f["line"] for f in by_id(doc, "MCP032")]
    assert lines == [8]


# -- F21 / F22: Alexa+ account linking -----------------------------------------------

def test_f21_the_cli_reference_names_account_linking_and_scope_discovery(plugin_root):
    text = (plugin_root / "skills/mcp-alexa/references/alexa-ai-cli.md").read_text()
    assert "alexa-ai configure-account-linking --addon-id" in text
    assert "scopes_supported" in text and "ALX054" in text and "not named" in text


def test_f21_prm_scopes_against_the_alexa_scope_names(run_script, fixtures, tmp_path):
    common = ["--as-file", fixtures / "auth/as-good.json", "--endpoint", "https://mcp.bookshelf.example/mcp",
              "--alexa", "--json"]
    mixed = run_script(CHECK_PRM, "--prm-file", fixtures / "auth/prm-good.json", *common).json()
    assert by_id(mixed, "ALX054")[0]["severity"] == "info"
    empty = tmp_path / "prm.json"
    empty.write_text(json.dumps({"resource": "https://mcp.bookshelf.example/mcp",
                                 "authorization_servers": ["https://auth.bookshelf.example"]}))
    assert by_id(run_script(CHECK_PRM, "--prm-file", empty, *common).json(), "ALX054")[0]["severity"] == "warn"


def test_f22_issuer_versus_token_iss(run_script, fixtures, tmp_path):
    facade = tmp_path / "as.json"
    facade.write_text(json.dumps({
        "issuer": "https://alexa.example.test", "token_endpoint": "https://alexa.example.test/oauth2/token",
        "jwks_uri": "https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_X/.well-known/jwks.json",
        "code_challenge_methods_supported": ["S256"],
        "grant_types_supported": ["authorization_code", "client_credentials"]}))
    base = ["--prm-file", fixtures / "auth/prm-alexa-good.json", "--as-file", facade, "--alexa", "--json"]
    inferred = run_script(CHECK_PRM, *base).json()
    assert by_id(inferred, "ALX055")[0]["severity"] == "info"
    assert "AUT031" not in {f["id"] for f in inferred["findings"]}
    told = run_script(CHECK_PRM, *base, "--token-iss",
                      "https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_X").json()
    assert by_id(told, "ALX055")[0]["severity"] == "warn"
    generic = run_script(CHECK_PRM, "--prm-file", fixtures / "auth/prm-good.json", "--as-file", facade, "--json")
    assert "AUT031" in generic.ids() and "ALX055" not in generic.ids()


# -- review: references and facts -------------------------------------------------------

def test_result_type_rows_agree(plugin_root):
    text = (plugin_root / "skills/mcp-review/references/spec-2026-07-28.md").read_text()
    row6 = next(l for l in text.splitlines() if l.startswith("| 6 | Tasks moved"))
    row8 = next(l for l in text.splitlines() if l.startswith("| 8 | `resultType`"))
    assert "extension" in row6 and '"task"' in row6
    assert "`complete`" in row8 and "`input_required`" in row8 and '"task"' in row8
    assert "Extensions add their own" in row8


def test_every_verified_fact_row_names_a_full_url(plugin_root):
    path = plugin_root / ".dev" / "VERIFIED-FACTS.md"
    if not path.is_file():
        pytest.skip("the verified-facts ledger is maintainer working notes, not shipped")
    missing = []
    for line in path.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not line.startswith("|"):
            continue
        status = next((c for c in cells[1:] if re.fullmatch(r"V2?( \([a-z /]+\))?|V / conflict|V \(.*\)", c)), None)
        if status and not re.search(r"https?://|file://", cells[-1]):
            missing.append(line[:100])
    assert missing == []


def test_f09_live_probe_evidence_settles_a_guarded_challenge(run_script, project, tmp_path):
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps({"subject": "http://x/mcp", "discovered": {
        "tool_names": sorted(ALEXA_TOOLS), "latency": {},
        "auth": {"unauthenticated_status": 401, "www_authenticate": False}}}))
    doc = run_script(LINT_ALEXA, project("vault_alexa"), "--tools-from", probe, "--probe-report", probe,
                     "--json").json()
    alx050 = by_id(doc, "ALX050")[0]
    assert alx050["severity"] == "info" and "probed endpoint answered 401 without it" in alx050["message"]
