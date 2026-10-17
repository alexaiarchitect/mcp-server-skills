"""`lint_auth.py`, `check_prm.py`, the Alexa+ scripts, the CI scripts and `check_spec.py`."""

from __future__ import annotations

import json
from pathlib import Path

from mcp_server_skills.report import EXIT_FINDINGS, EXIT_INCONCLUSIVE, EXIT_OK, EXIT_USAGE

LINT_AUTH = "skills/mcp-auth/scripts/lint_auth.py"
CHECK_PRM = "skills/mcp-auth/scripts/check_prm.py"
VALIDATE = "skills/mcp-alexa/scripts/validate_addon.py"
LINT_ALEXA = "skills/mcp-alexa/scripts/lint_alexa.py"
LOCK = "skills/mcp-alexa/scripts/tools_lock.py"
FRICTION = "skills/mcp-alexa/scripts/friction_log.py"
GEN = "skills/mcp-ci/scripts/gen_workflow.py"
LINT_WF = "skills/mcp-ci/scripts/lint_workflows.py"
SPEC = "skills/mcp-upgrade/scripts/check_spec.py"


# -- auth -------------------------------------------------------------------------

def test_auth_review_of_the_lambda_server(run_script, project):
    result = run_script(LINT_AUTH, project("ts_v1_lambda"), "--json")
    assert {"AUT011", "AUT012"} <= result.ids()
    assert "AUT002" not in result.ids(), "PRM is served (from the workspace auth package)"
    assert "AUT020" not in result.ids(), "jwtVerify is given an audience"
    unit = result.json()["discovered"]["units"][0]
    assert unit["protected_resource_metadata"] and unit["audience_checked"]


def test_auth_review_of_a_clean_v2_server_and_of_no_auth(run_script, project):
    assert run_script(LINT_AUTH, project("ts_v2"), "--json").ids() == set()
    assert run_script(LINT_AUTH, project("py_v2"), "--json").ids() == {"AUT001"}
    assert run_script(LINT_AUTH, project("ts_stdio"), "--json").ids() == set(), "stdio is out of scope"


def test_auth_static_rules_fire_on_their_triggers(run_script, tmp_path):
    (tmp_path / "package.json").write_text('{"name": "a", "dependencies": {"@modelcontextprotocol/server": "^2.3.1"}}')
    (tmp_path / "s.ts").write_text(
        "import { createMcpHandler } from '@modelcontextprotocol/server';\n"
        "import { decodeJwt, jwtVerify } from 'jose';\n"
        "const h = createMcpHandler(f);\n"
        "export async function handle(req: Request) {\n"
        "  const token = new URL(req.url).searchParams.get('access_token');\n"
        "  await jwtVerify(token, keys);\n"
        "  const claims = decodeJwt(token);\n"
        "  await fetch('https://downstream', { headers: { Authorization: req.headers.get('authorization') } });\n"
        "  if (!claims) return new Response(null, { status: 401 });\n"
        "  return h.fetch(req);\n"
        "}\n"
        "const asMeta = { path: '/.well-known/oauth-authorization-server', registration_endpoint: '/register',\n"
        "  scopes_supported: ['offline_access'] };\n")
    found = run_script(LINT_AUTH, tmp_path, "--json").ids()
    assert {"AUT002", "AUT010", "AUT020", "AUT021", "AUT022", "AUT023", "AUT030", "AUT031", "AUT040",
            "AUT041", "AUT051"} <= found


def test_check_prm_offline(run_script, fixtures):
    good = run_script(CHECK_PRM, "--prm-file", fixtures / "auth/prm-good.json", "--as-file",
                      fixtures / "auth/as-good.json", "--endpoint", "https://mcp.bookshelf.example/mcp", "--json")
    assert good.returncode == EXIT_OK and good.ids() == set()
    alexa = run_script(CHECK_PRM, "--prm-file", fixtures / "auth/prm-alexa-good.json", "--as-file",
                       fixtures / "auth/as-good.json", "--endpoint", "https://mcp.bookshelf.example/mcp",
                       "--alexa", "--json")
    assert alexa.returncode == EXIT_OK and alexa.ids() == set()
    bad = run_script(CHECK_PRM, "--prm-file", fixtures / "auth/prm-bad.json", "--as-file",
                     fixtures / "auth/as-cognito-like.json", "--endpoint", "https://mcp.bookshelf.example/mcp",
                     "--alexa", "--json")
    # Under --alexa, CIMD advice (AUT031) is not given: Alexa+ does not support CIMD (F22).
    assert {"AUT003", "AUT005", "AUT051", "AUT040", "AUT041", "ALX051"} <= bad.ids()
    assert "AUT031" not in bad.ids()
    assert bad.returncode == EXIT_FINDINGS
    assert run_script(CHECK_PRM).returncode == EXIT_USAGE


