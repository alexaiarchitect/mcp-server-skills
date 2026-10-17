# Inventory fields

What `discover.py --json` puts under `discovered.units[]`, and where each value
comes from. Every value is read from files; nothing is executed.

| Field | Meaning | Source |
|---|---|---|
| `path` | the server package, relative to the root | nearest directory with `package.json`, `pyproject.toml`, `requirements.txt`, `setup.cfg` or `Pipfile` that declares or imports an MCP SDK |
| `name` | package name | `package.json` `name`, else the directory |
| `language` | `typescript`, `python`, `mixed` | manifests and the files that import an SDK |
| `manifest` | the manifest that owns the unit | as above |
| `sdk.package` | `@modelcontextprotocol/sdk` (v1), `@modelcontextprotocol/server` (v2), `mcp` | dependencies, then imports |
| `sdk.declared` | the spec as written: `^1.29.0`, `catalog:`, `>=1.9` | the manifest |
| `sdk.resolved` | a concrete or minimum version | the spec itself, or the pnpm `catalog:` / `catalogs:` entry in `pnpm-workspace.yaml` |
| `sdk.major` | 1 or 2 | `resolved`; else the import paths |
| `sdk.v1_imported` / `v2_imported` | which import paths appear | `import ... from '@modelcontextprotocol/...'` |
| `sdk.ext_apps` | `@modelcontextprotocol/ext-apps` version and major | dependencies |
| `sdk.zod` | zod version (v2 needs >= 4.2.0) | dependencies |
| `sdk.apis` (Python) | `fastmcp-v1`, `mcpserver-v2`, `lowlevel`, `fastmcp-thirdparty` | imports |
| `era` | `handshake`, `stateless`, `dual`, `unknown` | see detection-rules.md |
| `transports` | `streamable-http`, `stdio`, `sse` | transport classes, `createMcpHandler`, `serveStdio`, Python `run(transport=...)`, `streamable_http_app()` |
| `hosting` | `aws-lambda`, `express`, `hono`, `fastify`, `node:http`, `fastapi`, `starlette`, plus infra files | handler signatures and imports; `serverless.yml`, `template.yaml`, `cdk.json`, `terragrunt.hcl`, `*.tf` with `aws_lambda_function`, `Dockerfile`, `wrangler.toml` |
| `extensions.apps` | MCP Apps in use | `registerAppTool`, `registerAppResource`, ext-apps dependency |
| `extensions.tasks_extension` / `tasks_experimental` | tasks extension id, or 2025-11-25 core tasks (`taskSupport`, `tasks/result`) | literals |
| `auth.protected_resource_metadata` | a route serves `/.well-known/oauth-protected-resource` | literals in server or workspace packages |
| `auth.www_authenticate` / `resource_metadata_challenge` | challenges are built | literals |
| `auth.token_verification` | a JWT is verified | `jwtVerify`, `CognitoJwtVerifier`, `createRemoteJWKSet`, `jwt.verify`, `verifyAuthorizationHeader`, Python `PyJWKClient`, `TokenVerifier` |
| `auth.audience_checked` | an audience / resource is part of verification | `audience`, `aud`, `resource:` near verification |
| `auth.authorization_server` | issuer family | domain and SDK names |
| `auth.self_hosted_as_metadata` | the project serves authorization server metadata itself | `/.well-known/oauth-authorization-server`, `openid-configuration` routes |
| `auth.dcr` | a registration endpoint exists | `registration_endpoint`, `/register` |
| `auth.per_tool_scopes` | tools declare `securitySchemes` | tool `_meta` |
| `tools[]` | name, line, API, description (first 160 chars), `input_schema` kind, `output_schema`, `security`, `ui_resource`, params | `registerTool`, `registerAppTool`, `server.tool`, `@mcp.tool()` |
| `resources[]`, `prompts[]` | name, uri, whether an MCP App resource | `registerResource`, `registerAppResource`, `@mcp.resource`, `registerPrompt`, `@mcp.prompt` |
| `sources`, `tests` | file counts | non-test and test sources of the unit |
| `workspace_packages` | `workspace:*` dependencies read for signals | `package.json` names across the repo |

Top level: `ci.workflows`, `ci.runs_mcp_review` (`lint_server.py` appears),
`ci.runs_probe` (`probe.py` appears), `addon_json`, `node_version` (`.nvmrc`).

## What is deliberately not read

`node_modules`, build output (`dist`, `build`, `cdk.out`), virtualenvs, lock
files. The inventory reports what the project *declares*; what is installed on
one machine is not evidence about what deploys.

---

Sources: this plugin's `lib/mcp_server_skills/layout.py` and `inventory.py`;
pnpm catalogs per https://pnpm.io/catalogs; package names per
https://ts.sdk.modelcontextprotocol.io/v2/migration/upgrade-to-v2.html and
https://py.sdk.modelcontextprotocol.io/migration/ (read 2026-10-05).
