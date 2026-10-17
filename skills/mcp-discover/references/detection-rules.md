# Detection rules

How `discover.py` decides the era, the transports, the hosting and the auth
picture — so a surprising result can be explained rather than argued with.

## Reading without running

TypeScript and JavaScript are masked once: comments blanked, then string,
template and regex literal contents blanked, with every offset kept. Structural
patterns (`new WebStandardStreamableHTTPServerTransport(`, `registerTool(`)
are matched on the code mask, where a brace inside a string cannot unbalance
anything; literal values (`"/.well-known/oauth-protected-resource"`,
`"server/discover"`) are matched on the comment-free text. Python is parsed
with `ast`, comments blanked with `tokenize`. Nothing is imported or executed.

## Era

Evaluated per server, first match wins:

1. **Python**: `mcp` resolves to 2.x, or the code imports
   `mcp.server.mcpserver` → `dual` (the v2 SDK always serves both eras).
   `mcp` 1.x or `mcp.server.fastmcp` → `handshake`.
2. **TypeScript, v2 entry point** (`createMcpHandler(`, `serveStdio(`):
   `legacy: 'reject'` with no legacy branch (`isLegacyRequest`, a v1
   transport) → `stateless`; otherwise → `dual`.
3. **Hand-written discover**: a `"server/discover"` literal → `dual` if
   `"initialize"` or a v1 transport also appears, else `stateless`.
4. **v1 transport** (`StreamableHTTPServerTransport`,
   `WebStandardStreamableHTTPServerTransport`, `SSEServerTransport`,
   `StdioServerTransport`) or SDK major 1 → `handshake`.
5. Otherwise `unknown`.

A 1.x SDK at a recent minor is still `handshake`: the 2.x line is the one that
implements 2026-07-28.

## Transports

| Seen | Transport |
|---|---|
| `createMcpHandler`, `toNodeHandler`, `(Node|WebStandard)?StreamableHTTPServerTransport`; Python `run(transport="streamable-http"|"http")`, `streamable_http_app()` | `streamable-http` |
| `serveStdio`, `StdioServerTransport`; Python `run()` with no transport | `stdio` |
| `SSEServerTransport`; Python `run(transport="sse")`, `sse_app()` | `sse` (Deprecated) |

## Hosting

Code: `APIGatewayProxy*` types, an `aws-lambda` import, `export const handler`,
`streamifyResponse`, `Mangum(` → Lambda; `express()`, `new Hono`, `fastify(`,
`createServer(`, a default export with `fetch`, `FastAPI(`, `Starlette(`,
`uvicorn.run(`. Files: Serverless, SAM, CDK, Terragrunt, Terraform with
`aws_lambda_function`, Dockerfile, Wrangler, Vercel, Fly, AgentCore configs.
Hosting matters twice later: Lambda cold starts count against the Alexa+
500 ms budget, and a custom router in front of the SDK needs its own header
validation.

## Auth

Signals are collected from the server **and** the `workspace:*` packages it
depends on, because a monorepo keeps its verifier and its metadata builder in a
shared package. A finding cites the file where the signal was seen.

## Known blind spots

- Values built at run time (`registerTool(name, ...)` in a loop over config)
  are reported as expressions, not names.
- A server assembled from several packages, each registering tools on a
  shared instance, is reported per package that imports the SDK.
- Generated code under `dist/` is skipped; if only `dist/` exists, discovery
  finds nothing — point it at the sources.

---

Sources: https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning
(eras), https://ts.sdk.modelcontextprotocol.io/v2/api/@modelcontextprotocol/server/server/createMcpHandler.html
(`legacy` option), https://py.sdk.modelcontextprotocol.io/run/legacy-clients/
(Python serves both eras, read 2026-10-05); this plugin's `inventory.py`.
