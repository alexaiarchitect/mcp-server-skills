# Test fixtures

All projects use a fictional "bookshelf" library domain; `projects/vault_alexa` is an anonymized copy of a real server.

| Path | What it is | Built to trigger |
|---|---|---|
| `projects/ts_v1_lambda` | pnpm monorepo, `@modelcontextprotocol/sdk` 1.29.0 via `catalog:`, a Lambda handler that builds a `WebStandardStreamableHTTPServerTransport` per request behind a body-inspecting auth gate, PRM in a `workspace:*` auth package, an MCP App tool. Modelled on the structure of a real Lambda-hosted vault server, not its code | MCP001 MCP002 MCP011 MCP012 MCP015 MCP020 MCP031 MCP050; AUT011 AUT012; ALX041 ALX042 ALX043 ALX050 ALX053 |
| `projects/py_v1_fastmcp` | `mcp` 1.x FastMCP over Streamable HTTP, constructor transport settings, `ctx.elicit`, `ctx.info`, `get_context()`, `McpError(-32002)`, a `**kwargs` tool | MCP001 MCP011 MCP012 MCP020 MCP040 MCP050 MCP060 MCP070; AUT001 |
| `projects/py_v2` | `mcp` 2.x `MCPServer`, `streamable_http_app()` | era `dual`; no errors |
| `projects/ts_v2` | `@modelcontextprotocol/server` 2.3.1, `createMcpHandler` + Express, PRM, `jwtVerify` with audience, 403 `insufficient_scope` | era `dual`; no findings |
| `projects/ts_stdio` | v1 stdio server: `console.log`, `server.tool()` with raw shapes, a duplicate, tools in a loop, a bad name, elicitation, logging, a `ping` handler | MCP001 MCP011 MCP012 MCP040 MCP041 MCP061 MCP062 MCP064 MCP065 MCP066 MCP067 MCP070 MCP080 |
| `projects/addon_good` | a valid Alexa+ `addon.json` | nothing |
| `projects/addon_broken` | an invalid one | ALX003 ALX011 ALX012 ALX013 ALX015 ALX016 ALX017 ALX018 ALX019 ALX020 ALX022 |
| `servers/fake_mcp.py` | in-process HTTP MCP server: `dual`, `legacy`, `lax`, `modern` modes, optional token, optional challenge, optional delay | the PRB band |
| `spec/` | versioning page excerpt, a synthetic newer revision (2027-03-30 does not exist), an unparseable page, newer SDK versions | UPG001-UPG003 |
| `auth/` | PRM and authorization server metadata documents, good and bad; `prm-alexa-good.json` advertises the three Alexa+ `mcp:*` scopes | AUT003 AUT005 AUT030 AUT031 AUT040 AUT041 AUT051 ALX051 ALX054 ALX055 |
| `projects/vault_alexa` | an anonymized copy (2026-10-05) of a real Alexa+ server after its migration (names, domains and product strings replaced): `apps/mcp-server` (22 `registerTool` calls, 16 ChatGPT-profile tools after an `if (alexa) { ... return }` and 6 voice tools in `alexa/tools.ts`), `packages/auth`, the workspace files with `.npmrc` `strict-peer-dependencies=true`, and `alexa-addon/addon.json`. Regression fixture for the 0.2.0 friction fixes (`tests/skills/test_friction_regressions.py`) | ALX031 ALX032 ALX041 ALX042 ALX043 ALX050; AUT012 AUT031 AUT041 |
