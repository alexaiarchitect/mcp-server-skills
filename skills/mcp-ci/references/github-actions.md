# The generated GitHub Actions workflow

`gen_workflow.py` writes `.github/workflows/mcp-conformance.yml`. Every line is
plain shell around this plugin's scripts; there is no marketplace action and no
model call. This file explains it so it can be adapted.

## Triggers and permissions

```yaml
on:
  pull_request:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
env:
  MCP_SKILLS_REF: v0.2.0      # plugin tag; pin it (CI005)
  MCP_TARGET: "2026-07-28"     # the revision you review against (move it with the upgrade loop)
```

## Job `review` — every PR and push, free

```yaml
- name: Fetch the mcp-server plugin (pinned)
  run: git clone --depth 1 --branch "$MCP_SKILLS_REF" https://github.com/alexaiarchitect/mcp-server-skills.git .mcp-skills
- name: MCP review
  run: |
    set +e
    python3 .mcp-skills/skills/mcp-review/scripts/lint_server.py "apps/mcp-server" --target "$MCP_TARGET" --json > mcp-review.json
    code=$?
    python3 .mcp-skills/skills/mcp-review/scripts/lint_server.py "apps/mcp-server" --target "$MCP_TARGET" >> "$GITHUB_STEP_SUMMARY"
    exit $code
```

`set +e` lets the markdown reach the job summary; `exit $code` keeps the gate.
Add `--strict` to fail on warnings too. With `--alexa` a step runs
`validate_addon.py` on the manifest.

## Job `probe` — after deploys, probe tier

```yaml
probe:
  if: github.event_name != 'pull_request' && vars.MCP_URL != ''
  needs: review
  steps:
    - name: Probe
      env:
        MCP_TOKEN: ${{ secrets.MCP_TOKEN }}
      run: |
        set +e
        args=(--legacy --n 20 --budget-ms 500)
        if [ -n "$MCP_TOKEN" ]; then args+=(--token-env MCP_TOKEN); fi
        python3 .mcp-skills/skills/mcp-verify/scripts/probe.py "${{ vars.MCP_URL }}" "${args[@]}" --json > mcp-probe.json
        code=$?
        if [ "$code" = 3 ]; then
          echo "::warning::MCP probe inconclusive (exit 3)"; exit 0
        fi
        exit $code
```

- **Never on pull requests**: the job holds a secret and calls a real server.
- **`MCP_URL`** (repository variable) switches it on; **`MCP_TOKEN`** (secret)
  is optional — without it an auth-protected endpoint yields exit 3, which is
  reported as a warning.
- The token is passed by environment variable name; `probe.py` never prints it.
- If the deploy happens in another workflow, call this job from there
  (`workflow_call`) or trigger on `workflow_run` so the probe sees the new
  version, not the old one.

## Exit codes the gate relies on

| Code | Review | Probe | Workflow |
|---|---|---|---|
| 0 | no errors | no errors | pass |
| 1 | errors | errors (latency only with `--profile alexa`) | fail |
| 2 | no server found | unreachable | fail |
| 3 | — | needs a token | warning, pass |

## What `lint_workflows.py` checks

| Id | Finds |
|---|---|
| CI001 | no workflow runs `lint_server.py` |
| CI002 | no workflow runs `probe.py` |
| CI003 | a bearer token or JWT literal in a workflow |
| CI004 | `|| true` after an MCP gate, or `continue-on-error: true` near one |
| CI005 | the plugin cloned from `main`/`master`/`HEAD` or without `--branch` |

## Adapting it

- Monorepo with several servers: one review step per `--unit`, or a matrix.
- Other CI systems: the two `run:` blocks are portable shell; keep `set +e` /
  `exit $code` and the exit-3 branch.
- Moving the target revision is a reviewed change to `MCP_TARGET` (or to
  `.mcp-spec-pin`), done after the upgrade loop's re-review.

---

Sources: this plugin's `gen_workflow.py` and `lint_workflows.py`; GitHub Actions
workflow syntax per https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions
(not re-read for this plugin; the template uses only long-standing keys).