def test_check_prm_live_follows_the_discovery_chain(run_script, fake_server):
    url = fake_server("dual", token="t")
    result = run_script(CHECK_PRM, url, "--json", "--timeout", "5")
    data = result.json()
    assert data["discovered"]["prm_location"].endswith("/.well-known/oauth-protected-resource/mcp")
    assert data["discovered"]["as_location"].endswith("/.well-known/oauth-authorization-server/as")
    assert {"AUT030", "AUT041"} <= result.ids()
    assert run_script(CHECK_PRM, "http://127.0.0.1:9/mcp", "--json", "--timeout", "2").returncode == EXIT_INCONCLUSIVE


# -- Alexa+ --------------------------------------------------------------------------

def test_validate_addon(run_script, project, tmp_path):
    assert run_script(VALIDATE, project("addon_good"), "--json").returncode == EXIT_OK
    broken = run_script(VALIDATE, project("addon_broken") / "addon.json", "--json")
    assert broken.returncode == EXIT_FINDINGS and "ALX016" in broken.ids()
    mismatch = run_script(VALIDATE, project("addon_good"), "--endpoint", "https://other.example/mcp", "--json")
    assert mismatch.ids() == {"ALX021"}
    missing = run_script(VALIDATE, tmp_path, "--json")
    assert missing.returncode == EXIT_USAGE and missing.ids() == {"ALX001"}
    (tmp_path / "addon.json").write_text("{nope")
    assert run_script(VALIDATE, tmp_path, "--json").ids() == {"ALX002"}


def test_lint_alexa_overlay(run_script, project):
    result = run_script(LINT_ALEXA, project("ts_v1_lambda"), "--json")
    assert {"ALX001", "ALX031", "ALX032", "ALX040", "ALX041", "ALX042", "ALX043", "ALX050", "ALX053"} <= result.ids()
    stdio = run_script(LINT_ALEXA, project("ts_stdio"), "--no-addon", "--json").ids()
    assert "ALX061" in stdio


def test_lint_alexa_reads_latency_from_a_probe_report(run_script, project, tmp_path):
    report = {"subject": "https://x/mcp", "discovered": {"latency": {
        "tools/list": {"p50_ms": 300, "p95_ms": 820}, "server/discover": {"p50_ms": 90, "p95_ms": 140}}}}
    path = tmp_path / "probe.json"
    path.write_text(json.dumps(report))
    result = run_script(LINT_ALEXA, project("ts_v2"), "--probe-report", path, "--no-addon", "--json")
    alx030 = next(f for f in result.json()["findings"] if f["id"] == "ALX030")
    assert "tools/list" in alx030["message"] and "820" in alx030["message"]
    assert result.returncode == EXIT_FINDINGS
    assert "ALX031" not in result.ids()


def test_lint_alexa_flags_modern_only(run_script, tmp_path):
    (tmp_path / "package.json").write_text('{"name": "m", "dependencies": {"@modelcontextprotocol/server": "^2.3.1"}}')
    (tmp_path / "i.ts").write_text("import { createMcpHandler } from '@modelcontextprotocol/server';\n"
                                   "export default createMcpHandler(f, { legacy: 'reject' });\n")
    assert "ALX060" in run_script(LINT_ALEXA, tmp_path, "--no-addon", "--json").ids()


def test_tools_lock_record_then_detect_change(run_script, tmp_project):
    root = tmp_project("ts_v2")
    dry = run_script(LOCK, root, "--dry-run", "--json")
    assert dry.returncode == EXIT_OK and not (root / "docs/alexa-tools.lock.json").exists()
    assert run_script(LOCK, root, "--write", "--json").returncode == EXIT_OK
    assert run_script(LOCK, root, "--json").json()["discovered"]["status"] == "unchanged"
    src = root / "src/server.ts"
    src.write_text(src.read_text().replace("zone: z.string().optional(), ", "zone: z.string(), floor: z.number(), "))
    changed = run_script(LOCK, root, "--json")
    assert changed.returncode == EXIT_FINDINGS and changed.ids() == {"ALX080"}
    assert "ALX080" in run_script(LINT_ALEXA, root, "--no-addon", "--json").ids()


def test_friction_log_appends_rows_and_escapes(run_script, tmp_path):
    args = ["--area", "alexa", "--step", "account linking", "--expected", "401 | challenge",
            "--actual", "simulator\nrejected", "--severity", "major", "--link", "https://x"]
    dry = run_script(FRICTION, tmp_path, *args, "--dry-run", "--json")
    assert dry.json()["written"] is False and not (tmp_path / "docs/FRICTION-LOG.md").exists()
    assert run_script(FRICTION, tmp_path, *args, "--date", "2026-10-05").returncode == EXIT_OK
    run_script(FRICTION, tmp_path, "--area", "latency", "--step", "probe", "--expected", "<500",
               "--actual", "820", "--date", "2026-10-05")
    text = (tmp_path / "docs/FRICTION-LOG.md").read_text()
    assert text.startswith("# Friction log")
    rows = [l for l in text.splitlines() if l.startswith("| 2026-10-05")]
    assert len(rows) == 2
    assert "401 \\| challenge" in rows[0] and "simulator<br>rejected" in rows[0]


