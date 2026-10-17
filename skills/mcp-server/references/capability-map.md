# What each skill does, needs and costs

| Skill | Does | Needs | Cost tier | Writes |
|---|---|---|---|---|
| `mcp-server` | discovers, counts findings per band, routes | a directory | free | nothing |
| `mcp-discover` | inventory: SDK, era, transports, auth, tools, extensions, hosting, CI | a directory | free | nothing |
| `mcp-review` | `MCP0xx` static review against a pinned revision; baseline delta | a directory | free | nothing |
| `mcp-migrate` | plan (TS v1→v2, Python v1→v2, dual-version), diff, apply auto steps | a directory | free to plan, write to apply | the files in the write plan, after confirmation |
| `mcp-verify` | live probe: discover, legacy handshake, headers, results, 401 + PRM, p50/p95 | a URL (and a token if the server wants one) | probe | nothing |
| `mcp-auth` | `AUT0xx` static review; live PRM and authorization server metadata | a directory and/or a URL | free / network | nothing |
| `mcp-alexa` | `ALX0xx` overlay, addon.json validator, tool lock, friction log | a directory; a probe report for latency | free; write for the lock and the log; deploy for `alexa-ai` | `docs/alexa-tools.lock.json`, `docs/FRICTION-LOG.md`, after confirmation |
| `mcp-ci` | a workflow that gates on review + probe exit codes; workflow lint | a repository | write | `.github/workflows/mcp-conformance.yml` |
| `mcp-upgrade` | versioning page and SDK registries vs the pin; delta file; next commands | network (or saved copies) | network | `delta-<date>.md`, when asked |

## Scripts, by skill

| Skill | Script | Reads | Writes |
|---|---|---|---|
| mcp-server | `route.py` | project | — |
| mcp-discover | `discover.py` | project | — |
| mcp-review | `lint_server.py` | project, optional baseline JSON | — |
| mcp-migrate | `plan_migration.py` | project | `--out plan.json` |
| mcp-migrate | `apply_codemod.py` | project, plan | planned files, only with `--apply` |
| mcp-verify | `probe.py` | a URL | — |
| mcp-auth | `lint_auth.py` | project | — |
| mcp-auth | `check_prm.py` | a URL or saved documents | — |
| mcp-alexa | `validate_addon.py` | addon.json | — |
| mcp-alexa | `lint_alexa.py` | project, optional probe JSON | — |
| mcp-alexa | `tools_lock.py` | project | `docs/alexa-tools.lock.json` with `--write` |
| mcp-alexa | `friction_log.py` | — | `docs/FRICTION-LOG.md` (append) |
| mcp-ci | `gen_workflow.py` | project | the workflow file |
| mcp-ci | `lint_workflows.py` | `.github/workflows` | — |
| mcp-upgrade | `check_spec.py` | versioning page, registries | `delta-<date>.md` with `--write-delta` |

Every script takes `--json`; every script that writes takes `--dry-run`.

## Exit codes, everywhere

| Code | Meaning |
|---|---|
| 0 | no errors |
| 1 | errors (or warnings under `--strict`); for `check_spec.py`, a newer revision is current |
| 2 | usage or environment: bad path, no server found, unreachable URL |
| 3 | inconclusive: the server wanted a token, a page could not be read |

Exit 3 is separate on purpose: "the probe could not authenticate" is a
different problem from "the server is non-conformant", and a CI gate should be
able to say so.

## What none of them do

- Run the server, install its dependencies, or import its code.
- Call a tool on the user's server (the probe lists; it never calls).
- Deploy: `alexa-ai deploy` and cloud changes are commands the user runs, or
  confirms, explicitly.

---

Sources: the scripts' own `--help` texts in this plugin; exit-code contract in
`lib/mcp_server_skills/report.py`.
