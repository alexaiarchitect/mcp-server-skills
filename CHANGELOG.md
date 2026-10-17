# Changelog

## 0.2.0 — 2026-10-05

Every friction logged during the plugin's first real-world use on an Alexa+
MCP server (friction log rows F01–F22; the rows that belonged to other plugins
are not listed here) is resolved below. Each fix has a regression test in
`tests/skills/test_friction_regressions.py` (named `test_fNN_*`), replayed on
`tests/fixtures/projects/vault_alexa`, an anonymized copy of that server.

| # | Friction | Resolution |
|---|---|---|
| F01 | `route.py` printed the band table and then `0 error(s), 0 warning(s)` | **Fixed.** `GapReport.rollup` carries counts a report summarises but does not list; the router fills it from `findings_by_band`, so the JSON `summary` and the closing line add up the table ("… across the review bands above"). Gaps are counted too (`summary.gaps`, "N gap(s)"). |
| F02 | `file` / `line` were null for every finding | **Fixed.** Every finding's JSON carries `file` (= `path`) and an integer `line`: parsed from a `line N` locator, or looked up in the file for a named locator (MCP001/002/004/005 now point at the dependency's line in `package.json`). Findings about something *absent* (MCP012 "nothing answers `server/discover`") still have no line, by nature. |
| F03 | scripts left `__pycache__` in the plugin | **Fixed.** Every script sets `sys.dont_write_bytecode = True` before importing the library; the test conftest does the same and pytest runs with `-p no:cacheprovider`. A hygiene test enforces the line in every script; a regression test runs scripts from a copy of the plugin and finds no `__pycache__`. |
| F04 | TS01 bumped ext-apps to 2.x without its required peers; `strict-peer-dependencies` unseen | **Fixed.** TS01 reads the target release's `peerDependencies` / `peerDependenciesMeta` (an installed 2.x copy first, else the pinned table: ext-apps 2.0.3 requires `@modelcontextprotocol/client` and `/core` ^2.0.0) and adds the missing ones where the dependency lives — catalog entry + `"catalog:"`, or a range in `package.json`. `.npmrc` / `pnpm-workspace.yaml` strict-peer settings are read; the plan carries step `notes` and `MIG004` (warn when strict and peers were missing). |
| F05 | cache-hint option shape marked **U** | **Fixed.** Promoted to **V (source)** from the SDK 2.3.1 source (`server.ts` `ServerOptions.cacheHints`, `resultCacheHints.ts` `CACHEABLE_RESULT_METHODS`); TS07's `after` is now the exact snippet and `ts-v1-to-v2.md` documents the type. |
| F06 | TS03 did not say the legacy leg answers SSE | **Fixed.** TS03's `why` states it, and its `after` shows the `isLegacyRequest` + `WebStandardStreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true })` composition for buffered hosts; `ts-v1-to-v2.md` explains `responseMode` shapes modern exchanges only (verified in `createMcpHandler.ts`). |
| F07 | `--profile alexa` reported the Alexa-correct bare 401 as warning PRB041 | **Fixed.** Under `--profile alexa` a 401 without `WWW-Authenticate` is PRB041 at **info**, citing the ALX050 conflict; the generic profile is unchanged. |
| F08 | the GET check was sent without the token | **Fixed.** The GET carries the token when one was given; an anonymous GET answered 401 is recorded as "401 (auth before method)", not PRB051. The fake server gained an `auth_get` shape to test both. |
| F09 | `lint_alexa.py` reviewed every `registerTool`, both profiles | **Fixed.** `--profile alexa` reads profile gating statically (enclosing `if (alexa)`, an earlier `if (alexa) { … return }`, `register*Alexa*` functions, `alexa/` paths); `--tools a,b` / `--tools-from probe.json` (probe `discovered.tool_names`, a `tools/list` result, or a list; gateway `target___` prefixes stripped) is exact and wins; `--exclude-tools`. `discovered.units[].scope` lists what was reviewed and why the rest was left out. A `WWW-Authenticate` sent only on a guarded branch is ALX050 at info under the profile, or when the probe report shows the endpoint answered a bare 401. |
| F10 | ALX041 flagged the voice-correct fixed page of five | **Fixed.** A list tool passes with a `limit` bounded at 5, a server-side page size ≤ 5 in the handler (`limit: 5`, `limit: MAX_VOICE_OPTIONS` resolved through `const X = N` anywhere in the unit), or a `page_token`/`cursor` input and no `limit` input. The message says how it judged ("server-side page size PAGE = 10"). |
| F11 | AUT021 was an error on a token-endpoint façade relaying HTTP Basic | **Fixed.** AUT021 now classifies the relay: a fetch to a token endpoint behind a `^Basic ` check is **info** (client authentication per RFC 6749 §2.3.1, allowed); a relay to a token endpoint with no scheme check is a qualified **warn** saying which header class to forward; any other forwarded `Authorization` stays an **error** ("a bearer access token"). |
| F12 | MCP032 flagged `cacheScope: 'public'` on `server/discover` | **Fixed.** A public hint whose key is `server/discover` (static server info) is not raised; other public hints on an authenticating server still are, with their line. |
| F21 | `alexa-ai-cli.md` lacked account linking and PRM-driven scopes | **Fixed.** The reference has `alexa-ai configure-account-linking --addon-id … --stage development --client-id …` (secret via masked prompt / `ALEXA_CLIENT_SECRET`), the PRM `scopes_supported` discovery, and records that no page names the npm package (**U**). The conflict with the authentication page's fixed `mcp:*` scopes is a new finding, `ALX054` (`check_prm.py --alexa`; warn when PRM lists no scopes). |
| F22 | `tools_lock.py` locked both profiles; `check_prm.py --alexa` recommended CIMD and missed the issuer façade | **Fixed.** `tools_lock.py` takes the same scope flags as `lint_alexa.py` and records the scope in the lock. Under `--alexa`, AUT031 (CIMD) is not raised, and `ALX055` reports an AS metadata `issuer` that is not the tokens' `iss` (warn with `--token-iss`; info when inferred from a `jwks_uri` on another origin). |

Also, from the independent review:

- `spec-2026-07-28.md`: rows 6 and 8 now agree with the changelog
  (re-read 2026-10-05): major 8 defines only `complete` and `input_required`;
  `"task"` is the tasks extension's own value, returned only to clients that
  declared the extension. `probe.py` accepts extension result types.
- The verified-facts ledger (maintainer working notes, not shipped): every
  **V** row names its source as a full URL (no more "same", "changelog major
  3", "quickstart"); new rows for the account-linking page, the ext-apps peers
  and the legacy-leg transport. A test checks the URL rule when the ledger is
  present.

New finding ids: `MIG004`, `ALX054`, `ALX055` (catalogued in
`skills/mcp-server/references/findings.md`). Tests: 415 → 462.

## 0.1.0 — 2026-10-05

First release.
