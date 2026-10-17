---
name: mcp-verify
description: >-
  Live conformance probe of a deployed MCP endpoint over Streamable HTTP,
  stdlib urllib only: `server/discover` with the 2026-07-28 envelope
  (resultType, supportedVersions, capabilities, ttlMs/cacheScope, serverInfo),
  `tools/list` twice (cache hints, stable order, object inputSchema on every
  tool), header validation (mismatched and missing `Mcp-Method` must get 400 +
  -32020 HeaderMismatch), the 2025-11-25 handshake with `--legacy`
  (`initialize` then `tools/list`), unauthenticated requests (401,
  `WWW-Authenticate` with `resource_metadata`, Protected Resource Metadata
  reachable), a GET that should be 405, and p50/p95/max latency per method
  against a budget (500 ms by default, the Alexa+ round-trip figure). Never
  calls a tool. Use when asked to "test / probe / verify my MCP endpoint",
  "is the deployed server 2026-07-28 compliant", "does it still work for old
  clients", "how fast is it", "check the 401", after a deploy or a migration.
  Don't use for source review (use `/mcp-server:mcp-review`), for OAuth
  metadata in depth (use `/mcp-server:mcp-auth`), or for stdio servers (the
  probe speaks HTTP only).
argument-hint: "<mcp-url> [--legacy] [--token-env VAR] [--n 20] [--budget-ms 500]"
allowed-tools: Read, AskUserQuestion, Skill, Bash(python3 *)
---

# Probe a live MCP endpoint

The review says what the code intends; the probe says what the endpoint does —
behind the API gateway, the CDN, the Lambda cold start and the authorizer.
Both are needed, and they disagree more often than people expect.

**Probing costs something.** Every request reaches the user's server: Lambda
invocations, log lines, rate-limit budget, maybe production. Say which URL and
how many requests before running anything.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim; sibling scripts are at
`${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Ask what to probe** if the user has not said: the URL, staging or
   production, whether a token is needed and which environment variable holds
   it. Never ask for the token itself in the conversation.

2. **State the cost**: about `3 + 2n` modern requests plus `2 + n` legacy ones
   with `--legacy` (`--n 20` → about 65), and that no tool is called.

3. **Confirm** with `AskUserQuestion` (cost tier `probe`).

4. **Probe.**

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/probe.py <url> --legacy --token-env MCP_TOKEN --n 20 --budget-ms 500
   ```

   `--profile alexa` implies `--legacy`, makes the latency budget an error,
   and reports a bare 401 (no `WWW-Authenticate`, as Alexa+ asks) as a note
   citing `ALX050` rather than a `PRB041` warning. The GET check carries the
   token when one is given; an anonymous 401 there is "auth before method".
   `--json > probe.json` saves the report for `/mcp-server:mcp-alexa`
   (`lint_alexa.py --probe-report probe.json`) and for CI artifacts.

5. **Report**: the era the endpoint actually serves (`dual`, `modern`,
   `stateless`, `handshake`), the checks table, the latency table, then the
   findings by severity. Compare with the review's era when both exist and say
   plainly when they differ.

## Reading the result

| Era | Means |
|---|---|
| `dual` | discover and the legacy handshake both worked |
| `stateless` | discover worked, `initialize` was refused (`PRB012`) |
| `modern` | discover worked; legacy was not tested (no `--legacy`) |
| `handshake` | discover was refused (`PRB010`), legacy worked |
| `unknown` | neither worked; check the URL, auth and `PRB001` |

Exit 3 means the endpoint wants a token and none was given: the modern checks
did not run. Say so; it is not a pass.

## Decision rules

- **Read-only by construction**: discovery and listings only. Do not add a
  `tools/call` to "test properly" without the user naming the tool and saying
  it is safe.
- **Latency is p95, not the mean**, measured from this machine. Say where the
  probe ran; a laptop on Wi-Fi is not the Alexa+ cloud. Cold starts show up
  as the first sample and in `max`.
- **A 401 without `WWW-Authenticate`** is `PRB041` for the MCP spec — and what
  Alexa+ documents. Report both readings (see `ALX050`).
- **The probe does not fix anything.** Offer `/mcp-server:mcp-migrate` for code
  findings and `/mcp-server:mcp-ci` to repeat the probe after every deploy.

## References

| Question | File |
|---|---|
| Every request the probe sends and what passes | [probe-checks.md](references/probe-checks.md) |
| Latency: what is measured, budgets, where time goes | [latency-budget.md](references/latency-budget.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/probe.py <url> [--token-env VAR] [--n 20] [--legacy] [--budget-ms 500] [--profile generic\|alexa] [--json] [--strict]` | the live probe | 0 ok, 1 errors, 2 unreachable, 3 inconclusive |

## Completion checklist

- [ ] The URL and the request count were stated, and the user confirmed before probing.
- [ ] The token came from an environment variable and was never printed.
- [ ] The era the endpoint serves was reported, and compared with the review when one exists.
- [ ] Latency was reported as p50/p95/max per method against the budget, with where the probe ran.
- [ ] Exit 3 (inconclusive) was reported as such, not as a pass.
