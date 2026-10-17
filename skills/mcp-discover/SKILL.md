---
name: mcp-discover
description: >-
  Read-only inventory of the MCP server(s) in a project, from files alone:
  language, SDK package and version (resolving pnpm `catalog:` and
  `workspace:*`), transports (Streamable HTTP, stdio, HTTP+SSE), the protocol
  era the code really implements (handshake-only, 2026-07-28-only, dual),
  auth (Protected Resource Metadata, WWW-Authenticate, token verification,
  audience checks, authorization server type, DCR, per-tool scopes), tools,
  resources and prompts with their schemas, MCP Apps and tasks extension use,
  hosting hints (Lambda handler, Express, Hono, FastAPI, Terraform, SAM, CDK)
  and CI workflows. Use when asked "what MCP servers are in this repo",
  "which SDK version / which spec version does my server use", "does it use
  sessions", "is it Lambda", "list my tools", "inventory", or before any
  migration or certification so the facts are on the table. Don't use for
  judging the server against the spec (use `/mcp-server:mcp-review`), for a
  running endpoint (use `/mcp-server:mcp-verify`), or for routing a vague
  request (use `/mcp-server:mcp-server`).
argument-hint: "[project-dir] [--unit name]"
allowed-tools: Read, Grep, Glob, AskUserQuestion, Skill, Bash(python3 *)
---

# Inventory an MCP server

Everything later depends on four facts that are easy to get wrong by eye:
which package is the server, which SDK version it really resolves to, which
era its serving code implements, and where its auth lives. Discovery reads
them from the files — manifests, lockless catalogs, sources of the server
*and* of the workspace packages it imports — and never runs anything.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim; sibling scripts are at
`${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Discover.**

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/discover.py <project> [--unit name] [--json]
   ```

   Point it at the repository root; it finds servers in subdirectories
   (`apps/mcp-server`, `services/*`). `--unit` narrows to one by package name
   or path suffix.

2. **Report** the Found block per server as printed: SDK `package version
   (declared as ...)`, era and its meaning, transports, hosting, auth summary,
   the tool table, extensions, CI. Then Missing and any `DSC` findings.

3. **Options** come from the report: review (free), probe (probe), auth
   (free), Alexa+ (free) when an `addon.json` or Lambda hosting is present.
   One is recommended: review when the era is `handshake` or `unknown`, probe
   when the code is already dual.

4. **Confirm** with `AskUserQuestion`, then hand over with `Skill`. Discovery
   itself writes nothing and needs no confirmation.

## Reading the result

- **`era`** is the headline. `handshake` means 2026-07-28 clients are refused
  today; `stateless` means 2025-era clients (Alexa+ among them) are refused;
  `dual` serves both. See [detection-rules.md](references/detection-rules.md).
- **`sdk.resolved`** is the version the manifests pin, not what
  `node_modules` holds. `DSC003` means it could not be resolved: say so, do not
  guess.
- **`auth.authorization_server`** names the issuer family it recognised
  (cognito, auth0, okta, entra, keycloak, agentcore); `unknown` means token
  verification exists but the issuer could not be named.
- **`tools[].input_schema`**: `zod-object`, `json`, `derived` (Python type
  hints) are fine; `raw-shape` is deprecated in v2; `none` is a finding.
- **Workspace packages** are read for auth and hosting signals but are not
  servers; a PRM route in `packages/auth` counts for the server that imports
  it.

## Decision rules

- **Several servers**: list them all (`DSC002`) and ask which one before any
  write-capable skill; reviews may run on all.
- **Third-party `fastmcp`** (`DSC004`) is not the official SDK; its 2026-07-28
  support is its own release notes' business.
- **Nothing found** (`DSC001`, exit 2): ask for the directory. Do not start
  guessing from file names.

## References

| Question | File |
|---|---|
| Every field in the inventory and where it comes from | [inventory-fields.md](references/inventory-fields.md) |
| How era, transport, hosting and auth are detected | [detection-rules.md](references/detection-rules.md) |

## Scripts

| Command | Output | Exit codes |
|---|---|---|
| `scripts/discover.py <project> [--unit name] [--json] [--strict]` | inventory gap report | 0 found, 1 parse errors, 2 no server |

## Completion checklist

- [ ] `discover.py` ran and its Found block was shown as printed.
- [ ] The era of each server was stated with its consequence for modern and legacy clients.
- [ ] An unresolved SDK version (`DSC003`) was reported, not guessed.
- [ ] Several servers were listed and the user chose one before anything write-capable.
- [ ] The next skill was offered with its cost tier and invoked only after the user chose.
