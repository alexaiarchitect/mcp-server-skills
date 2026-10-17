---
name: mcp-server
description: >-
  Entry point for work on an existing MCP server (TypeScript or Python,
  Streamable HTTP first, stdio second). Discovers the project — SDK and
  version (pnpm catalogs and workspaces included), transports, the protocol
  era the code really implements (handshake-only, 2026-07-28-only or
  dual-version), auth, tools, hosting, CI, any Alexa+ addon.json — runs every
  review band once (MCP protocol, AUT authorization, ALX Alexa+), reports the
  counts, and routes to one focused skill with its cost. Use when the user
  says "MCP server", "upgrade my MCP server", "is my server compliant",
  "2026-07-28", "server/discover", "Mcp-Session-Id", "createMcpHandler",
  "FastMCP", "MCP SDK v2", "Alexa+ add-on", "what can this plugin do", or when
  the request spans several of those. Don't use when the request already names
  one task — go straight to `/mcp-server:mcp-discover`, `/mcp-server:mcp-review`,
  `/mcp-server:mcp-migrate`, `/mcp-server:mcp-verify`, `/mcp-server:mcp-auth`,
  `/mcp-server:mcp-alexa`, `/mcp-server:mcp-ci` or `/mcp-server:mcp-upgrade`.
  Don't use for building an MCP *client*, for configuring which MCP servers
  Claude Code loads (`.mcp.json`), or for writing a brand-new server from
  nothing.
argument-hint: "[project-dir] [--intent review|migrate|verify|auth|alexa|ci|upgrade]"
allowed-tools: Read, Grep, Glob, AskUserQuestion, Skill, Bash(python3 *)
---

# MCP servers — start here

The spec moved under every existing server on 2026-07-28: no `initialize`,
no sessions, a mandatory `server/discover`, headers that must match the body,
`resultType` on every result, cache hints on every list. A server built on a
1.x SDK still answers 2025-era clients and turns every modern one away. So
the first question is never "what should I change" but "which era does this
code actually speak, and who calls it" — and that is read from the files, not
guessed from `package.json`.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim in every command below; a sibling skill's scripts
are at `${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Discover.** Run it before saying anything about the project:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/route.py <project> [--intent alexa]
   ```

   Pass `--intent` when the user's words name a goal; it biases the
   recommendation and hides nothing. `--json` to branch on the bands.

2. **Report.** Show the `Found` block as printed: per server the SDK and
   version, the era with its meaning, transports, tool count, hosting, the
   authorization server; then findings per band and whether CI gates on
   anything. Never retype a version from memory.

3. **Options.** Offer the options the script printed, each with its cost
   tier, exactly one recommended. The tiers: `free` (reads files),
   `network` (fetches public pages or registries), `probe` (sends requests to
   *their* server — invocations, logs, rate limits, maybe production),
   `write` (edits the project), `deploy` (changes something outside it).

4. **Confirm.** Ask with `AskUserQuestion`, then invoke the chosen skill with
   the `Skill` tool. Nothing is written, probed or deployed before that
   answer. Full protocol: [interaction-protocol.md](references/interaction-protocol.md).

## Route by intent

| The user wants | Skill |
|---|---|
| an inventory: SDK, era, transports, auth, tools, hosting, CI | `/mcp-server:mcp-discover` |
| to know what is wrong against 2026-07-28 (or 2025-11-25) | `/mcp-server:mcp-review` |
| to move to SDK v2 / dual-version, with a plan and a diff | `/mcp-server:mcp-migrate` |
| to test a running endpoint: both eras, headers, 401, latency | `/mcp-server:mcp-verify` |
| OAuth 2.1 checked: PRM, challenges, audience, PKCE, DCR vs CIMD | `/mcp-server:mcp-auth` |
| an Alexa+ add-on: addon.json, voice tools, 500 ms, account linking | `/mcp-server:mcp-alexa` |
| a CI gate on the review and the probe | `/mcp-server:mcp-ci` |
| to know whether the spec or the SDKs moved, and what that means | `/mcp-server:mcp-upgrade` |

"Is my server OK?" starts with `mcp-review` when the code is here and
`mcp-verify` when only a URL is.

## The loop this plugin exists for

Every time the spec moves: **refresh** (`mcp-upgrade`: versioning page and
SDK registries) → **delta** (`delta-<date>.md`) → **re-review** against the new
revision with the old report as baseline (`mcp-review --baseline`) →
**migrate the delta** (`mcp-migrate`) → **verify** both eras (`mcp-verify`).
See [upgrade-loop.md](references/upgrade-loop.md).

## What to tell the user when they ask what this can do

1. **Find** every MCP server in a repo and say which protocol era it speaks.
2. **Review** it statically against a pinned revision, with ids they can grep.
3. **Migrate** it to dual-version (2026-07-28 + 2025-era) with a plan, a diff,
   and nothing written until they say so.
4. **Verify** the deployed endpoint: discover, legacy handshake, headers,
   cache hints, 401 + PRM, p50/p95 against a budget.
5. **Prepare** an Alexa+ add-on: manifest, voice-shaped tools, latency,
   account linking — and log every surprise in `docs/FRICTION-LOG.md`.
6. **Keep up**: one command says whether the spec moved and what to re-run.

## Ground rules

- **Never infer the era from a version number.** A 2.x SDK behind a custom
  router can still be handshake-only in practice; the script reads the code.
- **Dual-version is the default.** Alexa+ speaks 2025-11-25; modern-only
  turns it away. Say so whenever `legacy: 'reject'` comes up.
- **A probe is not free.** It invokes their server, maybe in production, with
  their token. Name the URL and the request count before running it.
- **Cite the source** for every protocol claim: each finding carries one.

## References

| Question | File |
|---|---|
| How every skill here behaves | [interaction-protocol.md](references/interaction-protocol.md) |
| Every finding id, by band, with severity and source | [findings.md](references/findings.md) |
| Handshake vs stateless vs dual, and who can call what | [eras.md](references/eras.md) |
| What each skill does, needs and costs | [capability-map.md](references/capability-map.md) |
| The upgrade loop, step by step | [upgrade-loop.md](references/upgrade-loop.md) |

## Scripts

| Command | Output | Exit codes |
|---|---|---|
| `scripts/route.py <project> [--intent name] [--target rev] [--json]` | inventory summary, findings per band, ranked options | 0 routed, 2 no server |

## Completion checklist

- [ ] `route.py` ran and its Found block was shown, not paraphrased.
- [ ] The era of each server was stated with what it means for who can connect.
- [ ] Options were offered with cost tiers, exactly one recommended, and the user chose.
- [ ] The chosen skill was invoked with `Skill`, not re-implemented here.
- [ ] Nothing was written, probed or deployed before the user answered.
