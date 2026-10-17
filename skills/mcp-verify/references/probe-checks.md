# What the probe sends, and what passes

All requests are POSTs to the MCP endpoint unless noted. No tool is ever
called. The token, when given, is sent as `Authorization: Bearer ...` and
never printed.

## 1. `server/discover` (modern)

```http
POST /mcp
Content-Type: application/json
Accept: application/json, text/event-stream
MCP-Protocol-Version: 2026-07-28
Mcp-Method: server/discover

{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{
  "io.modelcontextprotocol/protocolVersion":"2026-07-28",
  "io.modelcontextprotocol/clientInfo":{"name":"mcp-server-skills-probe","version":"0.1.0"},
  "io.modelcontextprotocol/clientCapabilities":{}}}}
```

| Passes when | Else |
|---|---|
| HTTP 200 with a `result` | `PRB010` (HTTP status and JSON-RPC error recorded); 401 → auth path |
| `supportedVersions` contains the target and `capabilities` is an object | `PRB011` |
| `resultType` is `complete` or `input_required` | `PRB030` |
| `ttlMs` and `cacheScope` (`public`/`private`) present | `PRB031` |
| `_meta["io.modelcontextprotocol/serverInfo"]` present (SHOULD) | `PRB032` (note) |
| answered as JSON | `PRB052` (note) when SSE |

## 2. `tools/list` (modern), twice

Same envelope, `Mcp-Method: tools/list`. Checks `resultType` and cache hints
(`PRB030`, `PRB031`), that every tool has an `inputSchema` object with
`"type": "object"` (`PRB034`), and that the second call lists the same names in
the same order (`PRB033`).

## 3. Header validation

| Request | Expected | Else |
|---|---|---|
| `tools/list` body with `Mcp-Method: prompts/list` | HTTP 400, JSON-RPC `-32020` | accepted → `PRB020`; other status/code → `PRB022` |
| `tools/list` without `Mcp-Method` | HTTP 400, `-32020` | accepted → `PRB021`; other → `PRB022` |

`Mcp-Name` mismatches are not probed: the methods that carry `Mcp-Name`
(`tools/call`, `resources/read`, `prompts/get`) could have side effects on a
server that fails to validate.

## 4. Legacy handshake (`--legacy`)

```json
{"jsonrpc":"2.0","id":7,"method":"initialize","params":{"protocolVersion":"2025-11-25",
 "capabilities":{},"clientInfo":{"name":"mcp-server-skills-probe","version":"0.1.0"}}}
```

then `notifications/initialized` (expects 202), then `tools/list` with
`MCP-Protocol-Version: <negotiated>` and `Mcp-Session-Id` if one was minted.
A failed `initialize` is `PRB012`; a failed listing `PRB013`.

## 5. Auth

Run when a token was given or discover answered 401: `tools/list` *without* a
token.

| Passes when | Else |
|---|---|
| HTTP 401 (when the server requires auth) | `PRB040` |
| `WWW-Authenticate: Bearer resource_metadata="..."` | `PRB041` |
| the PRM URL (from the challenge, else the RFC 9728 well-known paths) returns JSON with `resource` and `authorization_servers` | `PRB042` |

## 6. Latency

`--n` more rounds of discover and `tools/list` (and legacy `tools/list`),
timed from send to full body. Reported per method: `n`, `p50_ms`, `p95_ms`
(nearest rank), `max_ms`, transport `errors`. p95 above `--budget-ms` is
`PRB050` — a warning, an error under `--profile alexa`.

## 7. GET

`GET /mcp` with `Accept: text/event-stream`: a 2026-07-28 server answers 405,
and so does a v2 TypeScript server's stateless legacy path. Anything else is
`PRB051` (note).

## Output

The JSON report is the plugin's gap report with the probe data under
`discovered`: `url`, `target`, `profile`, `era`, `tools`, `checks[]`
(`check`, `ok`, `detail`), `auth`, `latency`, `budget_ms`.

---

Sources: https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http,
https://modelcontextprotocol.io/specification/2026-07-28/server/discover,
https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/caching,
https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization (read 2026-10-05).
