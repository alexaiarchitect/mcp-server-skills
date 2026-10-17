---
type: llm
---

PASS if the response:

- runs `check_spec.py` with the saved page and reports the pinned revision
  (`2026-07-28`, from `.mcp-spec-pin`) and the current one read from the page
  (`2027-03-30`);
- writes the delta file into `docs/mcp/` after showing what it will contain;
- names the next steps in order: re-review with `--target 2027-03-30` and a
  baseline, plan the migration of the delta, probe both eras;
- says the plugin's rules know revisions up to 2026-07-28, so the new
  changelog must be read for requirements the rules do not cover.

FAIL if it:

- claims to know what changed in 2027-03-30 without a changelog;
- moves `.mcp-spec-pin` without being asked;
- edits server code.
