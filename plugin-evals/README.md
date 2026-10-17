# Plugin eval cases

Behavioural tests for the **skills**, not for your MCP server. They live under
`plugin-evals/` (named in `plugin.json`'s `experimental.evals`). Each case runs
a prompt in a session with only this plugin loaded, and grades what the model
did.

```bash
claude plugin eval . --scaffold --allow-tools Bash Write Edit
claude plugin eval . --scaffold --allow-tools Bash Write Edit --case routing-ambiguous --runs 1
claude plugin eval . --scaffold --allow-tools Bash Write Edit --json results.json --threshold 0.8 --max-cost-usd 5
```

**Both flags are required, and neither is a default.**

- `--scaffold` runs each case's `scaffold_script`. It is opt-in because a
  scaffold script is author-supplied bash that runs as you. Without it, every
  case starts in an empty directory and fails for the wrong reason.
- `--allow-tools Bash Write Edit` is the operator grant for gated tools. Every
  case runs the plugin's scripts through `Bash`; some cases also write files.

Every run is a full `claude` child on your own credential; start with
`--runs 1` and a `--max-cost-usd` ceiling.

## What each case pins

| Case | Asserts |
|---|---|
| `routing-ambiguous` | a vague "the spec changed, where do I stand" goes to the router, which discovers before advising and recommends one costed step |
| `review-finds-mcp011` | the review reports the planted handshake-only transport as `MCP011` (with `MCP012`, `MCP001`) and edits nothing, with `Write`/`Edit` available |
| `migrate-dry-run` | "show me, don't change" produces a plan and a diff, and `--apply` never runs |
| `verify-reports-latency-budget` | the probe reports the era and p50/p95 against the 500 ms Alexa+ budget, against a local fake server, without calling a tool |
| `alexa-addon-invalid` | the manifest validator's errors are reported by id, ES availability is a warning, nothing is edited or deployed |
| `auth-missing-prm` | a server whose PRM route was removed is reported as `AUT002`, with the challenge and anonymous-method findings |
| `upgrade-delta` | a (synthetic) newer revision on a saved versioning page yields `UPG001`, a delta file, and a handover to review/migrate/verify |
| `ci-setup` | CI is linted, planned, written and linted again; the review gates on its exit code and no secret is written |

## Shared setup

Each case's `scaffold.sh` calls the shared `plugin-evals/scaffold.sh`:

```
scaffold.sh [<fixture>|none] [<mutation>] [stage-spec] [stage-server]
```

- **fixture** copies a project from `tests/fixtures/projects/`.
- **mutation** plants a defect: `no-prm` (remove the PRM route and builder),
  `pin` (write `.mcp-spec-pin`).
- **stage-spec** copies the synthetic versioning page to
  `./fixtures/versioning.html`; **stage-server** copies the fake MCP server to
  `./fixtures/fake_mcp.py`.

It writes `.scaffold/manifest.txt` and `.scaffold/protected.sha256` (a
checksum per file a case must not modify).

## How the "nothing happened" graders work

Cases that assert something did *not* happen use `regex` graders over
`target: trace` with `match: not_contains`: failing if any `Edit`/`Write` names a
protected file, or the codemod ran with `--apply`. Each grader says what it
proves and what it does not.

## Grader types in use

`llm` (a judged rubric), `tool_used` (the skill fired), `regex` over the
trace or a file, and `file_exists` (a deliverable landed).
