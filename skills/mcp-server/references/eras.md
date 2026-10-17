# Protocol eras: handshake, stateless, dual

Revision 2026-07-28 changed how a client and a server agree on what they speak.
The specification names the two sides **legacy** (2025-11-25 and earlier: an
`initialize` handshake opens a session) and **modern** (2026-07-28: every
request carries its version and capabilities in `_meta`). An implementation
that supports both is **dual-era**. Discovery reports which one the *code*
implements, as one of four values.

## The four values `discover.py` reports

| Era | What the code does | Who can connect |
|---|---|---|
| `handshake` | a 1.x transport (`StreamableHTTPServerTransport`, `WebStandardStreamableHTTPServerTransport`, `StdioServerTransport`, FastMCP 1.x) | 2025-era clients only. A modern client's first request lacks the handshake and is refused |
| `stateless` | modern only: `createMcpHandler(f, { legacy: 'reject' })`, or a hand-written `server/discover` without `initialize` | 2026-07-28 clients only. Legacy clients — Alexa+ today — have no fall-forward |
| `dual` | `createMcpHandler(f)` (default `legacy: 'stateless'`), `serveStdio`, Python `mcp` 2.x, or an explicit split on `isLegacyRequest` | both |
| `unknown` | no serving entry point recognised | review by hand |

## What a modern request looks like

```http
POST /mcp
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tools/call
Mcp-Name: search_books

{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_books","arguments":{...},
 "_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28",
          "io.modelcontextprotocol/clientCapabilities":{}}}}
```

The server must reject a header/body disagreement with HTTP 400 and JSON-RPC
`-32020` (HeaderMismatch); an unsupported version with 400 and `-32022`
listing `supported`; a missing required `_meta` field with 400 and `-32602`.
Every result carries `resultType`; discover, list and read results carry
`ttlMs` and `cacheScope`.

## How a dual-era client finds out

On Streamable HTTP it sends a modern request first. A recognised modern error
body means "modern server, retry with a supported version"; anything else (an
empty 400, a 404 or 405 without a modern error) means legacy, and it falls back
to `initialize`. On stdio it sends `server/discover` first. The result is
cached per origin (HTTP) or per process (stdio).

## What the SDKs do

- **TypeScript v2** (`@modelcontextprotocol/server` 2.x): `createMcpHandler(factory,
  { legacy })` with `legacy: 'stateless'` (default) answering 2025-era traffic
  from a fresh instance per request — no sessions, so legacy GET and DELETE get
  405 — or `'reject'`. Nothing in v2 puts a 2026-07-28 byte on the wire unless
  the client asks for it.
- **Python v2** (`mcp` 2.x): `streamable_http_app()` routes by
  `MCP-Protocol-Version`; legacy clients get the `initialize` path with
  in-process sessions (sticky routing with several workers, or
  `stateless_http=True`). There is no option to turn either era off.

## Who needs which era

| Caller | Speaks |
|---|---|
| Alexa+ add-ons | 2025-11-25 (toolkit overview, read 2026-10-05) |
| Clients on TS SDK v2 with `versionNegotiation: { mode: 'auto' }` | probes modern, falls back |
| Clients on TS SDK v2 default | legacy handshake only, until they opt in |
| Python SDK v2 `Client` | `mode='auto'` by default |

Hence the default of this plugin: **dual**.

---

Sources: https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning,
https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http,
https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28,
https://ts.sdk.modelcontextprotocol.io/v2/serving/legacy-clients.html,
https://py.sdk.modelcontextprotocol.io/run/legacy-clients/,
https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-overview.html (all read 2026-10-05).
