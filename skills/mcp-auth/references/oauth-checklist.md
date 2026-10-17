# The MCP resource-server checklist (2026-07-28)

Authorization is optional for MCP; when an HTTP server does it, it SHOULD
follow this profile. stdio servers SHOULD NOT and take credentials from the
environment instead. Each item names the finding that checks it.

## Discovery

| # | Requirement | Strength | Id |
|---|---|---|---|
| 1 | Implement OAuth 2.0 Protected Resource Metadata (RFC 9728) | MUST | AUT002 |
| 2 | PRM names `resource` (the canonical server URI) and `authorization_servers` | needed for discovery | AUT003 |
| 3 | Serve PRM at the path-inserted location for a path endpoint (`/.well-known/oauth-protected-resource/mcp`) as well as or instead of the root | RFC 9728 §3.1 | AUT004 |
| 4 | `resource` equals the endpoint clients call (no fragment; no trailing slash unless significant) | canonical URI rules | AUT005 |
| 5 | 401 carries `WWW-Authenticate: Bearer resource_metadata="<PRM URL>"`, and SHOULD carry `scope="..."` for the operation | SHOULD (RFC 9728 §5.1, RFC 6750 §3) | AUT010 |
| 6 | Authorization servers expose RFC 8414 metadata or OpenID Connect Discovery; clients try both | AS: at least one | AUT061 |

Example challenge:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource/mcp",
                         scope="books.read"
```

## Token handling

| # | Requirement | Strength | Id |
|---|---|---|---|
| 7 | Validate tokens per OAuth 2.1 §5.2: signature, issuer, expiry | MUST | AUT022 |
| 8 | Validate the token was issued for *this* server (audience / RFC 8707 resource) | MUST | AUT020 |
| 9 | Invalid, expired or missing tokens get 401 | MUST | AUT011, PRB040 |
| 10 | Accept or transit no other tokens; never forward the caller's token downstream | MUST NOT | AUT021 |
| 11 | Tokens only in the `Authorization` header, never the query string | MUST NOT | AUT023 |
| 12 | Insufficient scope: 403 with `error="insufficient_scope"`, `scope`, `resource_metadata` — all scopes the operation needs in one challenge | SHOULD | AUT012 |
| 13 | Do not advertise `offline_access` in PRM `scopes_supported` or challenges | SHOULD NOT | AUT051 |

## Client registration (what the authorization server offers)

Priority for clients: Client ID Metadata Documents (CIMD), pre-registration,
then Dynamic Client Registration. 2026-07-28 **deprecates DCR** (earliest
removal: first revision on or after 2027-07-28) in favour of CIMD, which the
authorization server advertises as `client_id_metadata_document_supported`.

| # | Item | Id |
|---|---|---|
| 14 | DCR (`registration_endpoint`) offered or relied on | AUT030 |
| 15 | CIMD not advertised by a self-hosted authorization server | AUT031 |

## Authorization server metadata (when it is yours, or to check your IdP)

| # | Item | Id |
|---|---|---|
| 16 | `code_challenge_methods_supported` includes `S256` (PKCE) | AUT040 |
| 17 | `authorization_response_iss_parameter_supported: true` and `iss` in responses (RFC 9207); clients MUST validate a present `iss` | AUT041 |

## Least privilege per tool

Declare required scopes per tool (`_meta.securitySchemes: [{type: "oauth2",
scopes: [...]}]`) so a client can request only what a tool needs and a server
can answer 403 with the precise scope (`AUT050`). Scope hierarchies are the
server's to honour: a broader scope implies narrower ones.

## Clients' side of the same flow (for context)

PKCE with S256, the `resource` parameter on both authorization and token
requests, `iss` validation before redeeming the code, credentials keyed by
issuer, the union of previously granted and challenged scopes on step-up.

---

Sources: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization,
https://modelcontextprotocol.io/specification/2026-07-28/changelog (minor 7-9,
deprecated 4), https://modelcontextprotocol.io/specification/2026-07-28/deprecated
(read 2026-10-05); RFC 9728, RFC 8707, RFC 9207, RFC 6750.
