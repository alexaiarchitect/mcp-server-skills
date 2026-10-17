---
type: llm
---

PASS if the response:

- reports findings produced by `lint_server.py`, by id, including `MCP011`
  (the per-request `WebStandardStreamableHTTPServerTransport` answers only the
  handshake), `MCP012` (no `server/discover`) and `MCP001` (SDK 1.x behind the
  2.x line);
- presents those three as one problem — modern clients are turned away — before
  the details;
- mentions `MCP020` (headers not validated by the custom router) and `MCP050`
  (-32002), each with its consequence and the source the script printed;
- recommends a dual-version migration as the next step and does not apply it.

FAIL if it:

- edits any file;
- lists problems from memory without running the review script;
- recommends a modern-only endpoint without saying it drops 2025-era clients.
