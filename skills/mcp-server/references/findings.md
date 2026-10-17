# Finding ids

Every id any script in this plugin can emit. Ids are stable across releases:
a skill may branch on them, a test asserts them, a user can grep for them.
Severity is the default; a few rules lower it in context (named in the table).
`lib/mcp_server_skills/catalog.py` is the machine-readable twin of this file,
and a hygiene test keeps them in step.

Severities: **error** — a client following the pinned revision cannot use the
server as intended, or a MUST is broken; **warn** — it works today but
misleads, is Deprecated, or breaks on a date; **info** — worth knowing.

## `DSC` — Discovery (`discover.py`, every script)

| Id | Severity | Trigger |
|---|---|---|
| `DSC001` | error | no MCP server found under the path |
| `DSC002` | info | several MCP servers found |
| `DSC003` | warn | SDK version could not be resolved |
| `DSC004` | info | third-party FastMCP package, not the official SDK |
| `DSC010` | warn | a source file could not be parsed |

## `MCP` — Protocol review (`lint_server.py`)

| Id | Severity | Trigger |
|---|---|---|
| `MCP001` | error | SDK major is behind the target revision |
| `MCP002` | info | SDK is older than the newest release of its major |
| `MCP003` | warn | v1 and v2 SDK packages imported side by side |
| `MCP004` | warn | MCP Apps package does not match the SDK major |
| `MCP005` | warn | zod older than the v2 TypeScript SDK accepts |
| `MCP006` | warn | Node.js older than the v2 TypeScript SDK supports |
| `MCP010` | warn | protocol-level sessions are used |
| `MCP011` | error | handshake-only transport: the server answers `initialize` and nothing modern |
| `MCP012` | error | `server/discover` is not served |
| `MCP013` | warn | legacy traffic is rejected (modern-only endpoint) |
| `MCP014` | info | an old protocol revision is written as a literal |
| `MCP015` | warn | custom HTTP routing in front of the SDK |
| `MCP020` | warn | `Mcp-Method` / `Mcp-Name` are not validated against the body |
| `MCP021` | info | a tool parameter is mirrored into a header with `x-mcp-header` |
| `MCP030` | warn | a hand-built JSON-RPC result has no `resultType` |
| `MCP031` | warn | cacheable results carry no deliberate `ttlMs` / `cacheScope` |
| `MCP032` | warn | `cacheScope: 'public'` on an authenticated server (not raised for `server/discover`, whose result is static server info) |
| `MCP040` | warn | a deprecated feature is used |
| `MCP041` | warn | a method removed by 2026-07-28 is implemented or called |
| `MCP042` | warn | SSE resumability (`Last-Event-ID`, event store) is configured |
| `MCP050` | warn | error code -32002 (resource not found) |
| `MCP051` | warn | draft error numbering |
| `MCP052` | error | an error code in the spec-reserved range that the spec does not define |
| `MCP060` | warn | a tool declares no `inputSchema` |
| `MCP061` | warn | `inputSchema` is a raw shape, not `z.object(...)` |
| `MCP062` | warn | tools are registered in a nondeterministic order |
| `MCP063` | warn | the tool list depends on the caller |
| `MCP064` | warn | a tool name does not follow the naming guidance |
| `MCP065` | error | two tools share a name |
| `MCP066` | warn | a tool has no description |
| `MCP067` | warn | deprecated variadic registration (`server.tool(...)`) |
| `MCP070` | warn | a server-initiated request needs MRTR |
| `MCP071` | info | unsolicited list-changed notifications |
| `MCP080` | error | a stdio server writes to stdout |
| `MCP081` | info | an HTTP server binds all interfaces |
| `MCP082` | warn | the deprecated HTTP+SSE transport is served |
| `MCP090` | warn | experimental core tasks from 2025-11-25 |
| `MCP091` | error | a tool points at a UI resource that is not registered |

## `AUT` — Authorization (`lint_auth.py`, `check_prm.py`)

| Id | Severity | Trigger |
|---|---|---|
| `AUT001` | warn | an HTTP server with no authorization at all |
| `AUT002` | error | no Protected Resource Metadata endpoint |
| `AUT003` | error | the PRM document lacks `resource` or `authorization_servers` |
| `AUT004` | info | PRM is served only at the root well-known path |
| `AUT005` | warn | PRM `resource` does not match the MCP endpoint |
| `AUT010` | warn | a 401 without `WWW-Authenticate: Bearer resource_metadata=...` |
| `AUT011` | warn | unauthenticated requests are served for some methods |
| `AUT012` | info | insufficient scope is not signalled with 403 `insufficient_scope` |
| `AUT020` | error | access tokens are not checked for audience / resource |
| `AUT021` | error | the incoming bearer token is passed through downstream (warn when relayed to a token endpoint without a `^Basic ` check; info for a façade relaying only `Basic` client authentication) |
| `AUT022` | error | a JWT is decoded without verification |
| `AUT023` | error | an access token is read from the query string |
| `AUT030` | warn | Dynamic Client Registration is offered or relied on |
| `AUT031` | info | no Client ID Metadata Document support advertised (not raised by `check_prm.py --alexa`: Alexa+ does not support CIMD) |
| `AUT040` | error | PKCE S256 is not advertised |
| `AUT041` | info | authorization responses are not marked as carrying `iss` |
| `AUT050` | info | tools declare no per-tool scopes |
| `AUT051` | warn | `offline_access` is advertised by the resource server |
| `AUT060` | error | PRM document could not be fetched |
| `AUT061` | error | authorization server metadata could not be fetched |

## `ALX` — Alexa+ overlay (`validate_addon.py`, `lint_alexa.py`, `tools_lock.py`)

