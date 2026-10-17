# `mcp-server` — Claude Code skills for existing MCP servers

Nine skills for auditing, migrating, verifying and keeping up to date the MCP
servers you already run — TypeScript and Python, Streamable HTTP first, stdio
second. Checked against MCP specification **2026-07-28** (current) and
**2025-11-25**, TypeScript SDK `@modelcontextprotocol/server` **2.3.1** /
`@modelcontextprotocol/sdk` **1.32.0**, Python SDK `mcp` **2.3.0** / **1.30.0**,
and the Alexa+ add-on documentation as of 2026-10-05.

The premise: on 2026-07-28 the protocol went stateless — no `initialize`, no
sessions, a mandatory `server/discover`, headers that must match the body,
`resultType` on every result, cache hints on every list — and a server on a
1.x SDK still answers 2025-era clients while turning every modern one away.
Which era a server *actually* speaks is a fact about its code, not its
`package.json`, and it changes again with every revision. This plugin reads
that fact, plans the move to **dual-version** (2026-07-28 per request, 2025-era
clients still served), proves it against the live endpoint, and repeats the
loop each time the spec moves.

## Install

Run these commands inside Claude Code:

```text
/plugin marketplace add alexaiarchitect/mcp-server-skills
/plugin install mcp-server@alexaiarchitect-mcp-server
```

To try a local checkout without installing:

```bash
claude --plugin-dir /path/to/mcp-server-skills
```

Then start with `/mcp-server:mcp-server` in any project, or go straight to the
skill you want.

## The skills

| Skill | Use it to |
|---|---|
| `/mcp-server:mcp-server` | discover a project, count findings per band, route to the right skill |
| `/mcp-server:mcp-discover` | inventory: SDK and version, transports, protocol era, auth, tools, extensions, hosting, CI |
| `/mcp-server:mcp-review` | review the code against a pinned revision (`MCP0xx`), with a baseline delta |
| `/mcp-server:mcp-migrate` | plan TS v1→v2 / Python v1→v2 to dual-version; show the diff; apply only after you confirm |
| `/mcp-server:mcp-verify` | probe a live endpoint: discover, legacy handshake, headers, results, 401 + PRM, p50/p95 |
| `/mcp-server:mcp-auth` | review OAuth 2.1 resource-server behaviour (`AUT0xx`) and the live metadata documents |
| `/mcp-server:mcp-alexa` | Alexa+ add-on readiness (`ALX0xx`): addon.json, voice-shaped tools, 500 ms, account linking, friction log |
| `/mcp-server:mcp-ci` | a plain workflow that gates on the review and the probe; lint existing workflows |
| `/mcp-server:mcp-upgrade` | did the spec or the SDKs move? write the delta and hand over to review, migrate, verify |

## How they behave

Every skill follows the same five steps: **discover** with a script, **report**
what it found, **offer options** with their cost, **confirm** with a question,
then **act and verify**. Nothing is written, probed or deployed before you
answer.

Costs are stated up front as a tier: `free` (reads files), `network` (fetches
public pages or registries), `probe` (sends requests to *your* server —
invocations, logs, rate limits, maybe production), `write` (edits the
project), `deploy` (changes something outside it, such as `alexa-ai deploy`).

Findings carry stable ids in bands — `DSC` discovery, `MCP` protocol, `AUT`
authorization, `ALX` Alexa+, `PRB` probe, `MIG` migration, `CI` workflows, `UPG`
upgrade — each with its severity, fix and the page it comes from
(`skills/mcp-server/references/findings.md`).

## The upgrade loop

```
refresh ──► delta ──► re-review ──► migrate the delta ──► verify
check_spec   delta-    lint_server     plan_migration       probe.py
  .py        <date>.md --baseline      + apply_codemod      --legacy
```

Pin the revision you target in `.mcp-spec-pin`; `/mcp-server:mcp-upgrade`
compares it with the live versioning page and the npm / PyPI releases, writes
`delta-<date>.md` with the changelog link and the next commands, and hands
over. The same five steps run every time the spec moves.

## Four things worth knowing before you start

