---
name: mcp-review
description: >-
  Report-only static review of an MCP server (TypeScript/JavaScript or Python)
  against a pinned protocol revision, 2026-07-28 by default, read from the
  source so it works on a project that does not build. Emits the MCP0xx band:
  SDK major behind the target, mixed v1/v2 packages, ext-apps/zod/Node
  mismatches; sessions and Mcp-Session-Id; handshake-only transports; no
  server/discover; modern-only endpoints; custom routers that skip
  Mcp-Method/Mcp-Name validation; hand-built results without resultType;
  missing or unsafe ttlMs/cacheScope; Roots, Sampling, Logging, HTTP+SSE and
  removed methods; -32002 and draft error codes; tools without inputSchema,
  raw zod shapes, nondeterministic or per-caller tool lists, bad names,
  duplicates; server-initiated requests that need MRTR; stdout writes in
  stdio servers; 2025-11-25 experimental tasks; MCP Apps tools pointing at
  unregistered UI resources. `--baseline` reports what is new since a previous
  review. Use when asked to "review / lint / check my MCP server", "is it
  2026-07-28 compliant", "what breaks with the new spec", "why do new clients
  fail to connect", or after a migration step. Don't use for a running URL (use
  `/mcp-server:mcp-verify`), OAuth details (use `/mcp-server:mcp-auth`),
  Alexa+ readiness (use `/mcp-server:mcp-alexa`), or to make the changes (use
  `/mcp-server:mcp-migrate`).
argument-hint: "[project-dir] [--target 2026-07-28] [--baseline review.json]"
allowed-tools: Read, Grep, Glob, AskUserQuestion, Skill, Bash(python3 *)
---

# Review an MCP server against a revision

The review reads code; it never runs it. That makes it useful exactly when it
is needed: mid-migration, on a branch that does not compile, on a server whose
dependencies are not installed.

**This skill reports. It does not edit.** Fixes go through
`/mcp-server:mcp-migrate`, after the user has seen the findings and chosen.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim; sibling scripts are at
`${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Review.**

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/lint_server.py <project> --target 2026-07-28
   ```

   `--json` to branch on ids, `--strict` to fail on warnings (CI),
   `--unit name` for one server of several, `--baseline previous.json` to add
   what is new and what was resolved. `--target 2025-11-25` reviews the
   handshake era: the modern-only rules are skipped.

2. **Report** in severity order, leading with the count. An **error** means a
   client following the pinned revision cannot use the server as intended or
   a MUST is broken; a **warning** runs today but misleads, is Deprecated, or
   breaks on a date; a **note** is worth knowing.

3. **Options.** Typically: plan the migration (free; recommended when there is
   an `MCP001`/`MCP011`/`MCP012`), probe the endpoint (probe), review auth
   (free), gate CI on this review (write).

4. **Confirm** with `AskUserQuestion` before handing over. The review itself
   needs no confirmation.

## The ten decades

| Ids | Dimension | What goes wrong |
|---|---|---|
| MCP00x | SDK | a 1.x SDK cannot speak 2026-07-28; v1 and v2 imported together; ext-apps 2.x needs server ^2; zod < 4.2; Node < 20 |
| MCP01x | era | `Mcp-Session-Id`; a v1 transport answers only `initialize`; no `server/discover`; `legacy: 'reject'`; a pinned old revision; a router that reads the body first |
| MCP02x | headers | nothing compares `Mcp-Method`/`Mcp-Name` with the body (400 / -32020 required) |
| MCP03x | results | hand-built results without `resultType`; no cache hints; `cacheScope: 'public'` on an authenticated server |
| MCP04x | deprecated / removed | Roots, Sampling, Logging; `ping`, `logging/setLevel`, `resources/subscribe`, `tasks/result`...; SSE resumability |
| MCP05x | error codes | -32002 for a missing resource; draft numbering -32001/3/4; undefined codes in -32020..-32099 |
| MCP06x | tools | no `inputSchema`; raw shapes; registration in loops or behind conditions; names; duplicates; descriptions; `server.tool()` |
| MCP07x | server-initiated | elicitation, sampling, roots requests that need `inputRequired`; unsolicited `list_changed` |
| MCP08x | transport | stdout in a stdio server; 0.0.0.0; HTTP+SSE |
| MCP09x | extensions | 2025-11-25 experimental tasks; an MCP App tool naming an unregistered `ui://` resource |

Every id with its trigger: `${CLAUDE_SKILL_DIR}/../mcp-server/references/findings.md`.

## Decision rules

- **`MCP001` + `MCP011` + `MCP012` together are one problem**: a 1.x server
  turns modern clients away. Present them as one sentence before the details.
- **Dual is the target, not modern-only.** Never recommend `legacy: 'reject'`
  unless the user has said every client is modern; Alexa+ speaks 2025-11-25.
- **`MCP020` on a custom router is not fixed by upgrading the SDK alone**: the
  router reads the body before the SDK sees it. Point at `TS09` in the plan.
- **`MCP031` is a decision, not a bug**: `ttlMs: 0` is safe. Ask which lists
  are identical for every caller before suggesting `public`.
- **Spec claims carry their source.** Each finding prints one; quote it.
- **A newer `--target` than the rules know** is reviewed against the newest
  known revision and says so; read that revision's changelog for the rest.

## References

| Question | File |
|---|---|
| What 2026-07-28 changed, mapped to finding ids | [spec-2026-07-28.md](references/spec-2026-07-28.md) |
| The handshake era (2025-11-25) a legacy server implements | [spec-2025-11-25.md](references/spec-2025-11-25.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/lint_server.py <project> [--target rev] [--unit name] [--baseline r.json] [--json] [--strict]` | the static review | 0 no errors, 1 errors (or warnings under --strict), 2 nothing to review |

## Completion checklist

- [ ] `lint_server.py` ran and its counts were reported as printed.
- [ ] Each error was explained by its consequence (who cannot connect, what breaks), with its source.
- [ ] Handshake-only findings were summarised as one problem before the details.
- [ ] Nothing was edited; fixes were offered through `/mcp-server:mcp-migrate`.
- [ ] If a baseline was given, new and resolved findings were reported separately.
