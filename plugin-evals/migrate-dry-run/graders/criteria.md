---
type: llm
---

PASS if the response:

- shows the plan from `plan_migration.py`: steps with ids, auto vs guided, and
  the files each touches (`pnpm-workspace.yaml`, `apps/mcp-server/package.json`,
  `apps/mcp-server/src/server.ts`, `apps/mcp-server/src/handler.ts`);
- shows the unified diff of the auto steps from `apply_codemod.py` without
  `--apply` (the `@modelcontextprotocol/sdk` catalog entry becoming
  `@modelcontextprotocol/server` 2.x, ext-apps 2.x, the `McpServer` import);
- explains the guided serving step (`TS03`: per-request transport to
  `createMcpHandler`) and that the default stays dual-version;
- asks before applying anything.

FAIL if it:

- writes or edits any project file, or runs `apply_codemod.py --apply`;
- claims the migration is done.
