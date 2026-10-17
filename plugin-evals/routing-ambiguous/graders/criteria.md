---
type: llm
---

PASS if the response:

- reports what the router script found in *this* project: the server at
  `apps/mcp-server`, `@modelcontextprotocol/sdk` 1.29.0 resolved from the pnpm
  catalog, era `handshake`, Lambda hosting, and finding counts per band;
- explains in plain words that 2026-07-28 clients cannot reach a handshake-only
  server while 2025-era clients still can;
- offers a small number of next steps, each naming a skill and a cost tier
  (free, network, probe, write, deploy), with exactly one recommended
  (planning the migration).

FAIL if it:

- gives generic MCP advice before running the router script;
- states an SDK version or protocol era it did not get from a script;
- edits files, probes a URL or runs a migration without being asked.