# -- CI -------------------------------------------------------------------------------

def test_gen_workflow_dry_run_write_and_lint(run_script, tmp_project):
    root = tmp_project("ts_v1_lambda")
    before = run_script(LINT_WF, root, "--json")
    assert {"CI001", "CI002"} <= before.ids()
    dry = run_script(GEN, root, "--dry-run", "--json")
    assert not (root / ".github/workflows/mcp-conformance.yml").exists()
    content = dry.json()["content"]
    assert 'lint_server.py "apps/mcp-server"' in content and "exit $code" in content
    assert "${{ secrets.MCP_TOKEN }}" in content and "--branch \"$MCP_SKILLS_REF\"" in content
    assert run_script(GEN, root, "--alexa").returncode == EXIT_OK
    wf = (root / ".github/workflows/mcp-conformance.yml").read_text()
    assert "validate_addon.py" in wf and "--profile alexa" in wf
    after = run_script(LINT_WF, root, "--json")
    assert after.ids() == set() and after.returncode == EXIT_OK
    assert run_script(GEN, root).returncode == EXIT_FINDINGS, "refuses to overwrite without --force"
    assert run_script(GEN, root, "--force").returncode == EXIT_OK


def test_lint_workflows_catches_bad_gates(run_script, tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "bad.yml").write_text(
        "jobs:\n  x:\n    steps:\n"
        "      - run: git clone --depth 1 https://github.com/alexaiarchitect/mcp-server-skills .mcp-skills\n"
        "      - run: python3 .mcp-skills/skills/mcp-review/scripts/lint_server.py . || true\n"
        "      - run: python3 .mcp-skills/skills/mcp-verify/scripts/probe.py https://x --token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0\n")
    found = run_script(LINT_WF, tmp_path, "--json").ids()
    assert {"CI003", "CI004", "CI005"} <= found


# -- upgrade --------------------------------------------------------------------------

def test_check_spec_up_to_date(run_script, fixtures, tmp_path):
    result = run_script(SPEC, tmp_path, "--page-file", fixtures / "spec/versioning-2026-07-28.md", "--json")
    assert result.returncode == EXIT_OK
    assert result.json()["discovered"]["live"] == "2026-07-28" and result.ids() == set()


def test_check_spec_newer_revision_writes_a_delta(run_script, fixtures, tmp_path):
    (tmp_path / ".mcp-spec-pin").write_text("2026-07-28\n")
    out = tmp_path / "docs"
    dry = run_script(SPEC, tmp_path, "--page-file", fixtures / "spec/versioning-synthetic-newer.html",
                     "--sdk-file", fixtures / "spec/sdk-versions-newer.json", "--write-delta", out,
                     "--dry-run", "--date", "2027-04-01", "--json")
    assert dry.returncode == EXIT_FINDINGS
    assert {"UPG001", "UPG003"} <= dry.ids()
    assert not out.exists() and "2026-07-28 -> 2027-03-30" in dry.json()["discovered"]["delta"]
    assert dry.json()["discovered"]["pin_source"].endswith(".mcp-spec-pin")
    wet = run_script(SPEC, tmp_path, "--page-file", fixtures / "spec/versioning-synthetic-newer.html",
                     "--write-delta", out, "--date", "2027-04-01", "--json")
    assert (out / "delta-2027-04-01.md").is_file() and wet.returncode == EXIT_FINDINGS


def test_check_spec_inconclusive_and_bad_pins(run_script, fixtures, tmp_path):
    unread = run_script(SPEC, tmp_path, "--page-file", fixtures / "spec/versioning-unparseable.html", "--json")
    assert unread.returncode == EXIT_INCONCLUSIVE and unread.ids() == {"UPG002"}
    odd = run_script(SPEC, tmp_path, "--pinned", "2026-01-01", "--page-file",
                     fixtures / "spec/versioning-2026-07-28.md", "--json")
    assert "UPG004" in odd.ids()
    assert run_script(SPEC, tmp_path, "--pinned", "latest").returncode == EXIT_USAGE


def test_check_spec_offline_page_url_is_not_fetched_when_a_file_is_given(run_script, fixtures, tmp_path):
    result = run_script(SPEC, tmp_path, "--page-file", fixtures / "spec/versioning-2026-07-28.md",
                        "--url", "http://127.0.0.1:9/never", "--json")
    assert result.returncode == EXIT_OK
    assert Path(result.json()["discovered"]["source"]).name == "versioning-2026-07-28.md"
