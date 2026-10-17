# Upgrade playbook

## The pin

`.mcp-spec-pin` at the project root holds one line, the revision the project
targets:

```text
2026-07-28
```

`check_spec.py` compares against it; CI reviews against it (`MCP_TARGET` in the
generated workflow); moving it is a reviewed change. Without a pin file the
plugin's own target is used and reported as "plugin default".

## How the live revision is read

The versioning page states it in one sentence: "The **current** protocol
version is [**2026-07-28**](/specification/2026-07-28/)." `check_spec.py`
accepts the page as HTML or Markdown, strips tags, and reads the date after
"current protocol version is". If the sentence ever moves, it falls back to the
newest `/specification/YYYY-MM-DD` link on the page — and says where it read
from. Revisions are marked Draft, Current or Final; only Current matters here.

## What the SDK check compares

| Package | Registry | Checked against |
|---|---|---|
| `@modelcontextprotocol/sdk` (v1) | npm `/latest` | 1.32.0 |
| `@modelcontextprotocol/server` (v2) | npm `/latest` | 2.3.1 |
| `@modelcontextprotocol/node` | npm `/latest` | 2.1.1 |
| `@modelcontextprotocol/ext-apps` | npm `/latest` | 2.0.3 |
| `mcp` (Python) | PyPI JSON | 2.3.0 |

"Checked against" is what this plugin's rules and references were verified
with on 2026-10-05. A newer version is `UPG003`: read its release notes, then
re-run the review.

## The delta file

`--write-delta DIR` writes `DIR/delta-<date>.md`:

```markdown
# MCP upgrade delta 2027-03-31

- Pinned revision: `2026-07-28`
- Current revision on the versioning page: `2027-03-30` (read from https://...)

## Protocol: 2026-07-28 -> 2027-03-30

Read the changelog first: https://modelcontextprotocol.io/specification/2027-03-30/changelog

1. Re-review ... `lint_server.py <project> --target 2027-03-30 --baseline review-2026-07-28.json --json`
2. Plan only what the delta needs ...
3. Apply the auto steps after confirmation ...
4. Verify both eras: `probe.py <url> --legacy`.

## SDK releases newer than the plugin's checked versions
- `@modelcontextprotocol/server`: 2.3.1 -> 2.4.0
```

(Revision `2027-03-30` above is invented for illustration.)

## A full cycle, by hand

```bash
P=${CLAUDE_SKILL_DIR}/..
python3 $P/mcp-review/scripts/lint_server.py . --json > review-current.json      # baseline
python3 $P/mcp-upgrade/scripts/check_spec.py . --sdk --write-delta docs/mcp     # refresh + delta
python3 $P/mcp-review/scripts/lint_server.py . --target <new> --baseline review-current.json
python3 $P/mcp-migrate/scripts/plan_migration.py . --target <new> --out plan.json
python3 $P/mcp-migrate/scripts/apply_codemod.py . --plan plan.json --dry-run
python3 $P/mcp-verify/scripts/probe.py https://<host>/mcp --legacy --token-env MCP_TOKEN
echo <new> > .mcp-spec-pin                                                        # once clean
```

## On a schedule

A weekly scheduled job can run step 1 alone and open an issue when it exits 1;
everything after that involves decisions and belongs in a session with the
user.

## When the plugin itself is behind

The plugin's maintainers run the same loop on its own source corpus and
re-pin `lib/mcp_server_skills/__init__.py`. Until a plugin release knows a new
revision, its review is honest about reviewing against the newest one it knows.

---

Sources: https://modelcontextprotocol.io/specification/versioning (revision
states and the current-revision sentence, read 2026-10-05); npm registry and
PyPI metadata (read 2026-10-05); this plugin's `check_spec.py` and
`specpage.py`.
