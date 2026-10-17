---
name: mcp-migrate
description: >-
  Plan and apply the migration of an existing MCP server to the 2026-07-28
  revision while still serving 2025-era clients (dual-version by default).
  Builds an ordered plan from the MCP0xx review — TypeScript SDK v1 to v2
  (`@modelcontextprotocol/sdk` to `@modelcontextprotocol/server`, the
  per-request `StreamableHTTPServerTransport` / `WebStandardStreamableHTTPServerTransport`
  pattern to `createMcpHandler(factory)`, raw shapes and `server.tool()` to
  `registerTool` + `z.object`, sessions out, -32002 to -32602, cache hints,
  elicitation to `inputRequired`, custom routers) or Python `mcp` 1.x to 2.x
  (`FastMCP` to `MCPServer`, transport settings to `run()`, injected
  `Context`, `MCPError`, `InputRequiredResult`) — marks each step auto
  (mechanical edit shown as a diff) or guided (before/after), records file
  hashes, and applies nothing until the user confirms. Use when asked to
  "migrate / upgrade my MCP server", "move to SDK v2", "support 2026-07-28",
  "make it dual-version", "replace StreamableHTTPServerTransport", "fix the
  review findings", or for the migrate-the-delta step of an upgrade. Don't
  use to find out what is wrong (use `/mcp-server:mcp-review`), to test a
  deployed server (use `/mcp-server:mcp-verify`), or to write a new server.
argument-hint: "[project-dir] [--unit name] [--modern-only]"
allowed-tools: Read, Grep, Glob, Edit, AskUserQuestion, Skill, Bash(python3 *)
---

# Migrate an MCP server to dual-version

A migration here is three artefacts in order: a **plan** (data, reviewed),
a **diff** (the mechanical part, reviewed), and **guided edits** (the parts
that need judgement, one at a time). Nothing is written before the user has
seen the plan and said yes; nothing is written to a file that changed after
the plan was made.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim; sibling scripts are at
`${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Baseline.** Save the review the migration starts from:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../mcp-review/scripts/lint_server.py <project> --json > review-before.json
   ```

2. **Plan** (reads only; `--out` saves the plan file, `--dry-run` only names it):

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/plan_migration.py <project> --out plan.json
   ```

   Report the steps table: id, auto/guided, title, files, and any step
   `notes` (TS01 names the peer dependencies it adds, and strict peer
   settings, `MIG004`). Then the write plan (files the auto steps edit).
   `MIG001` lists every guided step.

3. **Options**, each with its tier: show the diff (free, recommended), apply
   the auto steps (write), walk the guided steps (write), or run the official
   SDK codemod first (`TS00`, network + write).

4. **Confirm** with `AskUserQuestion`. Then show the diff before writing:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/apply_codemod.py <project> --plan plan.json --dry-run
   python3 ${CLAUDE_SKILL_DIR}/scripts/apply_codemod.py <project> --plan plan.json --apply
   ```

   `--apply` only after the user saw the diff and said yes. `--step TS01`
   limits a run to named steps.

5. **Guided steps**, one per turn: show the step's before (from the user's
   file) and after (from the plan and the reference), make the smallest edit,
   re-run the review with `--baseline review-before.json`. Finish with the
   `VERIFY` step's commands and offer `/mcp-server:mcp-verify`.

## Decision rules

- **Dual-version unless told otherwise.** TypeScript `createMcpHandler`
  defaults to `legacy: 'stateless'`; Python `mcp` 2.x always serves both.
  `--modern-only` plans `legacy: 'reject'`; say that it turns away every
  2025-era client, Alexa+ included, before accepting it.
- **Prefer the official codemod for v1→v2 renames** (`TS00`) when npm is
  reachable; this plugin's auto steps cover the dependency and the
  `McpServer` import only. Re-plan after running it.
- **The serving change (`TS03`) is guided on purpose.** On Lambda the first,
  faithful step is building the handler per invocation, so per-request auth
  and telemetry closures keep working; moving auth to `ctx.http.authInfo` is
  a second, separate change.
- **A custom pre-auth router stays** (`TS09`), but it must stop answering
  protocol questions itself: header validation, 405s and error bodies belong
  to the handler.
- **Never "fix" a finding by deleting the feature.** An elicitation becomes an
  `inputRequired` return, not a removed question.
- **`MIG002` means stop**: a file changed since planning. Re-plan; never force.

## References

| Question | File |
|---|---|
| TypeScript v1 → v2, step by step, with before/after | [ts-v1-to-v2.md](references/ts-v1-to-v2.md) |
| Python `mcp` 1.x → 2.x, step by step, with before/after | [python-v1-to-v2.md](references/python-v1-to-v2.md) |
| The plan file: schema, auto vs guided, hashes | [migration-plan.md](references/migration-plan.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/plan_migration.py <project> [--target rev] [--unit n] [--modern-only] [--out plan.json] [--dry-run] [--json]` | review + plan; reads only (`--out` saves the plan) | 0 planned, 2 no server / several without --unit |
| `scripts/apply_codemod.py <project> --plan plan.json [--dry-run \| --apply] [--step ID] [--json]` | diff of the auto steps; writes only with `--apply` | 0 ok, 1 a file was refused, 2 bad plan |

## Completion checklist

- [ ] A baseline review was saved before anything changed.
- [ ] The plan was shown (steps, auto/guided, write plan) before any edit.
- [ ] The diff was shown and the user confirmed before `--apply`.
- [ ] Modern-only was not chosen silently; its consequence for 2025-era clients was stated.
- [ ] Guided steps were applied one at a time, with the review re-run after each.
- [ ] The final review was compared with the baseline and the verify step was offered.
