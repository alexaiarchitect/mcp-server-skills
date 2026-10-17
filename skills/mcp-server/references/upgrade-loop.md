# The upgrade loop

MCP revises its specification in dated revisions, and a revision can change
the wire (2026-07-28 removed `initialize`). The loop below is what to run every
time one appears, and whenever an SDK major lands. It is the same five steps
every time, so it can be scheduled and gated.

```
refresh corpus ──► compute delta ──► re-review ──► migrate the delta ──► verify
 check_spec.py      delta-<date>.md   lint_server     plan_migration       probe.py
 (network)          (write, asked)    --baseline       + apply_codemod     --legacy
```

## 1. Refresh

```bash
python3 ${CLAUDE_SKILL_DIR}/../mcp-upgrade/scripts/check_spec.py <project> --sdk
```

Reads the "current protocol version" from the versioning page and the newest
npm and PyPI releases, and compares them with the pin (`.mcp-spec-pin` in the
project, else the plugin's target). Exit 1 means a newer revision is current;
exit 3 means the page could not be read — nothing is assumed.

## 2. Delta

```bash
python3 ${CLAUDE_SKILL_DIR}/../mcp-upgrade/scripts/check_spec.py <project> --sdk --write-delta docs/mcp --dry-run
```

The delta names the old and new revision, links the new changelog, lists SDK
releases newer than the ones this plugin was checked against, and spells out
the next three commands. Read the changelog before anything else: the rules in
this plugin know the revisions up to the one they were written for, and a
brand-new revision may need new rules.

## 3. Re-review against the new revision, with a baseline

```bash
python3 .../lint_server.py <project> --target 2026-07-28 --json > review-2026-07-28.json   # before
python3 .../lint_server.py <project> --target <new> --baseline review-2026-07-28.json
```

The baseline adds `delta.new` / `delta.resolved` / `delta.unchanged` to the
report. "New" is the work; "unchanged" is debt the user already knew about.

## 4. Migrate the delta

```bash
python3 .../plan_migration.py <project> --target <new> --out plan.json
python3 .../apply_codemod.py <project> --plan plan.json --dry-run     # show the diff
python3 .../apply_codemod.py <project> --plan plan.json --apply       # after confirmation
```

Guided steps are applied by hand, one at a time, re-running the review after
each.

## 5. Verify both eras

```bash
python3 .../probe.py https://<host>/mcp --legacy --token-env MCP_TOKEN --budget-ms 500
```

Dual-version is done when both `server/discover` and the legacy `initialize`
pass, headers are enforced, results carry `resultType` and cache hints, and
latency is inside the budget.

## Pinning

Write the revision you target to `.mcp-spec-pin` (one line, `YYYY-MM-DD`) and
commit it. The loop then compares against *your* decision, not the plugin's
default, and moving the pin is a reviewed change.

---

Sources: https://modelcontextprotocol.io/specification/versioning (revision
policy, read 2026-10-05); this plugin's `check_spec.py`, `lint_server.py`,
`plan_migration.py`, `apply_codemod.py` and `probe.py`.
