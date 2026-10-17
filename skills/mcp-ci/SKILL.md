---
name: mcp-ci
description: >-
  Put an MCP server's conformance into CI as plain workflow steps that gate on
  exit codes: the static review (`lint_server.py --target <revision>`) on every
  pull request, and the live probe (`probe.py --legacy --budget-ms`) against
  the deployed endpoint after each push to the default branch, with the
  token from a repository secret, exit 3 (inconclusive) turned into a visible
  warning rather than swallowed, reports uploaded as artifacts, and the plugin
  fetched at a pinned tag. Optional Alexa+ manifest validation. Also lints
  existing workflows: no review step, no probe, credential literals, masked
  exit codes (`|| true`, `continue-on-error`), unpinned plugin refs. Use when
  asked to "add CI for my MCP server", "gate pull requests on MCP
  compliance", "run the probe after deploy", "check my workflows". Don't use
  for the review itself (use `/mcp-server:mcp-review`), for a one-off probe
  (use `/mcp-server:mcp-verify`), or for deployment pipelines in general.
argument-hint: "[repo-dir] [--alexa] [--budget-ms 500]"
allowed-tools: Read, Grep, Glob, AskUserQuestion, Skill, Bash(python3 *)
---

# Gate CI on MCP conformance

A spec revision or an SDK bump can turn a working server into one modern
clients cannot reach, and nothing in a normal test suite notices. Two plain
steps catch it: the static review on every pull request (free, seconds) and
the live probe after every deploy (probe tier: it calls the deployed server).
Both gate on the scripts' exit codes, which mean the same thing everywhere:
0 ok, 1 findings, 2 usage, 3 inconclusive.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim; sibling scripts are at
`${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Look at what exists** (free):

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/lint_workflows.py <repo>
   ```

2. **Show the write plan** — the workflow file, its path, the secret and the
   variable it needs:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/gen_workflow.py <repo> [--alexa] [--budget-ms 500] --dry-run
   ```

3. **Options**: write the workflow (write, recommended when no gate exists),
   add only the review job (write), or fix findings in an existing workflow
   (write).

4. **Confirm** with `AskUserQuestion`, then write it (`--force` only to replace
   an existing file the user named) and lint it:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/gen_workflow.py <repo> [--alexa]
   python3 ${CLAUDE_SKILL_DIR}/scripts/lint_workflows.py <repo>
   ```

5. **Tell the user what to set**: the `MCP_URL` repository variable (enables
   the probe job) and, if the endpoint needs one, the `MCP_TOKEN` secret — a
   token for a test identity, never a personal one.

## Decision rules

- **The PR job is free and must stay free**: review only, no network calls to
  the server, no secrets.
- **The probe job runs where the deploy is**: after pushes to the default
  branch or manually, never on pull requests from forks (it holds a secret).
- **Exit 3 is said out loud**: a warning annotation, not a silent pass and not
  a red build.
- **Pin the plugin** (`--ref v0.2.0`); `CI005` flags `main`.
- **The latency budget fails the build only with `--alexa`** (`--profile
  alexa`); otherwise it is a warning, because shared runners are noisy.

## References

| Question | File |
|---|---|
| The generated workflow, line by line, and how to adapt it | [github-actions.md](references/github-actions.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/gen_workflow.py <repo> [--unit p] [--target rev] [--budget-ms n] [--alexa] [--ref tag] [--out path] [--force] [--dry-run] [--json]` | writes the workflow | 0 written/printed, 1 exists without --force, 2 usage |
| `scripts/lint_workflows.py <repo> [--json] [--strict]` | CI001-CI005 | 0, 1 errors, 2 not a directory |

## Completion checklist

- [ ] Existing workflows were linted before anything was written.
- [ ] The write plan (file, secret, variable) was shown and the user confirmed.
- [ ] The generated workflow was linted after writing, and its findings reported.
- [ ] No credential literal was written; the token comes from a secret.
- [ ] The user was told how exit 3 is handled and which variable enables the probe.
