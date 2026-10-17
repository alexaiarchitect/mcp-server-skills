---
type: llm
---

PASS if the response:

- runs `lint_workflows.py` first and reports that no workflow runs the MCP
  review (`CI001`) or the probe (`CI002`);
- shows the write plan (the workflow path, the `MCP_URL` variable, the optional
  `MCP_TOKEN` secret) before writing;
- writes the workflow with `gen_workflow.py` and lints it afterwards;
- explains that the PR job is free and gates on `lint_server.py`'s exit code,
  the probe runs only after deploys, and exit 3 becomes a warning.

FAIL if it:

- writes a token or key literal into the workflow;
- masks the gate with `|| true` or `continue-on-error`;
- runs the probe against a real endpoint during setup.
