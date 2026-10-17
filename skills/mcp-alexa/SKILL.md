---
name: mcp-alexa
description: >-
  Alexa+ add-on readiness for an existing MCP server — the ALX0xx overlay on
  top of the protocol and auth reviews. Validates `addon.json`
  (manifestVersion, distributionCountries, locales, name <= 30,
  shortDescription <= 123, fullDescription <= 4000, 3-4 distinct example
  phrases, HTTPS privacy and terms URLs, six light icon sizes, 600x900
  carousel, an HTTPS MCP endpoint, no developer jargon); checks the server
  for what Alexa+ adds: a 2025-11-25 Streamable HTTP endpoint (modern-only
  servers are unreachable), the 500 ms round-trip budget from a probe report,
  voice-shaped tools (intent names, no screen references, at most 5 options
  with pagination, a voice path for MCP App tools), the account-linking
  profile (401 handling, the WWW-Authenticate conflict with the MCP spec,
  client_credentials, no DCR/CIMD/OIDC/step-up), and a tool-signature lock
  because Alexa+ re-reads tools only on `alexa-ai deploy`. Logs every surprise
  to `docs/FRICTION-LOG.md`. Use when the user mentions "Alexa", "Alexa+",
  "add-on", "addon.json", "alexa-ai", "voice", "account linking", "500 ms",
  "certification", "web simulator". Don't use for generic MCP compliance (use
  `/mcp-server:mcp-review`) or OAuth beyond the Alexa+ profile (use
  `/mcp-server:mcp-auth`).
argument-hint: "[project-dir] [--probe-report probe.json]"
allowed-tools: Read, Grep, Glob, Edit, Write, AskUserQuestion, Skill, Bash(python3 *), Bash(alexa-ai *)
---

# Make an MCP server an Alexa+ add-on

Alexa+ consumes an ordinary remote MCP server, so readiness is mostly the
protocol review and the auth review — plus four things Alexa+ documents on
top: a 2025-11-25 endpoint, a 500 ms round trip, tools that work as voice, and
an account-linking profile that differs from the MCP spec in places. This
skill checks those, validates the manifest, and keeps a friction log, because
an onboarding produces surprises worth writing down while they are fresh.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim; sibling scripts are at
`${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Overlay review** (free):

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/lint_alexa.py <project> --profile alexa [--tools-from probe.json] \
       [--probe-report probe.json] [--endpoint https://.../mcp]
   ```

   Scope it to what Alexa+ lists: `--profile alexa` reads the deployment
   switch statically (`if (alexa)`, early returns, `register*Alexa*`,
   `alexa/` paths); `--tools-from probe.json` or `--tools a,b` is exact and
   wins; `--exclude-tools a,b` drops names. `discovered.units[].scope` says
   which tools were reviewed and why the others were left out.

   It runs the manifest checks too when it finds an `addon.json`. Without a
   probe report it says latency is unmeasured (`ALX031`); offer
   `/mcp-server:mcp-verify` with `--profile alexa --json > probe.json`.
   The manifest alone: `python3 ${CLAUDE_SKILL_DIR}/scripts/validate_addon.py <addon.json>`.

2. **Report** by area: protocol (ALX06x), latency (ALX03x), tools as voice
   (ALX04x), account linking (ALX05x), manifest (ALX00x-02x), tool lock
   (ALX080). Lead with errors.

3. **Options**, each with its tier: fix the manifest (write), reshape tool
   descriptions (write), measure latency (probe), record the tool lock
   (write), deploy to the development stage and test in the web simulator
   (deploy — the user runs `alexa-ai deploy`, or confirms it explicitly).

4. **Confirm** with `AskUserQuestion`. Deploy and submit are separate
   confirmations from any file edit.

5. **Log friction** as it happens, after the user agrees to keep a log:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/friction_log.py <project> --area alexa --step "account linking" \
     --expected "401 with WWW-Authenticate accepted" --actual "..." --severity major --dry-run
   ```

   Drop `--dry-run` once the row reads right.

## Decision rules

- **Dual-version is non-negotiable for Alexa+**: the toolkit supports
  2025-11-25. A modern-only endpoint (`ALX060`) is unreachable.
- **The 401 header conflict (`ALX050`) is reported, not resolved.** The MCP
  spec wants `WWW-Authenticate: Bearer resource_metadata=...`; the Alexa+
  quickstart says 401 *without* it and lists the header as unsupported.
  Confirm in the web simulator which one account linking accepts; log the
  answer in the friction log; only then change code.
- **Latency is measured, never assumed.** p95 from `probe.py`, from as close
  to the cloud as possible, cold starts included.
- **Voice shape is advice with evidence**: "at most 5 options", "within 500 ms"
  and "no screen references" are quoted from the docs; description wording is
  a suggestion the user approves.
- **Signatures are sticky.** Record `tools_lock.py --tools-from probe.json
  --write` (or `--profile alexa`) right after a deploy, so the lock holds
  exactly the tools Alexa+ lists; a later `ALX080` means "redeploy, and if certified, expect review".
- **What is not documented is not enforced**: the docs read for this plugin do
  not state a 30-second speech limit or a post-certification signature lock;
  say so if asked.

## References

| Question | File |
|---|---|
| Every Alexa+ requirement with its source and finding id | [alexa-requirements.md](references/alexa-requirements.md) |
| `addon.json`, field by field | [addon-json.md](references/addon-json.md) |
| Shaping tools for voice | [voice-tools.md](references/voice-tools.md) |
| The `alexa-ai` CLI flow and the web simulator | [alexa-ai-cli.md](references/alexa-ai-cli.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/lint_alexa.py <project> [--profile alexa] [--tools a,b \| --tools-from p.json] [--exclude-tools a,b] [--probe-report p.json] [--budget-ms 500] [--endpoint url] [--no-addon] [--json] [--strict]` | the overlay review | 0, 1 errors, 2 nothing to review |
| `scripts/validate_addon.py <addon.json\|dir> [--endpoint url] [--json] [--strict]` | manifest validation | 0, 1 errors, 2 no addon.json |
| `scripts/tools_lock.py <project> [--profile alexa] [--tools a,b \| --tools-from p.json] [--exclude-tools a,b] [--write] [--dry-run] [--json]` | record / compare tool signatures | 0 unchanged or written, 1 changed |
| `scripts/friction_log.py <project> --area a --step s --expected e --actual x [--severity] [--dry-run] [--json]` | append a row to `docs/FRICTION-LOG.md` | 0 |

## Completion checklist

- [ ] `lint_alexa.py` ran, and `validate_addon.py` findings were reported when an addon.json exists.
- [ ] Latency was reported from a probe report, or explicitly as unmeasured.
- [ ] The WWW-Authenticate conflict was presented as a conflict to test, not silently "fixed".
- [ ] No deploy or submit ran without its own explicit confirmation.
- [ ] Friction met during the session was logged (after the user agreed), one row per event.
