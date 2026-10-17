# AgentCore Gateway and Identity in front of an MCP server

Amazon Bedrock AgentCore Gateway can sit in front of an MCP server (or turn
APIs and Lambda functions into MCP tools) and take over inbound authorization.
When it does, the resource-server duties in the checklist move to the gateway,
and the server behind it authenticates the *gateway*, not end users.

## What the gateway does for inbound auth

- **JWT authorizer** (`--authorizer-type CUSTOM_JWT`): a `discovery URL` for
  the identity provider, `allowed audience` validated against the token's
  `aud` claim, `allowed clients` validated against `client_id`.
- **401** responses carry `WWW-Authenticate` with `resource_metadata` and
  `scope`; **403** carries `error="insufficient_scope"`, `scope` and
  `resource_metadata`.
- It serves its own Protected Resource Metadata at
  `/.well-known/oauth-protected-resource`.

Example (AgentCore CLI, from the gateway docs):

```bash
agentcore add gateway \
  --name MyGateway \
  --protocol-type MCP \
  --authorizer-type CUSTOM_JWT \
  --discovery-url <OIDC_DISCOVERY_URL> \
  --allowed-clients <CLIENT_ID>
```

## What that changes in this plugin's findings

| Finding on the server behind the gateway | Becomes |
|---|---|
| AUT002/AUT003 (no PRM) | the gateway's PRM is the one clients see; check it with `check_prm.py <gateway-url>` |
| AUT010 (401 without challenge) | the gateway challenges; the server should not be reachable without the gateway |
| AUT020 (no audience check) | configure `allowed audience` on the gateway; the server checks the gateway's credential |
| AUT011 (anonymous methods) | moot if only the gateway can reach the server — verify the network path |

Run the probe against the **gateway URL**: that is the endpoint clients and
Alexa+ call, and where latency is measured (the gateway adds a hop).

## Things to verify before relying on it

- **Protocol revision.** The gateway documentation read for this plugin does
  not state which MCP revisions the gateway speaks. Probe it with
  `probe.py <gateway-url> --legacy` and read `era`.
- **Alexa+ header conflict.** The gateway emits `WWW-Authenticate` on 401;
  the Alexa+ quickstart describes a 401 without it (`ALX050`). Test account
  linking in the Alexa+ web simulator before going further.
- **Outbound credentials** (the gateway calling your server or third-party
  APIs) are AgentCore Identity's job — token vaults and workload identities —
  and are not part of this review.

---

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-inbound-auth.html
(read 2026-10-05); https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html
(read 2026-10-05). Outbound identity: the AgentCore Identity developer guide
(not distilled here).
