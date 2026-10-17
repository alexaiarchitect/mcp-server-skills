# The migration plan file

`plan_migration.py --out plan.json` writes one JSON document, schema
`mcp-server-skills.migration-plan/1`. It is data so it can be reviewed, saved
next to the pull request, and replayed by `apply_codemod.py` exactly.

```json
{
  "schema": "mcp-server-skills.migration-plan/1",
  "project": "/abs/path/to/repo",
  "unit": "apps/mcp-server",
  "language": "typescript",
  "target": "2026-07-28",
  "mode": "dual",
  "created": "2026-10-05",
  "sdk": {"from": "1.29.0", "package": "@modelcontextprotocol/sdk"},
  "files": {"apps/mcp-server/package.json": "<sha256>", "pnpm-workspace.yaml": "<sha256>"},
  "steps": [
    {
      "id": "TS01", "title": "...", "kind": "deps", "auto": true,
      "why": "...", "findings": ["MCP001"], "files": ["..."],
      "edits": [{"path": "pnpm-workspace.yaml", "find": "<regex>", "replace": "...", "regex": true}],
      "before": "", "after": "", "reference": "skills/mcp-migrate/references/ts-v1-to-v2.md#packages",
      "commands": []
    }
  ]
}
```

## Fields

| Field | Meaning |
|---|---|
| `mode` | `dual` (default) or `modern-only` (`--modern-only`) |
| `files` | SHA-256 of every file a step names, at plan time |
| `steps[].kind` | `deps`, `imports`, `transport`, `results`, `errors`, `tools`, `mrtr`, `command`, `verify` |
| `steps[].auto` | true: `edits` are applied by `apply_codemod.py`; false: guided |
| `steps[].edits` | literal (`regex: false`) or regex replacements, applied in order |
| `steps[].before` / `after` | for guided steps: the user's current code and the target shape |
| `steps[].findings` | review ids the step addresses |
| `steps[].commands` | commands for `command` and `verify` steps, run only after confirmation |

## Step ids

| Id | Language | Auto | What |
|---|---|---|---|
| TS00 | ts | command | `npx @modelcontextprotocol/codemod@latest v1-to-v2 .` |
| TS01 | ts | yes | dependencies (package.json or pnpm catalog), ext-apps 2.x, zod >= 4.2 |
| TS02 | ts | yes | `McpServer` import path |
| TS03 | ts | guided | per-request transport → `createMcpHandler(factory)` |
| TS04 | ts | guided | `server.tool()` and raw shapes → `registerTool` + `z.object` |
| TS05 | ts | guided | sessions, `Mcp-Session-Id`, event store |
| TS06 | ts | yes | -32002 → -32602 |
| TS07 | ts | guided | cache hints |
| TS08 | ts | guided | server-initiated requests → `inputRequired` |
| TS09 | ts | guided | a custom router in front of the SDK |
| PY01 | py | yes | `mcp>=2.3,<3` |
| PY02 | py | yes | `FastMCP` → `MCPServer`, `mcp.server.fastmcp` → `mcp.server.mcpserver` |
| PY03 | py | guided | transport settings → `run()` / `streamable_http_app()` |
| PY04 | py | guided | `get_context()` → injected `ctx: Context` |
| PY05 | py | guided | `McpError` → `MCPError` |
| PY06 | py | yes | -32002 → -32602 |
| PY07 | py | guided | elicitation → `InputRequiredResult` |
| PY08 | py | guided | low-level decorators → constructor handlers |
| VERIFY | both | guided | build, test, re-review against the baseline, probe both eras |

## Guarantees of `apply_codemod.py`

1. Without `--apply` it writes nothing and prints the unified diff.
2. A file whose hash differs from `files[path]` is refused (`MIG002`) and none
   of its edits run.
3. An edit that no longer matches is skipped and listed, never forced.
4. Guided steps are listed (`MIG001`), never applied.
5. The plan must have been made for the same project root.

---

Sources: this plugin's `lib/mcp_server_skills/codemods.py`; step content from
https://ts.sdk.modelcontextprotocol.io/v2/migration/upgrade-to-v2.html and
https://py.sdk.modelcontextprotocol.io/migration/ (read 2026-10-05).
