"""The TypeScript reader: masks keep offsets, ignore comments and strings, and extract MCP registrations."""

from __future__ import annotations

from mcp_server_skills import ts_scan

SOURCE = '''
// server.registerTool("commented_out", {});
const s = "registerTool(\\"in_a_string\\", {})";
const t = `template ${ok ? "{" : "}"} still balanced`;
const r = /registerTool\\(/g;
server.registerTool(
  "search_books",
  {
    description: "Use this when " + "a reader asks.",
    inputSchema: z.object({ query: z.string(), limit: z.number().max(25).optional() }),
    _meta: { securitySchemes: [{ type: "oauth2", scopes: ["books.read"] }], ui: { resourceUri: "ui://x" } }
  },
  async () => ({ content: [] })
);
server.tool("old", "Old style", { isbn: z.string() }, async () => ({}));
for (const [k, v] of Object.entries(map)) {
  server.registerTool(`dyn_${k}`, { inputSchema: z.object({}) }, async () => ({}));
}
if (options.auth) {
  server.registerTool("admin_only", { description: "x", inputSchema: { type: "object", properties: { a: {} } } }, h);
}
'''


def test_masks_keep_every_offset_and_blank_comments_and_literals():
    m = ts_scan.mask(SOURCE)
    assert len(m.code) == len(m.text) == len(m.nocomment)
    assert "commented_out" not in m.nocomment
    assert "in_a_string" in m.nocomment and "in_a_string" not in m.code
    assert m.code.count("\n") == m.text.count("\n")


def test_registrations_are_found_only_in_code():
    tools = ts_scan.extract_tools(ts_scan.mask(SOURCE), "server.ts")
    names = [t.name for t in tools]
    assert "commented_out" not in names and "in_a_string" not in names
    assert {"search_books", "old", "admin_only"} <= set(names)


def test_register_tool_details():
    tools = {t.name: t for t in ts_scan.extract_tools(ts_scan.mask(SOURCE), "server.ts")}
    tool = tools["search_books"]
    assert tool.description == "Use this when a reader asks."
    assert tool.schema_kind == "zod-object"
    assert tool.params == ["query", "limit"]
    assert tool.list_limit_max == 25
    assert tool.security is True
    assert tool.ui_resource == "ui://x"
    assert tool.line == 6


def test_variadic_tool_is_a_raw_shape():
    tools = {t.name: t for t in ts_scan.extract_tools(ts_scan.mask(SOURCE), "server.ts")}
    assert tools["old"].api == "tool-variadic"
    assert tools["old"].schema_kind == "raw-shape"
    assert tools["old"].description == "Old style"


def test_loops_and_conditions_are_noticed():
    tools = ts_scan.extract_tools(ts_scan.mask(SOURCE), "server.ts")
    dynamic = next(t for t in tools if t.name_kind == "expr")
    assert dynamic.in_loop is True
    admin = next(t for t in tools if t.name == "admin_only")
    assert admin.conditional is True and admin.schema_kind == "json"


def test_imports_are_read_including_multiline_and_type_only():
    m = ts_scan.mask('import {\n  a,\n  type B\n} from "@modelcontextprotocol/sdk/server/mcp.js";\n'
                     'import type { C } from "x";\nconst d = await import("y");\n')
    mods = {i.module: i for i in ts_scan.imports(m)}
    assert set(mods) == {"@modelcontextprotocol/sdk/server/mcp.js", "x", "y"}
    assert mods["@modelcontextprotocol/sdk/server/mcp.js"].names == ["a", "B"]
    assert mods["x"].type_only is True


def test_object_entries_and_string_values():
    m = ts_scan.mask('f({ a: 1, "b-c": "two", ...rest, d, e() { return 1 } })')
    call = ts_scan.calls(m, "f")[0]
    entries = ts_scan.object_entries(m, *call.args[0])
    assert set(entries) == {"a", "b-c", "...", "d", "e"}
    assert ts_scan.string_value(m, *entries["b-c"]) == "two"
    assert ts_scan.string_value(m, *entries["a"]) is None


def test_app_resources_and_prompts():
    m = ts_scan.mask('registerAppResource(server, "Card", CARD_URI, cfg, cb);\n'
                     'server.registerResource("config", "config://app", {}, cb);\n'
                     'server.registerPrompt("summarise", {}, cb);\n')
    resources = ts_scan.extract_resources(m, "a.ts")
    assert [(r.name, r.uri, r.app) for r in resources] == [("Card", "CARD_URI", True),
                                                          ("config", "config://app", False)]
    assert [p.name for p in ts_scan.extract_prompts(m, "a.ts")] == ["summarise"]


def test_unterminated_input_does_not_crash():
    m = ts_scan.mask('server.registerTool("x", { description: "unterminated')
    assert ts_scan.extract_tools(m, "x.ts") == []
