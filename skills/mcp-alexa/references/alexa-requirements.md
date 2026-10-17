# Alexa+ add-on requirements for an MCP server

Read from the Alexa+ developer documentation on 2026-10-05. Quotes are
verbatim; everything else is paraphrase. Ids are this plugin's checks.

## Protocol and transport

| Requirement | Source | Id |
|---|---|---|
| "Your MCP server must support Streamable HTTP." HTTP+SSE is deprecated | quickstart | ALX061 |
| The toolkit "supports the 2025-11-25 version of the MCP specification" and the MCP Apps extension | toolkit overview | ALX060 |
| The server is reachable at a remote URL (tunnels such as cloudflared for local development) | quickstart | ALX020 |
| "The MCP Toolkit is available in the United States." | toolkit overview | ALX011 |

## Latency

| Requirement | Source | Id |
|---|---|---|
| "a round-trip query response latency of less than 500 ms" | quickstart | ALX030, PRB050 |
| "Start delivering the first item within 500ms"; otherwise reduce the initial set and lazy-load behind "See more" | design guide | ALX041 |
| Search results "within 3 seconds", with an interim message if longer | functional requirements 7 | — |

## Tools

| Requirement | Source | Id |
|---|---|---|
| "Every tool returned by your server's `tools/list` endpoint must be invocable" | functional requirements 13 | PRB034, MCP063 |
| "Provide a valid JSON Schema `inputSchema` for every tool, with all required parameters declared" | functional requirements 13 | MCP060 |
| Failures use the MCP error contract (`isError: true` or JSON-RPC errors) | functional requirements 13 | — |
| Descriptions accurately reflect capabilities; intent-focused: when to call, what it returns, what it does not do | functional requirements 13, design guide | ALX040 |
| Names reflect customer intent (`search_hotels`), not `get_X` / `post_Y` | design guide | ALX042 |
| Voice-only: "Present a maximum of 5 options with key differentiators and offer pagination" | functional requirements 9 | ALX041 |
| Complete critical features by voice without referencing a screen | functional requirements 9 | ALX040, ALX043 |
| No API codes, tool names, JSON or internal IDs in customer-facing responses | functional requirements 2 | ALX022 (manifest) |

## Account linking

| Requirement | Source | Id |
|---|---|---|
| "Your MCP server returns `401 Unauthorized` (without a `WWW-Authenticate` header) for unauthenticated requests." | quickstart | ALX050, ALX053 |
| "Your auth server metadata is available at `/.well-known/oauth-authorization-server`." | quickstart | ALX051 |
| "`code_challenge_methods_supported` must be present and must include `S256`." | quickstart | ALX051, AUT040 |
| OAuth 2.1 authorization code with PKCE (S256); `resource` = the server's canonical URI on authorize and token requests; bearer token in the `Authorization` header on every request | quickstart | AUT020, AUT023 |
| Not supported: "Dynamic Client Registration (DCR), Client ID Metadata Documents (CIMD), OpenID Connect (OIDC), Step-Up Authorization, `WWW-Authenticate` header in 401 responses" | quickstart | ALX052, ALX050 |
| `client_credentials` for service-level calls (`mcp:service`); `mcp:tools` and `mcp:resources` via authorization code | authentication page | ALX051 |
| "Return a 401 Unauthorized when a token is expired or invalid"; scope all data to the authorized token | functional requirements 6 | PRB040 |

### The conflict

The MCP specification (2026-07-28 authorization section) has the server
answer 401 with `WWW-Authenticate: Bearer resource_metadata=...`; the Alexa+
quickstart describes the opposite. The
plugin reports `ALX050` as a warning and recommends testing account linking in
the web simulator with the header present before removing it — removing it
would break spec-following clients. Record the outcome in the friction log.

## Store listing (addon.json)

See [addon-json.md](addon-json.md). In short: name, short and full
descriptions, 3-4 example phrases that "actually work when spoken", privacy
policy and terms URLs, icons, carousel images, an MCP endpoint (ALX003-ALX022).

## Lifecycle

`alexa-ai new` → `alexa-ai deploy` (development stage; "Alexa+ refreshes tool
information only on redeployment") → test (web simulator, device,
`alexa-ai test`) → `alexa-ai submit` → In Review → Certified → Live. Failed
certification returns to Development. The certification page states that the
complete rubric and self-review checklist "will be added in a future revision".

## Not found in the docs read

- a limit on spoken answer length (e.g. 30 seconds);
- that tool signatures are locked after publication — this plugin's
  `tools_lock.py` treats any change as "redeploy and expect review", which is
  safe either way.

---

Sources: https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html,
https://developer.amazon.com/docs/alexaplus/add-ons/functional-requirements.html,
https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-certify.html,
https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-overview.html,
https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-design-guide.html,
https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-authentication.html,
https://developer.amazon.com/docs/alexaplus/add-ons/alexa-plus-add-on-development-stages.html (all read 2026-10-05).
