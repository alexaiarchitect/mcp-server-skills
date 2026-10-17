"""The finding catalog: every id this plugin can emit, in one place.

Each entry carries a default severity, a one-line title, the fix and the page
the rule derives from. Scripts pass only the id and a specific message; the
rest comes from here, so `MCP011` means the same thing in the review, the
router summary and the migration plan. `skills/mcp-server/references/findings.md`
documents every id, and a hygiene test keeps the two in step.

Bands:

=====  ==========================================  =========================
DSC    discovery: what could not be determined     `discover.py`
MCP    protocol review against a pinned revision   `lint_server.py`
AUT    OAuth 2.1 resource-server review            `lint_auth.py`, `check_prm.py`
ALX    Alexa+ add-on readiness overlay             `validate_addon.py`, `lint_alexa.py`
PRB    live conformance probe                      `probe.py`
MIG    migration plan and codemods                 `plan_migration.py`, `apply_codemod.py`
CI     workflows                                   `lint_workflows.py`
UPG    upgrade loop                                `check_spec.py`
=====  ==========================================  =========================

Numbering is banded in decades by sub-area so new checks slot in without
renumbering. Ids are never reused.
"""

from __future__ import annotations

from dataclasses import dataclass

S = "https://modelcontextprotocol.io/specification/2026-07-28"
CHANGELOG = f"{S}/changelog"
VERSIONING = f"{S}/basic/versioning"
TRANSPORT = f"{S}/basic/transports/streamable-http"
BASIC = f"{S}/basic/index"
CACHING = f"{S}/server/utilities/caching"
DISCOVER = f"{S}/server/discover"
AUTHZ = f"{S}/basic/authorization"
DEPRECATED = f"{S}/deprecated"
TOOLS = f"{S}/server/tools"
TS_MIGRATE = "https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28"
TS_UPGRADE = "https://ts.sdk.modelcontextprotocol.io/v2/migration/upgrade-to-v2.html"
TS_HANDLER = ("https://ts.sdk.modelcontextprotocol.io/v2/api/@modelcontextprotocol/server/"
              "server/createMcpHandler.html")
PY_MIGRATE = "https://py.sdk.modelcontextprotocol.io/migration/"
PY_LEGACY = "https://py.sdk.modelcontextprotocol.io/run/legacy-clients/"
TASKS_EXT = "https://modelcontextprotocol.io/extensions/tasks/overview"
APPS_EXT = "https://modelcontextprotocol.io/extensions/apps/overview"
ALX_QUICK = "https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html"
ALX_FUNC = "https://developer.amazon.com/docs/alexaplus/add-ons/functional-requirements.html"
ALX_AUTH = "https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-authentication.html"
ALX_LINKING = "https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-account-linking.html"
ALX_OVERVIEW = "https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-overview.html"
ALX_DESIGN = "https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-design-guide.html"
ALX_STAGES = "https://developer.amazon.com/docs/alexaplus/add-ons/alexa-plus-add-on-development-stages.html"
PLUGIN = "https://github.com/alexaiarchitect/mcp-server-skills"


@dataclass(frozen=True)
class Entry:
    id: str
    severity: str
    area: str
    title: str
    fix: str
    source: str


def _e(id: str, severity: str, area: str, title: str, fix: str, source: str) -> Entry:
    return Entry(id, severity, area, title, fix, source)


