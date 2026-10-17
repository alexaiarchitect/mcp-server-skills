---
type: llm
---

PASS if the response:

- runs `lint_auth.py` and reports `AUT002`: nothing serves
  `/.well-known/oauth-protected-resource`, so a spec-following client cannot
  discover the authorization server (RFC 9728 is a MUST in the MCP profile);
- reports `AUT010` (401 without a `resource_metadata` challenge) and `AUT011`
  (only `tools/call` is rejected without a token) with their consequences;
- states whether tokens are checked for audience (they are: `audience` is passed
  to `jwtVerify` in the workspace auth package);
- edits nothing.

FAIL if it:

- edits any file;
- says the authorization server is discoverable;
- confuses the authorization server's metadata with the resource server's PRM.
