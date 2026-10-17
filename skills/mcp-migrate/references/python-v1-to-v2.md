# Python: `mcp` 1.x to 2.x, dual-version

`mcp` 2.0.0 shipped on 2026-07-28; 2.3.0 is current (2026-10-02); the last 1.x
release is 1.30.0. v2 serves both eras from one app with no switch to turn
either off: requests naming `2026-07-28` in `MCP-Protocol-Version` go to the
modern handler, older clients get the `initialize` path. Python 3.10+.

## Dependency

Plan step `PY01` (auto): `mcp>=1.x` → `mcp>=2.3,<3` in `requirements*.txt` or
`pyproject.toml`. v2 also changes transitive dependencies: `httpx` →
`httpx2`, `sse-starlette` >= 3, `pydantic` >= 2.12, exact-pinned `mcp-types`,
`opentelemetry-api` on by default.

## Imports

Plan step `PY02` (auto):

```python
# v1
from mcp.server.fastmcp import FastMCP, Context
mcp = FastMCP("Demo")
# v2
from mcp.server.mcpserver import MCPServer, Context
mcp = MCPServer("Demo")
```

Every `mcp.server.fastmcp.*` submodule moved to `mcp.server.mcpserver.*`; the
old import raises `ModuleNotFoundError`. `mcp.types` still works (it mirrors
the standalone `mcp_types`). Python attributes are snake_case
(`input_schema`, `is_error`, `next_cursor`, `mime_type`); the wire stays
camelCase.

## Transport

Plan step `PY03` (guided): transport settings leave the constructor.

```python
# v1
mcp = FastMCP("Demo", port=9000, stateless_http=True, json_response=True)
# v2
mcp = MCPServer("Demo")
mcp.run(transport="streamable-http", port=9000)
# or, to mount in Starlette / FastAPI / a Lambda adapter:
app = mcp.streamable_http_app(json_response=True, stateless_http=True)
```

Legacy sessions are in-process: with several workers, either sticky routing or
`stateless_http=True`, which gives legacy clients throwaway per-request
sessions and no back-channel (`ctx.elicit()` then fails on the legacy leg).
`stateless_http` has no effect on modern connections, which are sessionless.
Session limits: `session_idle_timeout` (1800 s), `max_sessions` (10 000).

## Context

Plan step `PY04` (guided): `mcp.get_context()` is gone; declare the context.

```python
@mcp.tool()
def my_tool(x: int, ctx: Context) -> str:
    return str(x)
```

Sync handlers run on worker threads.

## Errors

Plan steps `PY05` (guided) and `PY06` (auto): `McpError` → `MCPError(code,
message, data=None)`; raising it now produces a JSON-RPC error rather than a
`CallToolResult(is_error=True)` — raise `ToolError` for tool execution
failures the model should see. A missing resource is -32602 with the `uri` in
`data`; replace hand-written -32002.

## MRTR

Plan step `PY07` (guided). On 2026-07-28 connections there is no back-channel
(`NoBackChannelError`); a tool that needs input returns an
`InputRequiredResult`; legacy connections still use `ctx.elicit()`. Handlers
written with `Resolve(...)` dependencies serve both eras from one function.

```python
@mcp.tool()
async def multi_step_tool(ctx: Context) -> InputRequiredResult | CallToolResult:
    if not has_input:
        return InputRequiredResult(input_schema={...})
    return CallToolResult(content=[...])
```

## Lowlevel

Plan step `PY08` (guided): the low-level `Server` takes handlers as
constructor parameters (`Server("name", on_list_tools=handle_list_tools)`)
instead of decorators, and returns exact protocol types — no implicit
wrapping. Union types use adapters (`client_request_adapter.validate_python`)
instead of `RootModel.root`.

## What stays the same

Decorated tools derive their input schema from type hints, so a typed
signature is the schema. Untyped parameters produce an uninformative schema
(`MCP060` as a note).

---

Sources: https://py.sdk.modelcontextprotocol.io/migration/,
https://py.sdk.modelcontextprotocol.io/run/,
https://py.sdk.modelcontextprotocol.io/run/legacy-clients/,
https://pypi.org/project/mcp/ (release history; all read 2026-10-05).