**Dual-version is the default, on purpose.** TypeScript `createMcpHandler`
defaults to `legacy: 'stateless'` and Python `mcp` 2.x always serves both
eras. Modern-only (`legacy: 'reject'`) turns away every 2025-era client —
including Alexa+, whose MCP toolkit speaks 2025-11-25.

**The probe is read-only but not free.** It sends discovery and listing
requests (never `tools/call`) to the URL you give it, with the token from an
environment variable you name; `--n 20 --legacy` is about 65 requests.

**Two documents disagree about the 401.** The MCP authorization spec wants
`WWW-Authenticate: Bearer resource_metadata=...`; the Alexa+ quickstart says
401 *without* it. The plugin reports the conflict (`ALX050`) and asks you to
settle it in the Alexa+ web simulator instead of picking a side for you.

**Migrations are plans before they are edits.** `plan_migration.py` records a
hash of every file it will touch; `apply_codemod.py` shows a diff by default,
writes only with `--apply`, and refuses any file that changed since the plan.
The parts that need judgement — moving a Lambda handler to `createMcpHandler`,
replacing an elicitation with `inputRequired` — are guided steps with a
before and an after, never silent rewrites.

## New in 0.2.0

Fixes for every friction logged on the plugin's first real-world use (see
[CHANGELOG.md](CHANGELOG.md)). Flags that changed:

| Script | New flags / behaviour |
|---|---|
| `lint_alexa.py`, `tools_lock.py` | `--profile alexa`, `--tools a,b`, `--tools-from probe.json`, `--exclude-tools a,b`: review and lock only the tools Alexa+ lists |
| `check_prm.py --alexa` | `--token-iss URL`; no CIMD advice (`AUT031`); new `ALX054` (PRM scopes vs `mcp:*`) and `ALX055` (AS `issuer` vs token `iss`) |
| `probe.py` | `--profile alexa` lowers a bare 401 to a note citing `ALX050`; the GET check sends the token; `discovered.tool_names` |
| `plan_migration.py` | TS01 adds ext-apps 2.x peers and reports strict peer dependencies (`MIG004`); TS03/TS07 carry the verified SSE and `cacheHints` details |
| every finding (`--json`) | `file` and `line` beside `path` / `locator` |
| `route.py` | the closing summary adds up the band table; gaps are counted |

## Requirements

Python 3.10+ for the plugin's scripts, which are **standard library only**:
TypeScript is read with a comment- and string-aware scanner, Python with
`ast`, HTTP with `urllib`. Nothing imports an MCP SDK, Node, or the project
under review, so a review works on a server that does not build — which is
when a migration needs it.

Optional, outside the plugin: `npx` for the official TypeScript codemod
(`TS00`), the `alexa-ai` CLI for Alexa+ deploys.

## Layout

```
.mcp-spec-pin                 the revision you target (one line, optional)
addon.json                    Alexa+ add-on manifest (optional)
docs/FRICTION-LOG.md          appended by friction_log.py
docs/alexa-tools.lock.json    written by tools_lock.py --write
.github/workflows/mcp-conformance.yml   written by gen_workflow.py
```

## Development

```bash
python3 -m pytest -q                                                # the plugin's own tests
claude plugin validate . --strict
claude plugin eval . --scaffold --allow-tools Bash Write Edit --runs 1   # skill-level cases in plugin-evals/
```

Scripts are exercised as subprocesses, the way a skill runs them. The probe is
tested against an in-process fake server (`tests/fixtures/servers/fake_mcp.py`)
in four shapes — dual, legacy-only, lax, modern-only — so the suite needs no
network and no credentials.

## Attribution

Protocol behaviour is cited from the MCP specification at
`modelcontextprotocol.io`; SDK behaviour from the TypeScript and Python SDK
documentation; Alexa+ requirements from `developer.amazon.com`; Cognito and
AgentCore from `docs.aws.amazon.com`. See `THIRD_PARTY_NOTICES.md`. Fixtures use
a fictional library ("bookshelf") domain; `tests/fixtures/projects/vault_alexa`
is an anonymized copy of a real Alexa+ server (names, domains and product
strings replaced).
