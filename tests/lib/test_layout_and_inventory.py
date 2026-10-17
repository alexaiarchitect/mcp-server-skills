"""Layout detection and the inventory: units, catalogs, workspace packages, eras."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_server_skills import inventory, layout


def test_pnpm_catalog_and_workspace_packages_are_resolved(project):
    lay = layout.detect(project("ts_v1_lambda"))
    assert len(lay.units) == 1
    unit = lay.units[0]
    assert unit.path.name == "mcp-server"
    sdk = unit.dep("@modelcontextprotocol/sdk")
    assert (sdk.declared, sdk.resolved, sdk.major) == ("catalog:", "1.29.0", 1)
    assert sdk.source.endswith("pnpm-workspace.yaml")
    assert [p.name for p in unit.workspace_deps] == ["auth"]
    assert [p.name for p in unit.test_sources] == ["server.test.ts"]
    assert lay.node_version == "24.15.0"
    assert any("terraform" in k for k in lay.hosting_files)
    assert [w.name for w in lay.workflows] == ["ci.yml"]


def test_named_catalogs(tmp_path):
    (tmp_path / "pnpm-workspace.yaml").write_text(
        "catalog:\n  zod: 4.3.6\ncatalogs:\n  mcp2:\n    '@modelcontextprotocol/server': 2.3.1\n")
    cats = layout.pnpm_catalogs(tmp_path / "pnpm-workspace.yaml")
    assert cats["default"]["zod"] == "4.3.6"
    assert cats["mcp2"]["@modelcontextprotocol/server"] == "2.3.1"


def test_python_requirements_are_read(project):
    unit = layout.detect(project("py_v1_fastmcp")).units[0]
    dep = unit.dep("mcp")
    assert (dep.declared, dep.resolved, dep.major) == (">=1.9.0", "1.9.0", 1)
    assert unit.language == "python"


def test_a_directory_without_mcp_has_no_units(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "x", "dependencies": {"express": "^5"}}')
    (tmp_path / "index.js").write_text("console.log('hi')\n")
    assert layout.detect(tmp_path).units == []


@pytest.mark.parametrize("name,era,transports", [
    ("ts_v1_lambda", "handshake", ["streamable-http"]),
    ("ts_v2", "dual", ["streamable-http"]),
    ("ts_stdio", "handshake", ["stdio"]),
    ("py_v1_fastmcp", "handshake", ["streamable-http"]),
    ("py_v2", "dual", ["streamable-http"]),
])
def test_era_and_transport_per_fixture(project, name, era, transports):
    inv = inventory.build(project(name))
    unit = inv.units[0]
    assert unit.era == era
    assert unit.transports == transports


def test_modern_only_and_split_routing_eras(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "m", "dependencies": {"@modelcontextprotocol/server": "^2.3.1"}}')
    src = tmp_path / "index.ts"
    src.write_text("import { createMcpHandler } from '@modelcontextprotocol/server';\n"
                   "export default createMcpHandler(f, { legacy: 'reject' });\n")
    assert inventory.build(tmp_path).units[0].era == "stateless"
    src.write_text(src.read_text() + "if (await isLegacyRequest(req)) return old(req);\n")
    assert inventory.build(tmp_path).units[0].era == "dual"


def test_lambda_auth_and_extensions_are_summarised(project):
    unit = inventory.build(project("ts_v1_lambda")).units[0]
    assert "aws-lambda" in unit.hosting
    assert unit.auth["protected_resource_metadata"] is True, "PRM lives in the workspace auth package"
    assert unit.auth["audience_checked"] is True
    assert unit.extensions["apps"] is True
    assert {t.name for t in unit.tools} == {"search_books", "get_book", "prepare_loan"}


def test_select_by_name_and_path(project):
    inv = inventory.build(project("ts_v1_lambda"))
    assert inventory.select(inv, "@bookshelf/mcp-server") == inv.units
    assert inventory.select(inv, "apps/mcp-server") == inv.units
    assert inventory.select(inv, "nope") == []


def test_import_lines_are_not_code_hits(project):
    unit = inventory.build(project("ts_v1_lambda")).units[0]
    hits = unit.code_hits("ts.webstandard_transport")
    assert all(not unit.in_import(*h) for h in hits)
    assert Path(hits[0][0]).name == "handler.ts"