_ENTRIES = [
    # -- DSC: discovery --------------------------------------------------
    _e("DSC001", "error", "discovery", "no MCP server found under the path",
       "Point the script at the package that imports an MCP SDK, or at the monorepo root.", PLUGIN),
    _e("DSC002", "info", "discovery", "several MCP servers found",
       "Name one with --unit, or review each in turn; findings are reported per unit.", PLUGIN),
    _e("DSC003", "warn", "discovery", "SDK version could not be resolved",
       "Pin the SDK in package.json, the pnpm catalog, pyproject.toml or requirements.txt; "
       "a review against an unknown version cannot say which era the server speaks.", PLUGIN),
    _e("DSC004", "info", "discovery", "third-party FastMCP package, not the official SDK",
       "`fastmcp` (PyPI) is a separate project; check its own release notes for 2026-07-28 support.",
       PY_MIGRATE),
    _e("DSC010", "warn", "discovery", "a source file could not be parsed",
       "Fix the syntax error; what the reader cannot parse it cannot review.", PLUGIN),

    # -- MCP00x: SDK -----------------------------------------------------
    _e("MCP001", "error", "sdk", "SDK major is behind the target revision",
       "Move to the v2 line (TypeScript `@modelcontextprotocol/server`, Python `mcp>=2`), which "
       "serves 2026-07-28 and still answers 2025-era clients. Plan it with /mcp-server:mcp-migrate.",
       TS_MIGRATE),
    _e("MCP002", "info", "sdk", "SDK is older than the newest release of its major",
       "Upgrade within the major; minor releases carry spec fixes.", TS_MIGRATE),
    _e("MCP003", "warn", "sdk", "v1 and v2 SDK packages imported side by side",
       "Finish the migration per directory; objects must not flow between v1- and v2-imported "
       "code, they do not recognise each other's types or error classes.", TS_UPGRADE),
    _e("MCP004", "warn", "sdk", "MCP Apps package does not match the SDK major",
       "`@modelcontextprotocol/ext-apps` 2.x peers on `@modelcontextprotocol/server` ^2; "
       "upgrade both together.", APPS_EXT),
    _e("MCP005", "warn", "sdk", "zod older than the v2 TypeScript SDK accepts",
       "The v2 line requires zod >= 4.2.0.", TS_UPGRADE),
    _e("MCP006", "warn", "sdk", "Node.js older than the v2 TypeScript SDK supports",
       "The v2 packages declare engines node >= 20.", TS_UPGRADE),

    # -- MCP01x: era, sessions, discovery --------------------------------
    _e("MCP010", "warn", "protocol", "protocol-level sessions are used",
       "2026-07-28 removed sessions and `Mcp-Session-Id`; carry cross-call state in explicit, "
       "server-minted handles passed as tool arguments.", CHANGELOG),
    _e("MCP011", "error", "protocol", "handshake-only transport: the server answers `initialize` and nothing modern",
       "Serve through a dual-era entry point: TypeScript `createMcpHandler(factory)` (default "
       "`legacy: 'stateless'`) or `serveStdio`; Python `mcp>=2`.", VERSIONING),
    _e("MCP012", "error", "protocol", "`server/discover` is not served",
       "Servers MUST implement `server/discover`; the v2 SDK entry points do it for you.", DISCOVER),
    _e("MCP013", "warn", "protocol", "legacy traffic is rejected (modern-only endpoint)",
       "`legacy: 'reject'` drops every 2025-11-25 client, Alexa+ included. Keep the default "
       "`'stateless'` unless every client you serve is modern.", TS_HANDLER),
    _e("MCP014", "info", "protocol", "an old protocol revision is written as a literal",
       "Let the SDK negotiate; a pinned `protocolVersion` literal goes stale with the next revision.",
       VERSIONING),
    _e("MCP015", "warn", "protocol", "custom HTTP routing in front of the SDK",
       "A hand-written router that inspects the JSON body must also honour the 2026-07-28 rules "
       "(405 for GET/DELETE, header/body agreement, 400 bodies that are JSON-RPC errors).", TRANSPORT),

    # -- MCP02x: headers ---------------------------------------------------
    _e("MCP020", "warn", "protocol", "`Mcp-Method` / `Mcp-Name` are not validated against the body",
       "Reject a mismatch with 400 and JSON-RPC -32020 (HeaderMismatch); `createMcpHandler` "
       "does it, a custom router has to.", TRANSPORT),
    _e("MCP021", "info", "protocol", "a tool parameter is mirrored into a header with `x-mcp-header`",
       "Check the constraints: primitive non-number types, statically reachable, unique.", TRANSPORT),

    # -- MCP03x: results ---------------------------------------------------
    _e("MCP030", "warn", "protocol", "a hand-built JSON-RPC result has no `resultType`",
       "Every 2026-07-28 result carries `resultType` (`complete` or `input_required`).", BASIC),
    _e("MCP031", "warn", "protocol", "cacheable results carry no deliberate `ttlMs` / `cacheScope`",
       "Set `cacheHints` (TypeScript ServerOptions) or the equivalent; the v2 SDK defaults to "
       "`ttlMs: 0`, `cacheScope: 'private'`, which is safe but makes every list immediately stale.",
       CACHING),
    _e("MCP032", "warn", "protocol", "`cacheScope: 'public'` on an authenticated server",
       "A public result may be served to callers with a different token; use 'private' for "
       "anything that varies by user.", CACHING),

    # -- MCP04x: deprecated / removed -------------------------------------
    _e("MCP040", "warn", "protocol", "a deprecated feature is used",
       "Roots, Sampling, Logging, HTTP+SSE and DCR are Deprecated in 2026-07-28 (earliest "
       "removal: first revision on or after 2027-07-28). Follow the registry's migration path.",
       DEPRECATED),
    _e("MCP041", "warn", "protocol", "a method removed by 2026-07-28 is implemented or called",
       "Keep it only on the legacy path; modern clients use `subscriptions/listen`, per-request "
       "`logLevel`, MRTR, and the tasks extension's `tasks/get`.", CHANGELOG),
    _e("MCP042", "warn", "protocol", "SSE resumability (`Last-Event-ID`, event store) is configured",
       "Removed in 2026-07-28: a broken stream loses the request and the client re-issues it.",
       TRANSPORT),

    # -- MCP05x: error codes ---------------------------------------------
    _e("MCP050", "warn", "protocol", "error code -32002 (resource not found)",
       "2026-07-28 MUST NOT emit -32002; use -32602 (Invalid params).", BASIC),
    _e("MCP051", "warn", "protocol", "draft error numbering",
       "HeaderMismatch is -32020, MissingRequiredClientCapability -32021, "
       "UnsupportedProtocolVersion -32022.", CHANGELOG),
    _e("MCP052", "error", "protocol", "an error code in the spec-reserved range that the spec does not define",
       "-32020..-32099 is reserved for the MCP specification; allocate application codes outside "
       "-32768..-32000.", BASIC),

    # -- MCP06x: tools ----------------------------------------------------
    _e("MCP060", "warn", "tools", "a tool declares no `inputSchema`",
       "Declare an object schema with every required parameter; clients (and Alexa+ "
       "certification) need it to call the tool correctly.", TOOLS),
    _e("MCP061", "warn", "tools", "`inputSchema` is a raw shape, not `z.object(...)`",
       "Raw shapes are deprecated on registration in the v2 SDK; wrap with `z.object()`.", TS_UPGRADE),
    _e("MCP062", "warn", "tools", "tools are registered in a nondeterministic order",
       "Servers SHOULD return `tools/list` in a deterministic order; register from a fixed list.",
       CHANGELOG),
    _e("MCP063", "warn", "tools", "the tool list depends on the caller",
       "A list that varies per caller must be `cacheScope: 'private'`, and every listed tool "
       "must still be invocable.", CACHING),
    _e("MCP064", "warn", "tools", "a tool name does not follow the naming guidance",
       "Use 1-128 characters from A-Z a-z 0-9 _ - . (SEP-986).", TOOLS),
    _e("MCP065", "error", "tools", "two tools share a name",
       "Tool names must be unique within a server.", TOOLS),
    _e("MCP066", "warn", "tools", "a tool has no description",
       "The description is what the model routes on.", TOOLS),
    _e("MCP067", "warn", "tools", "deprecated variadic registration (`server.tool(...)`)",
       "v2 removes `.tool()` / `.prompt()` / `.resource()`; use `registerTool` with a config object.",
       TS_UPGRADE),

    # -- MCP07x: server-initiated requests --------------------------------
    _e("MCP070", "warn", "protocol", "a server-initiated request needs MRTR",
       "On 2026-07-28 return `inputRequired(...)` (TypeScript) / `InputRequiredResult` (Python); "
       "the v2 SDK shims it to push-style requests for 2025-era clients.", TS_MIGRATE),
    _e("MCP071", "info", "protocol", "unsolicited list-changed notifications",
       "On 2026-07-28 change notifications reach only clients that opened `subscriptions/listen`.",
       CHANGELOG),

    # -- MCP08x: transport hygiene ----------------------------------------
    _e("MCP080", "error", "transport", "a stdio server writes to stdout",
       "stdout carries the protocol; log to stderr.", f"{S}/basic/transports/stdio"),
    _e("MCP081", "info", "transport", "an HTTP server binds all interfaces",
       "Local servers SHOULD bind 127.0.0.1 and MUST validate `Origin`.", TRANSPORT),
    _e("MCP082", "warn", "transport", "the deprecated HTTP+SSE transport is served",
       "Migrate to Streamable HTTP.", DEPRECATED),

    # -- MCP09x: extensions ----------------------------------------------
    _e("MCP090", "warn", "extensions", "experimental core tasks from 2025-11-25",
       "Tasks moved to the `io.modelcontextprotocol/tasks` extension: `tasks/get`, `tasks/update`, "
       "`tasks/cancel`; `resultType: \"task\"`.", TASKS_EXT),
    _e("MCP091", "error", "extensions", "a tool points at a UI resource that is not registered",
       "Register the `ui://` resource the tool's `_meta.ui.resourceUri` names.", APPS_EXT),


    # -- AUT: authorization ----------------------------------------------
    _e("AUT001", "warn", "auth", "an HTTP server with no authorization at all",
       "Remote servers SHOULD implement the MCP authorization profile (OAuth 2.1 resource server).",
       AUTHZ),
    _e("AUT002", "error", "auth", "no Protected Resource Metadata endpoint",
       "MCP servers MUST implement RFC 9728: serve `/.well-known/oauth-protected-resource` "
       "(path-inserted for a path endpoint, e.g. `/.well-known/oauth-protected-resource/mcp`).", AUTHZ),
    _e("AUT003", "error", "auth", "the PRM document lacks `resource` or `authorization_servers`",
       "Both are needed for authorization server discovery.", AUTHZ),
    _e("AUT004", "info", "auth", "PRM is served only at the root well-known path",
       "For an endpoint with a path, also serve the path-inserted location.", AUTHZ),
    _e("AUT005", "warn", "auth", "PRM `resource` does not match the MCP endpoint",
       "The `resource` value is the canonical server URI clients put in the `resource` parameter.",
       AUTHZ),
    _e("AUT010", "warn", "auth", "a 401 without `WWW-Authenticate: Bearer resource_metadata=...`",
       "Point clients at the PRM document from the challenge (RFC 9728 §5.1).", AUTHZ),
    _e("AUT011", "warn", "auth", "unauthenticated requests are served for some methods",
       "Decide per method on purpose: an anonymous `tools/list` is a policy, not an accident; Alexa+ "
       "expects 401 for unauthenticated requests.", ALX_QUICK),
    _e("AUT012", "info", "auth", "insufficient scope is not signalled with 403 `insufficient_scope`",
       "Answer 403 with `WWW-Authenticate: Bearer error=\"insufficient_scope\", scope=...`.", AUTHZ),
    _e("AUT020", "error", "auth", "access tokens are not checked for audience / resource",
       "MCP servers MUST validate that tokens were issued for them (RFC 8707).", AUTHZ),
    _e("AUT021", "error", "auth", "the incoming bearer token is passed through downstream",
       "MCP servers MUST NOT accept or transit other tokens; use your own credentials downstream.",
       AUTHZ),
    _e("AUT022", "error", "auth", "a JWT is decoded without verification",
       "Verify signature, issuer, audience and expiry.", AUTHZ),
    _e("AUT023", "error", "auth", "an access token is read from the query string",
       "Access tokens MUST NOT be included in the URI query string.", AUTHZ),
    _e("AUT030", "warn", "auth", "Dynamic Client Registration is offered or relied on",
       "DCR is Deprecated in 2026-07-28 in favour of Client ID Metadata Documents; Alexa+ does not "
       "support DCR.", DEPRECATED),
    _e("AUT031", "info", "auth", "no Client ID Metadata Document support advertised",
       "Advertise `client_id_metadata_document_supported` if the authorization server accepts CIMD.",
       AUTHZ),
    _e("AUT040", "error", "auth", "PKCE S256 is not advertised",
       "Authorization server metadata must list `S256` in `code_challenge_methods_supported`.", AUTHZ),
    _e("AUT041", "info", "auth", "authorization responses are not marked as carrying `iss`",
       "Advertise `authorization_response_iss_parameter_supported: true` and emit `iss` (RFC 9207).",
       AUTHZ),
    _e("AUT050", "info", "auth", "tools declare no per-tool scopes",
       "Declare `securitySchemes` per tool so clients can request least privilege.", AUTHZ),
    _e("AUT051", "warn", "auth", "`offline_access` is advertised by the resource server",
       "Servers SHOULD NOT include `offline_access` in `scopes_supported` or challenges.", AUTHZ),
    _e("AUT060", "error", "auth", "PRM document could not be fetched",
       "Serve it publicly (no token) with `application/json`.", AUTHZ),
    _e("AUT061", "error", "auth", "authorization server metadata could not be fetched",
       "Serve RFC 8414 or OpenID Connect Discovery metadata at the issuer.", AUTHZ),

    # -- ALX: Alexa+ ------------------------------------------------------
    _e("ALX001", "warn", "alexa", "no `addon.json`",
       "Scaffold it with `alexa-ai new mcp --name ... --locale en-US --mcp-server-url ...`.", ALX_QUICK),
    _e("ALX002", "error", "alexa", "`addon.json` is not valid JSON", "Fix the syntax.", ALX_QUICK),
    _e("ALX003", "error", "alexa", "`manifestVersion` missing or not \"1.0\"", "Set it to \"1.0\".", ALX_QUICK),
    _e("ALX010", "error", "alexa", "`distributionCountries` missing or empty",
       "List the countries in `storeListing.distributionCountries`.", ALX_QUICK),
    _e("ALX011", "warn", "alexa", "a distribution country where the MCP toolkit is not documented as available",
       "The toolkit overview states availability in the United States.", ALX_OVERVIEW),
    _e("ALX012", "error", "alexa", "no locale, or a malformed locale key",
       "Use `storeListing.locales` keyed by tags such as `en-US`.", ALX_QUICK),
    _e("ALX013", "error", "alexa", "add-on name missing or longer than 30 characters",
       "`name.value` is required, at most 30 characters.", ALX_QUICK),
    _e("ALX014", "error", "alexa", "short description missing or longer than 123 characters",
       "`shortDescription` is required, at most 123 characters.", ALX_QUICK),
    _e("ALX015", "error", "alexa", "full description missing or longer than 4000 characters",
       "`fullDescription` is required, at most 4000 characters.", ALX_QUICK),
    _e("ALX016", "error", "alexa", "example phrases: need 3-4 distinct phrases of at most 200 characters",
       "Provide at least 3 distinct, relevant phrases that work when spoken.", ALX_FUNC),
    _e("ALX017", "error", "alexa", "privacy policy or terms-of-use URL missing or not HTTPS",
       "Both are required and must be valid HTTPS URLs.", ALX_QUICK),
    _e("ALX018", "error", "alexa", "a required light icon size is missing",
       "Provide 72, 64, 88, 126, 180 and 241 px square light icons over HTTPS.", ALX_QUICK),
    _e("ALX019", "error", "alexa", "media asset problem (carousel, format, HTTPS, alt text)",
       "At least one 600x900 carousel image; PNG/JPG/JPEG/WEBP over HTTPS; alt text <= 250.", ALX_QUICK),
    _e("ALX020", "error", "alexa", "no HTTPS MCP endpoint in `integrations`",
       "Add an `MCP` integration with `config.endpoints.default` `{type: HTTPS, uri}`.", ALX_QUICK),
    _e("ALX021", "warn", "alexa", "the add-on endpoint does not match the server's canonical URI",
       "Use the same URI as the PRM `resource` / OAuth `resource` parameter.", ALX_QUICK),
    _e("ALX022", "warn", "alexa", "store metadata contains developer jargon",
       "No API names, tool names, JSON references or developer jargon in customer-facing text.",
       ALX_FUNC),
    _e("ALX030", "error", "alexa", "measured latency is above the 500 ms round-trip budget",
       "Cut cold starts (provisioned concurrency, smaller bundle), cache secrets and JWKS, trim "
       "per-request setup; re-measure with probe.py.", ALX_QUICK),
    _e("ALX031", "info", "alexa", "no latency measurement yet",
       "Run `probe.py <url> --budget-ms 500 --json > probe.json` and pass `--probe-report`.", ALX_QUICK),
    _e("ALX032", "info", "alexa", "Lambda hosting: cold starts count against the 500 ms budget",
       "Measure p95 including cold starts; consider provisioned concurrency.", ALX_QUICK),
    _e("ALX040", "warn", "alexa", "a tool description is not voice-shaped",
       "Say when to call it, what it returns and what it does not do; no screen references.",
       ALX_DESIGN),
    _e("ALX041", "warn", "alexa", "a list-returning tool may present more than 5 options",
       "Voice-only: at most 5 options with key differentiators, and offer pagination.", ALX_FUNC),
    _e("ALX042", "info", "alexa", "a generic, API-shaped tool name",
       "Name tools for customer intent (`search_hotels`), not `get_x` / `post_y`.", ALX_DESIGN),
    _e("ALX043", "warn", "alexa", "a tool depends on a UI with no voice path",
       "Every critical feature must complete by voice on headless devices.", ALX_FUNC),
    _e("ALX050", "warn", "alexa", "401 responses carry `WWW-Authenticate`, which Alexa+ lists as unsupported",
       "The MCP spec wants the challenge, the Alexa+ quickstart says 401 *without* it. Confirm in the "
       "web simulator which one account linking accepts before changing anything.", ALX_QUICK),
    _e("ALX051", "warn", "alexa", "authorization server metadata does not match the Alexa+ profile",
       "S256 in `code_challenge_methods_supported`, `client_credentials` in `grant_types_supported`, "
       "metadata at `/.well-known/oauth-authorization-server`.", ALX_AUTH),
    _e("ALX052", "warn", "alexa", "relies on DCR, CIMD, OIDC or step-up, which Alexa+ does not support",
       "Pre-register the Alexa+ client with your authorization server.", ALX_QUICK),
    _e("ALX053", "warn", "alexa", "unauthenticated requests are not all answered with 401",
       "The quickstart expects 401 Unauthorized for unauthenticated requests.", ALX_QUICK),
    _e("ALX054", "info", "alexa", "the scopes Alexa+ will request are ambiguous",
       "Alexa+ discovers scopes from PRM `scopes_supported` (account-linking page) while the authentication "
       "page names `mcp:service`, `mcp:tools`, `mcp:resources`; advertise the names your authorization server "
       "accepts and confirm in the simulator which ones Alexa+ requests.", ALX_LINKING),
    _e("ALX055", "warn", "alexa", "the AS metadata `issuer` is not the `iss` the tokens carry",
       "A metadata façade must not claim an issuer its tokens do not carry; either serve the real issuer's "
       "metadata or mint tokens under the advertised issuer (RFC 8414 §3.3, RFC 9207).", ALX_AUTH),
    _e("ALX060", "error", "alexa", "the server cannot serve 2025-11-25 clients",
       "Alexa+ supports the 2025-11-25 revision; keep the legacy path (`legacy: 'stateless'`).",
       ALX_OVERVIEW),
    _e("ALX061", "error", "alexa", "no Streamable HTTP endpoint",
       "Alexa+ requires a remote Streamable HTTP server; stdio and HTTP+SSE are not reachable.",
       ALX_QUICK),
    _e("ALX080", "warn", "alexa", "tool signatures changed since the recorded lock",
       "Alexa+ refreshes tool information only on `alexa-ai deploy`; redeploy, and treat signature "
       "changes on a certified add-on as a new submission.", ALX_QUICK),

    # -- PRB: live probe -------------------------------------------------
    _e("PRB001", "error", "probe", "the endpoint is unreachable", "Check the URL, DNS and TLS.", TRANSPORT),
    _e("PRB010", "error", "probe", "`server/discover` failed",
       "Servers MUST implement `server/discover`.", DISCOVER),
    _e("PRB011", "error", "probe", "the discover result is incomplete or omits the target revision",
       "Return `supportedVersions` (including the target), `capabilities`, `resultType`, cache hints.",
       DISCOVER),
    _e("PRB012", "error", "probe", "legacy `initialize` failed",
       "Keep a dual-era entry point so 2025-11-25 clients still connect.", VERSIONING),
    _e("PRB013", "error", "probe", "legacy `tools/list` failed after `initialize`",
       "The legacy path must serve the session it opened.", VERSIONING),
    _e("PRB020", "error", "probe", "a header/body mismatch was accepted",
       "Reject with 400 and -32020 (HeaderMismatch).", TRANSPORT),
    _e("PRB021", "warn", "probe", "a request without `Mcp-Method` was accepted",
       "Missing required standard headers are a validation failure (400, -32020).", TRANSPORT),
    _e("PRB022", "warn", "probe", "a header rejection used the wrong status or code",
       "Use HTTP 400 with JSON-RPC -32020.", TRANSPORT),
    _e("PRB030", "error", "probe", "a modern result has no `resultType`",
       "Every 2026-07-28 result carries `resultType`.", BASIC),
    _e("PRB031", "error", "probe", "a cacheable result has no `ttlMs` / `cacheScope`",
       "Required on discover, list and read results.", CACHING),
    _e("PRB032", "info", "probe", "results carry no `serverInfo` in `_meta`",
       "Servers SHOULD identify themselves in each result's `_meta`.", BASIC),
    _e("PRB033", "warn", "probe", "`tools/list` order changed between calls",
       "Return tools in a deterministic order.", CHANGELOG),
    _e("PRB034", "error", "probe", "a listed tool has no valid object `inputSchema`",
       "Every listed tool needs an `inputSchema` of type object.", TOOLS),
    _e("PRB040", "warn", "probe", "an unauthenticated request was not answered with 401",
       "Invalid, expired or missing tokens get 401 when the server requires authorization.", AUTHZ),
    _e("PRB041", "warn", "probe", "the 401 has no `resource_metadata` challenge",
       "Add `WWW-Authenticate: Bearer resource_metadata=\"...\"` (see ALX050 for Alexa+).", AUTHZ),
    _e("PRB042", "error", "probe", "Protected Resource Metadata is not reachable or invalid",
       "Serve RFC 9728 metadata at the well-known path.", AUTHZ),
    _e("PRB050", "warn", "probe", "p95 latency is above the budget",
       "Find where the time goes (cold start, auth, storage) and re-measure.", ALX_QUICK),
    _e("PRB051", "info", "probe", "GET on the MCP endpoint is not answered with 405",
       "A 2026-07-28-only server SHOULD answer GET/DELETE with 405.", TRANSPORT),
    _e("PRB052", "info", "probe", "the server returned SSE where JSON was enough",
       "Either is valid; JSON responses are cheaper through API gateways.", TRANSPORT),

    # -- MIG: migration -------------------------------------------------
    _e("MIG001", "info", "migrate", "a step cannot be applied automatically",
       "Apply the guided step by hand from the before/after in the plan, then re-run the review.",
       TS_MIGRATE),
    _e("MIG002", "error", "migrate", "a file changed since the plan was made",
       "Re-run plan_migration.py; the codemod never edits a file it did not plan against.", PLUGIN),
    _e("MIG003", "info", "migrate", "nothing to migrate for this target",
       "The review found nothing a migration step addresses.", PLUGIN),
    _e("MIG004", "info", "migrate", "a dependency bump needs peer dependencies installed beside it",
       "Apply the dependency step whole (it adds the peers), then run the package manager's install before "
       "building; with strict peer dependencies an install without them fails.",
       "https://pnpm.io/settings#strictpeerdependencies"),

    # -- CI ------------------------------------------------------------
    _e("CI001", "warn", "ci", "no workflow runs the MCP review",
       "Add the review step generated by gen_workflow.py.", PLUGIN),
    _e("CI002", "info", "ci", "no workflow runs the live probe",
       "Probe the deployed endpoint after each deploy, with a latency budget.", PLUGIN),
    _e("CI003", "error", "ci", "a credential literal in a workflow",
       "Read tokens from repository secrets.", PLUGIN),
    _e("CI004", "warn", "ci", "an exit code is masked",
       "`|| true` or `continue-on-error` on the review hides the gate; treat exit 3 explicitly instead.",
       PLUGIN),
    _e("CI005", "warn", "ci", "the plugin is fetched from an unpinned ref",
       "Pin a tag so the gate does not move under you.", PLUGIN),

    # -- UPG: upgrade loop ---------------------------------------------
    _e("UPG001", "warn", "upgrade", "a newer protocol revision is current",
       "Compute the delta, re-review with --target <new>, and plan the migration.", VERSIONING),
    _e("UPG002", "info", "upgrade", "the live versioning page could not be read",
       "Re-run with network access, or pass --page-file with a saved copy.", VERSIONING),
    _e("UPG003", "info", "upgrade", "an SDK has a newer release than this plugin was checked against",
       "Read its release notes before upgrading; re-run the review afterwards.", TS_MIGRATE),
    _e("UPG004", "warn", "upgrade", "the pinned revision is not a published revision",
       "Pin a revision listed on the versioning page.", VERSIONING),
]

CATALOG: dict[str, Entry] = {e.id: e for e in _ENTRIES}
BANDS = ("DSC", "MCP", "AUT", "ALX", "PRB", "MIG", "CI", "UPG")


def lookup(id: str) -> Entry:
    try:
        return CATALOG[id]
    except KeyError:
        raise KeyError(f"finding id {id} is not in the catalog") from None


def ids(band: str | None = None) -> list[str]:
    return sorted(i for i in CATALOG if band is None or i.startswith(band))
