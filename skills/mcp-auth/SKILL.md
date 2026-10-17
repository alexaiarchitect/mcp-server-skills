---
name: mcp-auth
description: >-
  Review an MCP server as an OAuth 2.1 resource server under the 2026-07-28
  authorization profile, statically and against its live metadata. Emits the
  AUT0xx band: no auth on an HTTP server; Protected Resource Metadata (RFC
  9728) missing, incomplete or only at the root path; 401s without a
  `WWW-Authenticate: Bearer resource_metadata=...` challenge; methods served
  anonymously by a body-inspecting gate; no 403 `insufficient_scope` step-up;
  tokens verified without audience/resource binding (RFC 8707), passed
  through downstream, decoded without verification, or read from the query
  string; Dynamic Client Registration (Deprecated) versus Client ID Metadata
  Documents; PKCE S256 and RFC 9207 `iss` in authorization server metadata;
  per-tool scopes via `securitySchemes`; `offline_access` misuse. Includes
  Amazon Cognito and AgentCore Gateway/Identity recipes. Use when asked
  "review my MCP server's OAuth", "why does the client not find my
  authorization server", "PRM", "WWW-Authenticate", "audience", "PKCE",
  "DCR vs CIMD", "Cognito for MCP", or before an Alexa+ account-linking
  setup. Don't use for stdio servers (they take credentials from the
  environment), for building an authorization server, or for client-side
  OAuth.
argument-hint: "[project-dir] | <mcp-url> [--alexa]"
allowed-tools: Read, Grep, Glob, AskUserQuestion, Skill, Bash(python3 *)
---

# Authorization review for an MCP server

An MCP server is an OAuth 2.1 *resource server*: it does not issue tokens, it
tells clients where to get them (Protected Resource Metadata), challenges
correctly when a token is missing or insufficient, and accepts only tokens
minted for itself. Most failures are one of those three, and most of them are
in a shared auth package, not in the server file — the review reads both.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim; sibling scripts are at
`${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Static review** (free):

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/lint_auth.py <project> [--unit name]
   ```

2. **Live metadata** (network; no token is sent), when there is a URL:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/check_prm.py https://<host>/mcp [--alexa [--token-iss <iss of a real token>]]
   ```

   It follows the client's discovery chain: path-inserted PRM, root PRM, then
   the first authorization server's RFC 8414 / OIDC metadata. Offline:
   `--prm-file` / `--as-file`.

3. **Report** the auth summary from the Found block (PRM, challenge,
   verification, audience, issuer family, DCR, per-tool scopes), then the
   findings by severity, each with its source.

4. **Options**: fix in code (write), fix authorization-server settings (the
   user does it in their IdP console; give the exact setting), probe the 401
   end to end (`/mcp-server:mcp-verify`, probe). One recommended.

5. **Confirm** with `AskUserQuestion` before editing anything.

## Decision rules

- **Audience is the one that matters most.** A server that accepts any token
  from its issuer accepts tokens minted for other APIs (`AUT020`). With
  Cognito, request a resource binding so `aud` is the MCP URL, or check
  `client_id` against an allow-list — see [cognito.md](references/cognito.md).
- **An anonymous `tools/list` is a decision, not a default.** If the gate only
  401s `tools/call` (`AUT011`), ask whether discovery without a token is
  intended; Alexa+ expects 401 for unauthenticated requests.
- **DCR is Deprecated, not forbidden**: keep it if existing clients depend on
  it, offer CIMD alongside; Alexa+ supports neither — it uses a pre-registered
  client.
- **Two specs disagree on the 401 header.** MCP wants `WWW-Authenticate` with
  `resource_metadata`; the Alexa+ quickstart says 401 *without* it. Do not
  remove the header to please one reading; route to `/mcp-server:mcp-alexa`
  and test in the simulator (`ALX050`).
- **Report only.** Make no change before the user chose one.

## References

| Question | File |
|---|---|
| The resource-server checklist, item by item, with ids | [oauth-checklist.md](references/oauth-checklist.md) |
| Amazon Cognito as the authorization server | [cognito.md](references/cognito.md) |
| AgentCore Gateway and Identity in front of a server | [agentcore-identity.md](references/agentcore-identity.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/lint_auth.py <project> [--unit n] [--json] [--strict]` | static `AUT0xx` review | 0 no errors, 1 errors, 2 nothing to review |
| `scripts/check_prm.py <mcp-url> [--alexa [--token-iss URL]] [--json]` / `--prm-file f [--as-file f]` | fetch and validate PRM and AS metadata | 0, 1 errors, 2 usage, 3 not fetchable |

## Completion checklist

- [ ] `lint_auth.py` ran; `check_prm.py` ran too when a URL was available (or the user was told it was not).
- [ ] Audience binding was stated explicitly: checked, not checked, or unknown.
- [ ] Every anonymous method was named, and whether that is intended was asked, not assumed.
- [ ] The MCP-vs-Alexa+ 401 header conflict was surfaced if Alexa+ is in scope.
- [ ] Nothing was changed without the user choosing it.
