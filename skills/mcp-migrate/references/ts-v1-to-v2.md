# TypeScript: SDK v1 to v2, dual-version

v2 splits `@modelcontextprotocol/sdk` into `@modelcontextprotocol/server`,
`/client`, `/core`, framework adapters (`/node`, `/express`, `/hono`,
`/fastify`) and a frozen `/server-legacy`. v2 is "the stable release line
implementing the 2026-07-28 spec"; it needs Node.js 20+ and zod >= 4.2.0.
Versions on 2026-10-05: `@modelcontextprotocol/server` 2.3.1, `/node` 2.1.1,
`@modelcontextprotocol/ext-apps` 2.0.3 (peers on server ^2), v1 `sdk` 1.32.0.

## The official codemod

```bash
npx @modelcontextprotocol/codemod@latest v1-to-v2 .
grep -rn '@mcp-codemod-error' .        # what it could not do
npx tsc --noEmit
```

Run it at the package root first when npm is reachable (plan step `TS00`). It
rewrites imports and `package.json`. Both majors can coexist during a staged
migration, but objects must not flow between v1- and v2-imported code.

## Packages

Plan step `TS01` (auto): replace `@modelcontextprotocol/sdk` with
`@modelcontextprotocol/server` — in `package.json`, or in the pnpm catalog when
the dependency says `catalog:`; move `@modelcontextprotocol/ext-apps` to 2.x;
raise zod to 4.2.0 when below. Add `@modelcontextprotocol/node` for Express /
`node:http` hosting (`toNodeHandler`).

**Peers.** `@modelcontextprotocol/ext-apps` 2.0.3 declares
`peerDependencies` `@modelcontextprotocol/client` ^2.0.0,
`@modelcontextprotocol/core` ^2.0.0 and zod ^4.2.0 as **required**, and
`@modelcontextprotocol/server`, `react`, `react-dom` as optional
(`peerDependenciesMeta`). TS01 adds the missing required peers where the
dependency lives (catalog entry plus `"catalog:"` in package.json, or a
version range in package.json). It reads an installed 2.x copy's own
`package.json` when there is one, else the plugin's pinned table. When `.npmrc`
(or `pnpm-workspace.yaml`) sets `strict-peer-dependencies=true`, pnpm refuses
to install with a required peer missing; the plan says so (`MIG004`). Apply
TS01 whole, then install, then build.

## Imports

Plan step `TS02` (auto, the safe subset):

```ts
// before
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
// after
import { McpServer } from "@modelcontextprotocol/server";
```

Other renames the codemod handles: `McpError` → `ProtocolError`
(`ProtocolErrorCode`), `StreamableHTTPError` → `SdkHttpError`, OAuth error
classes → `OAuthError`; `setRequestHandler(CallToolRequestSchema, ...)` →
`setRequestHandler('tools/call', ...)`; handler `extra` → structured `ctx`
(`ctx.mcpReq.id`, `ctx.http?.req?.headers`).

## Serving: createMcpHandler

Plan step `TS03` (guided). v1's per-request pattern —

```ts
const server = createServer(options);
const transport = new WebStandardStreamableHTTPServerTransport({ enableJsonResponse: true });
await server.connect(transport);
const response = await transport.handleRequest(request);
await server.close();
```

— becomes a handler that builds a fresh `McpServer` from a factory for every
request:

```ts
import { createMcpHandler } from "@modelcontextprotocol/server";

const mcp = createMcpHandler(() => createServer(options), { responseMode: "json" });
const response = await mcp.fetch(request);           // web-standard Request -> Response
```

`createMcpHandler(factory, options)` returns `{ fetch, close, notify, bus }`.
Options: `legacy` (`"stateless"` default — answers 2025-era traffic per
request, no sessions, legacy GET/DELETE get 405 — or `"reject"`),
`responseMode` (`"auto"`, `"sse"`, `"json"`; it shapes **2026-07-28** exchanges
only), `maxRequestBodySize` (4 MiB),
`keepAliveMs`, `maxSubscriptions`, `onerror`, `bus`. It validates
`MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name` (and `Mcp-Param-*`) against
the body with 400 / -32020, answers `server/discover`, and emits `resultType`.

**Lambda.** Keep the API Gateway ↔ `Request`/`Response` conversion. First
step: create the handler *inside* the Lambda handler, so the factory still
closes over per-invocation values (verified auth context, telemetry
callbacks). Later, optionally: one module-level handler and auth passed as
`mcp.fetch(request, { authInfo })`, read in tools as `ctx.http.authInfo`.

**Node frameworks.** `app.all('/mcp', toNodeHandler(mcp))` with
`toNodeHandler` from `@modelcontextprotocol/node`.

**What the legacy leg puts on the wire.** Under the default `legacy:
'stateless'` each 2025-era POST is served by
`WebStandardStreamableHTTPServerTransport({ sessionIdGenerator: undefined })`
— no `enableJsonResponse` — so it is answered as `text/event-stream`, even
with `responseMode: 'json'`. A v1 server built with `enableJsonResponse: true`
answered `application/json`. On Lambda behind API Gateway the stream is
buffered into one response, so it still works, but the content type changes
for every 2025-era client (ChatGPT, Alexa+). To keep JSON, compose the legacy
leg yourself (the SDK documents this pattern on `isLegacyRequest`):

