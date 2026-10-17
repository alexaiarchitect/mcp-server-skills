---
name: mcp-upgrade
description: >-
  The keep-upgrading loop for an MCP server: refresh (read the live MCP
  versioning page and the npm / PyPI releases of the TypeScript and Python
  SDKs), compare with the revision the project pins (`.mcp-spec-pin`) and the
  versions this plugin was checked against, write a dated
  `delta-<date>.md` with the changelog link and the exact next commands, then
  route to a re-review against the new revision with the previous report as
  baseline and a migration plan for only the delta, and finally a probe of
  both eras. UPG0xx findings: a newer revision is current, the page could not
  be read (inconclusive, nothing assumed), an SDK release newer than checked,
  a pin that is not a published revision. Use when asked "did the MCP spec
  change", "is there a new MCP revision", "keep my server up to date",
  "upgrade loop", "new SDK release", or on a schedule. Don't use for the
  review or the migration themselves (use `/mcp-server:mcp-review` and
  `/mcp-server:mcp-migrate`), or to upgrade unrelated dependencies.
argument-hint: "[project-dir] [--sdk] [--write-delta DIR]"
allowed-tools: Read, Grep, Glob, AskUserQuestion, Skill, Bash(python3 *)
---

# Keep an MCP server current

MCP ships dated revisions, and 2026-07-28 showed a revision can change the
wire. The question to ask on a schedule is small — "did anything move since we
pinned?" — and the answer has to be read from the source, not remembered.
This skill asks it, writes down the delta, and hands the rest of the loop to
the skills that do the work.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim; sibling scripts are at
`${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Refresh** (network: two to six public fetches, no credentials):

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/check_spec.py <project> --sdk
   ```

   Offline or behind a proxy: `--page-file versioning.md` (a saved copy of
   https://modelcontextprotocol.io/specification/versioning) and
   `--sdk-file versions.json`. Exit 1: newer revision; exit 3: could not read
   the page — report it, assume nothing.

2. **Report** pinned vs live revision, where the pin came from
   (`.mcp-spec-pin`, `--pinned`, or the plugin default), SDK versions observed
   vs checked, the UPG findings.

3. **Options**: write the delta file (write), re-review against the new
   revision with a baseline (free), plan the migration of the delta (free),
   probe both eras (probe). Recommend re-review when the revision moved,
   nothing when it did not.

4. **Confirm** with `AskUserQuestion`; show the delta first with `--dry-run`:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/check_spec.py <project> --sdk --write-delta docs/mcp --dry-run
   ```

5. **Hand over**: `/mcp-server:mcp-review` with `--target <new> --baseline
   <previous review JSON>`, then `/mcp-server:mcp-migrate --target <new>`,
   then `/mcp-server:mcp-verify --legacy`. Offer to move `.mcp-spec-pin` only
   after the re-review is clean.

## Decision rules

- **Read the new changelog before reviewing.** This plugin's rules know the
  revisions up to 2026-07-28; for a newer one the review runs the newest rules
  it has and says so. New requirements need new rules — say that plainly.
- **An SDK release is not a migration.** `UPG003` means "read the release
  notes"; a minor within the same major usually needs nothing but a re-review.
- **Moving the pin is a decision**, committed with the re-review that
  justifies it.
- **Never assume a revision from memory** when the page is unreachable: exit 3
  is the answer.

## References

| Question | File |
|---|---|
| The loop, the pin, and the delta file | [upgrade-playbook.md](references/upgrade-playbook.md) |

The loop in one page, shared with the router:
`${CLAUDE_SKILL_DIR}/../mcp-server/references/upgrade-loop.md`.

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/check_spec.py [project] [--pinned rev] [--page-file f] [--sdk] [--sdk-file f] [--write-delta DIR] [--dry-run] [--json]` | pinned vs live revision and SDK releases; optional delta file | 0 current, 1 newer revision, 2 usage, 3 inconclusive |

## Completion checklist

- [ ] `check_spec.py` ran and the pinned and live revisions were both stated, with where the pin came from.
- [ ] An unreadable page was reported as inconclusive, not as "no change".
- [ ] The delta was shown before it was written, and written only after confirmation.
- [ ] The next steps were handed to review, migrate and verify, not done here.
- [ ] Moving `.mcp-spec-pin` was left to the user after a clean re-review.
