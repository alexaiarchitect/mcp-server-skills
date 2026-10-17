# Amazon Cognito as the MCP authorization server

Cognito user pools are a common issuer for MCP servers on AWS. They cover most
of the profile; the gaps are specific and worth knowing before a client fails.

## What Cognito gives you

| Need | Cognito |
|---|---|
| Issuer | `https://cognito-idp.<region>.amazonaws.com/<user-pool-id>` |
| Discovery | OpenID Connect Discovery at `<issuer>/.well-known/openid-configuration` — not RFC 8414 path insertion, so clients must fall back to OIDC (they MUST support both) |
| PKCE | authorization code with `code_challenge_method=S256` |
| Audience binding | **resource binding** (RFC 8707): pass `resource=<MCP URL>` on the authorize request; the access token's `aud` becomes that URL. Managed login only; one resource per request; user grants only — not `client_credentials`; refresh grants keep the original `aud` |
| Scopes | custom scopes on a resource server (`<identifier>/<scope>`); for resource binding the identifier must be a URL |
| Access token claims | `iss`, `client_id`, `token_use: "access"`, `scope`, `exp`, `sub`; `aud` **only** when a resource binding was requested |

## Verifying tokens in the MCP server

1. Verify signature against the pool's JWKS, `iss`, `exp`, `token_use ==
   "access"`.
2. Bind the audience, one of:
   - **with resource binding**: require `aud == <canonical MCP URL>`;
   - **without**: there is no `aud` in access tokens — require `client_id` in
     an explicit allow-list of app clients that may call this server. This is
     weaker (any resource the client may call is accepted), so prefer
     binding.
3. Map `scope` to per-tool requirements; answer 403 `insufficient_scope` with
   the missing scope.

Cache the JWKS at module scope (cold-start latency) — `aws-jwt-verify`'s
`CognitoJwtVerifier` and `jose`'s `createRemoteJWKSet` both do.

## PRM for a Cognito-backed server

```json
{
  "resource": "https://mcp.example.com/mcp",
  "authorization_servers": ["https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_AbCdEf"],
  "scopes_supported": ["https://mcp.example.com/books.read"],
  "bearer_methods_supported": ["header"]
}
```

## Gaps to check live

Run `check_prm.py <mcp-url>` and read what the pool's discovery document
actually advertises: whether `code_challenge_methods_supported` lists `S256`
(`AUT040` if absent — clients that require the advertisement will refuse),
whether `authorization_response_iss_parameter_supported` is present (`AUT041`),
and that there is no `registration_endpoint` (Cognito has no DCR; with CIMD
also absent, MCP clients need a pre-registered app client — which is exactly
what Alexa+ account linking uses).

## Alexa+ with Cognito

Alexa+ uses authorization code + PKCE for users and `client_credentials` for
service-level calls. Cognito supports `client_credentials` for M2M app clients
but **not** resource binding on that grant, so service-level tokens carry no
`aud`: validate them by `client_id` and scope instead. See
`/mcp-server:mcp-alexa`.

---

Sources: https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html,
https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-define-resource-servers.html,
https://docs.aws.amazon.com/cognito/latest/developerguide/using-pkce-in-authorization-code.html,
https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-authentication.html (all read 2026-10-05).