```ts
import { createMcpHandler, isLegacyRequest, WebStandardStreamableHTTPServerTransport }
  from "@modelcontextprotocol/server";

const modern = createMcpHandler(factory, { legacy: "reject", responseMode: "json" });

export async function serve(request: Request): Promise<Response> {
  if (await isLegacyRequest(request)) {          // classifies a clone; the body stays readable
    const server = await factory();
    const transport = new WebStandardStreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
      enableJsonResponse: true,
    });
    await server.connect(transport);
    try {
      return await transport.handleRequest(request);
    } finally {
      await server.close();
    }
  }
  return modern.fetch(request);
}
```

Hand-wired compositions must check `Content-Type` themselves before the
modern leg (`isJsonContentType`); the SDK transport checks it on the legacy
leg. `probe.py --legacy` reports which content type each era got (`PRB052`).

**Split routing** (keep a v1 stack for legacy): `createMcpHandler(f, { legacy:
'reject' })` for modern traffic and `isLegacyRequest(request)` to send the rest
to the existing handler.

## Tools

Plan step `TS04` (guided):

```ts
// v1
server.tool("greet", "Greet user", { name: z.string() }, handler);
// v2
server.registerTool("greet", { description: "Greet user", inputSchema: z.object({ name: z.string() }) }, handler);
```

Raw shapes are deprecated on registration; wrap them in `z.object()`.

## Sessions

Plan step `TS05` (guided): remove `sessionIdGenerator`, `Mcp-Session-Id`
handling and event stores. State that spans calls becomes an explicit handle
the server mints and the client passes as a tool argument.

## Errors

Plan step `TS06` (auto): -32002 (resource not found) → -32602. HeaderMismatch,
MissingRequiredClientCapability and UnsupportedProtocolVersion are -32020,
-32021, -32022; the SDK raises them.

## Cache hints

Plan step `TS07` (guided: the values are a decision). When serving
2026-07-28 the SDK always emits `ttlMs` and `cacheScope`, defaulting to
`ttlMs: 0` / `cacheScope: 'private'`. Set `ServerOptions.cacheHints` (per
operation) or `cacheHint` on a `registerResource` metadata object; a
per-resource hint wins field by field. The shape, from the SDK source
(`packages/server/src/server/server.ts`, `CACHEABLE_RESULT_METHODS` in
`packages/core-internal/src/shared/resultCacheHints.ts`, tag 2.3.1):

```ts
cacheHints?: Partial<Record<
  "tools/list" | "prompts/list" | "resources/list" | "resources/templates/list" | "resources/read" | "server/discover",
  { ttlMs?: number; cacheScope?: "public" | "private" }
>>;

new McpServer(info, {
  capabilities: { tools: {} },
  cacheHints: {
    "server/discover": { ttlMs: 300_000, cacheScope: "public" }, // static server info
    "tools/list": { ttlMs: 60_000, cacheScope: "private" },
  },
});
```

`ttlMs` must be a non-negative safe integer and `cacheScope` one of the two
values, or the constructor throws a `RangeError`. Use `public` only for
results identical for every caller: `server/discover` qualifies (the review
does not raise `MCP032` for it), a `tools/list` that varies by token does not.
Responses to 2025-era requests are never affected.

## MRTR

Plan step `TS08` (guided): server-to-client requests become returns.

```ts
// 2025 style
const answer = await ctx.mcpReq.elicitInput({ ... });
// 2026 style (also served to 2025-era clients through the SDK's shim)
return inputRequired({
  inputRequests: { id: inputRequired.elicit({ ... }) },
  requestState: await stateCodec.mint({ step: "phase1" })
});
// on retry
const state = ctx.mcpReq.requestState<PhaseState>();
const content = acceptedContent(ctx.mcpReq.inputResponses, "id", SCHEMA);
```

`createRequestStateCodec({ key, ttlSeconds })` HMAC-seals request state;
treat it as untrusted and verify on every retry.

## Custom routing

Plan step `TS09` (guided). A gate that parses the body to decide which methods
need a token sees both eras. Keep it for auth, decide per method on purpose
(Alexa+ expects 401 for every unauthenticated request), and leave 405s,
header validation and JSON-RPC error bodies to the handler.

---

Sources: https://ts.sdk.modelcontextprotocol.io/v2/migration/upgrade-to-v2.html,
https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28,
https://ts.sdk.modelcontextprotocol.io/v2/serving/web-standard.html,
https://ts.sdk.modelcontextprotocol.io/v2/serving/legacy-clients.html,
https://ts.sdk.modelcontextprotocol.io/v2/api/@modelcontextprotocol/server/server/createMcpHandler.html,
npm registry metadata for the packages named (all read 2026-10-05); the
TypeScript SDK source at tag 2.3.1 (https://github.com/modelcontextprotocol/typescript-sdk,
`packages/server/src/server/server.ts`, `packages/server/src/server/createMcpHandler.ts`,
`packages/core-internal/src/shared/resultCacheHints.ts`) and the published
`package.json` of `@modelcontextprotocol/ext-apps` 2.0.3 for the peers.