| Id | Severity | Trigger |
|---|---|---|
| `ALX001` | warn | no `addon.json` |
| `ALX002` | error | `addon.json` is not valid JSON |
| `ALX003` | error | `manifestVersion` missing or not "1.0" |
| `ALX010` | error | `distributionCountries` missing or empty |
| `ALX011` | warn | a distribution country where the MCP toolkit is not documented as available |
| `ALX012` | error | no locale, or a malformed locale key |
| `ALX013` | error | add-on name missing or longer than 30 characters |
| `ALX014` | error | short description missing or longer than 123 characters |
| `ALX015` | error | full description missing or longer than 4000 characters |
| `ALX016` | error | example phrases: need 3-4 distinct phrases of at most 200 characters |
| `ALX017` | error | privacy policy or terms-of-use URL missing or not HTTPS |
| `ALX018` | error | a required light icon size is missing |
| `ALX019` | error | media asset problem (carousel, format, HTTPS, alt text) |
| `ALX020` | error | no HTTPS MCP endpoint in `integrations` |
| `ALX021` | warn | the add-on endpoint does not match the server's canonical URI |
| `ALX022` | warn | store metadata contains developer jargon |
| `ALX030` | error | measured latency is above the 500 ms round-trip budget |
| `ALX031` | info | no latency measurement yet |
| `ALX032` | info | Lambda hosting: cold starts count against the 500 ms budget |
| `ALX040` | warn | a tool description is not voice-shaped |
| `ALX041` | warn | a list-returning tool may present more than 5 options (passes with a `limit` bounded at 5, a server-side page size <= 5, or a page token and no `limit` input) |
| `ALX042` | info | a generic, API-shaped tool name |
| `ALX043` | warn | a tool depends on a UI with no voice path |
| `ALX050` | warn | 401 responses carry `WWW-Authenticate`, which Alexa+ lists as unsupported (info under `--profile alexa` when the header is sent only on a guarded branch) |
| `ALX051` | warn | authorization server metadata does not match the Alexa+ profile |
| `ALX052` | warn | relies on DCR, CIMD, OIDC or step-up, which Alexa+ does not support |
| `ALX053` | warn | unauthenticated requests are not all answered with 401 |
| `ALX054` | info | the scopes Alexa+ will request are ambiguous (warn when PRM lists none; `check_prm.py --alexa`) |
| `ALX055` | warn | the AS metadata `issuer` is not the `iss` the tokens carry (info when only inferred from `jwks_uri`) |
| `ALX060` | error | the server cannot serve 2025-11-25 clients |
| `ALX061` | error | no Streamable HTTP endpoint |
| `ALX080` | warn | tool signatures changed since the recorded lock |

## `PRB` — Live probe (`probe.py`)

| Id | Severity | Trigger |
|---|---|---|
| `PRB001` | error | the endpoint is unreachable |
| `PRB010` | error | `server/discover` failed |
| `PRB011` | error | the discover result is incomplete or omits the target revision |
| `PRB012` | error | legacy `initialize` failed |
| `PRB013` | error | legacy `tools/list` failed after `initialize` |
| `PRB020` | error | a header/body mismatch was accepted |
| `PRB021` | warn | a request without `Mcp-Method` was accepted |
| `PRB022` | warn | a header rejection used the wrong status or code |
| `PRB030` | error | a modern result has no `resultType` |
| `PRB031` | error | a cacheable result has no `ttlMs` / `cacheScope` |
| `PRB032` | info | results carry no `serverInfo` in `_meta` |
| `PRB033` | warn | `tools/list` order changed between calls |
| `PRB034` | error | a listed tool has no valid object `inputSchema` |
| `PRB040` | warn | an unauthenticated request was not answered with 401 |
| `PRB041` | warn | the 401 has no `resource_metadata` challenge (info under `--profile alexa` for a bare 401, citing ALX050) |
| `PRB042` | error | Protected Resource Metadata is not reachable or invalid |
| `PRB050` | warn | p95 latency is above the budget |
| `PRB051` | info | GET on the MCP endpoint is not answered with 405 |
| `PRB052` | info | the server returned SSE where JSON was enough |

## `MIG` — Migration (`plan_migration.py`, `apply_codemod.py`)

| Id | Severity | Trigger |
|---|---|---|
| `MIG001` | info | a step cannot be applied automatically |
| `MIG002` | error | a file changed since the plan was made |
| `MIG003` | info | nothing to migrate for this target |
| `MIG004` | info | a dependency bump needs peer dependencies installed beside it (warn when strict peer dependencies are on and peers were missing) |

## `CI` — Workflows (`lint_workflows.py`)

| Id | Severity | Trigger |
|---|---|---|
| `CI001` | warn | no workflow runs the MCP review |
| `CI002` | info | no workflow runs the live probe |
| `CI003` | error | a credential literal in a workflow |
| `CI004` | warn | an exit code is masked |
| `CI005` | warn | the plugin is fetched from an unpinned ref |

## `UPG` — Upgrade loop (`check_spec.py`)

| Id | Severity | Trigger |
|---|---|---|
| `UPG001` | warn | a newer protocol revision is current |
| `UPG002` | info | the live versioning page could not be read |
| `UPG003` | info | an SDK has a newer release than this plugin was checked against |
| `UPG004` | warn | the pinned revision is not a published revision |

Context-dependent severities: `MCP031` is a note for Python 2.x servers, whose
cache-hint setting this plugin has not verified; `MCP060` is a note when the
schema is derived from untyped Python parameters; `PRB050` is an error under
`probe.py --profile alexa`.

Sources: each id's `source` in `lib/mcp_server_skills/catalog.py`, chiefly
https://modelcontextprotocol.io/specification/2026-07-28/changelog,
https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization and
https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html (all read 2026-10-05).
