"""The Python reader: SDK API detection, decorator registrations, transports, calls."""

from __future__ import annotations

from pathlib import Path

from mcp_server_skills import py_scan


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "server.py"
    path.write_text(text)
    return path


def test_v1_fastmcp_is_recognised_with_its_tools(project):
    facts = py_scan.scan(project("py_v1_fastmcp") / "server.py")
    assert facts.sdk_api == "fastmcp-v1"
    assert facts.server_vars == {"mcp": "FastMCP"}
    assert set(facts.constructor_kwargs["mcp"]) >= {"port", "stateless_http", "json_response"}
    assert ("streamable-http", facts.run_transports[0][1]) == facts.run_transports[0]
    tools = {t.name: t for t in facts.tools}
    assert set(tools) == {"search_catalogue", "reserve", "debug_dump"}
    assert tools["reserve"].params == ["isbn"], "the Context parameter is not a tool argument"
    assert tools["debug_dump"].has_input_schema is False
    assert [r.uri for r in facts.resources] == ["book://{isbn}"]
    assert (-32002, 43) in facts.int_literals or any(v == -32002 for v, _ in facts.int_literals)


def test_v2_mcpserver_is_recognised(project):
    facts = py_scan.scan(project("py_v2") / "server.py")
    assert facts.sdk_api == "mcpserver-v2"
    assert facts.http_apps and facts.http_apps[0][0] == "streamable_http_app"


def test_third_party_fastmcp_and_lowlevel(tmp_path):
    assert py_scan.scan(write(tmp_path, "from fastmcp import FastMCP\nmcp = FastMCP('x')\n")).sdk_api == \
        "fastmcp-thirdparty"
    assert py_scan.scan(write(tmp_path, "from mcp.server.lowlevel import Server\ns = Server('x')\n")).sdk_api == \
        "lowlevel"


def test_comments_are_blanked_but_offsets_kept():
    text = "x = 1  # mcp-session-id here\ny = 'kept # not a comment'\n"
    stripped = py_scan.strip_comments(text)
    assert len(stripped) == len(text)
    assert "mcp-session-id" not in stripped and "kept # not a comment" in stripped


def test_syntax_errors_are_reported_not_raised(tmp_path):
    facts = py_scan.scan(write(tmp_path, "def broken(:\n"))
    assert facts.error and facts.error.startswith("line 1")


def test_untyped_parameters_and_limits(tmp_path):
    facts = py_scan.scan(write(tmp_path, (
        "from typing import Annotated\nfrom pydantic import Field\n"
        "from mcp.server.mcpserver import MCPServer\nmcp = MCPServer('x')\n"
        "@mcp.tool()\ndef find(q, limit: Annotated[int, Field(le=50)] = 5):\n    return q\n")))
    tool = facts.tools[0]
    assert tool.schema_kind == "derived-untyped"
    assert tool.list_limit_max == 50
