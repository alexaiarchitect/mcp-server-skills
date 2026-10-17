"""`plan_migration.py` and `apply_codemod.py`: plans read only, the codemod writes only with --apply."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mcp_server_skills.report import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE

PLAN = "skills/mcp-migrate/scripts/plan_migration.py"
APPLY = "skills/mcp-migrate/scripts/apply_codemod.py"


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_planning_writes_nothing_without_out(run_script, tmp_project):
    root = tmp_project("ts_v1_lambda")
    before = tree_hash(root)
    result = run_script(PLAN, root, "--json")
    assert result.returncode == EXIT_OK
    data = result.json()
    assert tree_hash(root) == before
    steps = {s["id"]: s for s in data["discovered"]["steps"]}
    assert steps["TS03"]["auto"] is False and steps["TS01"]["auto"] is True
    assert data["discovered"]["mode"] == "dual"
    assert "plan" in data["discovered"], "--json without --out carries the plan inline"
    assert "MIG001" in {f["id"] for f in data["findings"]}


def test_dry_run_names_the_plan_file_without_writing_it(run_script, tmp_project, tmp_path):
    root = tmp_project("ts_v1_lambda")
    out = tmp_path / "plan.json"
    data = run_script(PLAN, root, "--out", out, "--dry-run", "--json").json()
    assert data["discovered"]["would_save"] == str(out) and not out.exists()


def test_the_full_flow_plan_diff_apply_rereview(run_script, tmp_project, tmp_path):
    root = tmp_project("ts_v1_lambda")
    plan = tmp_path / "plan.json"
    assert run_script(PLAN, root, "--out", plan).returncode == EXIT_OK
    before = tree_hash(root)

    dry = run_script(APPLY, root, "--plan", plan, "--json")
    assert dry.returncode == EXIT_OK
    data = dry.json()
    assert tree_hash(root) == before, "a dry run writes nothing"
    assert set(data["diffs"]) == {"pnpm-workspace.yaml", "apps/mcp-server/package.json",
                                  "apps/mcp-server/src/server.ts"}
    assert data["discovered"]["mode"].startswith("dry-run")

    md = run_script(APPLY, root, "--plan", plan, "--dry-run")
    assert "```diff" in md.stdout and "+import { McpServer } from \"@modelcontextprotocol/server\";" in md.stdout

    wet = run_script(APPLY, root, "--plan", plan, "--apply", "--json")
    assert wet.returncode == EXIT_OK
    assert sorted(wet.json()["discovered"]["written"]) == sorted(data["diffs"])
    pkg = json.loads((root / "apps/mcp-server/package.json").read_text())
    assert "@modelcontextprotocol/server" in pkg["dependencies"]
    assert "-32602" in (root / "apps/mcp-server/src/server.ts").read_text()

    review = run_script("skills/mcp-review/scripts/lint_server.py", root, "--json").json()
    ids = {f["id"] for f in review["findings"]}
    assert "MCP001" not in ids and "MCP050" not in ids
    assert "MCP011" in ids, "the guided serving step is still to do"


def test_apply_refuses_a_file_changed_after_planning(run_script, tmp_project, tmp_path):
    root = tmp_project("ts_v1_lambda")
    plan = tmp_path / "plan.json"
    run_script(PLAN, root, "--out", plan)
    target = root / "pnpm-workspace.yaml"
    target.write_text(target.read_text() + "# edited by a human\n")
    result = run_script(APPLY, root, "--plan", plan, "--apply", "--json")
    assert result.returncode == EXIT_FINDINGS
    assert "MIG002" in result.ids()
    assert "@modelcontextprotocol/sdk" in target.read_text(), "the refused file is untouched"


def test_apply_rejects_a_plan_for_another_project(run_script, tmp_project, tmp_path):
    root = tmp_project("ts_v1_lambda")
    other = tmp_project("py_v1_fastmcp")
    plan = tmp_path / "plan.json"
    run_script(PLAN, root, "--out", plan)
    assert run_script(APPLY, other, "--plan", plan).returncode == EXIT_USAGE
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    assert run_script(APPLY, root, "--plan", bad).returncode == EXIT_USAGE


def test_python_migration_and_modern_only(run_script, tmp_project, tmp_path):
    root = tmp_project("py_v1_fastmcp")
    data = run_script(PLAN, root, "--json").json()
    steps = {s["id"]: s for s in data["discovered"]["steps"]}
    assert {"PY01", "PY02", "PY03", "PY04", "PY05", "PY06", "PY07", "VERIFY"} <= set(steps)
    ts = run_script(PLAN, tmp_project("ts_v1_lambda"), "--modern-only", "--json").json()
    assert ts["discovered"]["mode"] == "modern-only"


def test_several_servers_need_a_unit(run_script, tmp_path):
    for name in ("a", "b"):
        d = tmp_path / name
        d.mkdir()
        (d / "package.json").write_text('{"name": "%s", "dependencies": {"@modelcontextprotocol/sdk": "^1.20.0"}}' % name)
        (d / "i.ts").write_text("import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';\n")
    assert run_script(PLAN, tmp_path, "--json").returncode == EXIT_USAGE
    assert run_script(PLAN, tmp_path, "--unit", "a", "--json").returncode == EXIT_OK


def test_a_v2_server_has_nothing_blocking(run_script, project):
    data = run_script(PLAN, project("ts_v2"), "--json").json()
    assert "MIG003" in {f["id"] for f in data["findings"]}
