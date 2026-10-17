# The `alexa-ai` CLI flow and the web simulator

The Alexa AI CLI drives an MCP add-on from scaffold to submission. This plugin
never runs a command that deploys or submits without the user's explicit
confirmation for that command; scaffolding and validation are safe.

## Commands

| Command | Does | Cost tier |
|---|---|---|
| `alexa-ai configure` | Login with Amazon in a browser; credentials stored at `~/.alexa-ai/credentials`; `--no-browser` for headless | write (outside the project) |
| `alexa-ai new mcp --name "<name>" --locale en-US --mcp-server-url "https://..."` | scaffolds the add-on project and `addon.json`; introspects the server's tools | write |
| `alexa-ai test` | local validation (development stages page) | free |
| `alexa-ai deploy` | deploys to the development stage, returns an add-on id; **the only moment Alexa+ refreshes tool information** | deploy |
| `alexa-ai configure-account-linking --addon-id <id> --stage development --client-id <client-id>` | registers the OAuth client Alexa+ uses for account linking; the client secret is read from a masked prompt or `ALEXA_CLIENT_SECRET`, **never** a `--client-secret` flag | deploy |
| `alexa-ai submit` | submits for certification | deploy |

The quickstart also offers an "Add-on Agent Skill" path that walks the same
phases: introspection, scaffolding, media and compliance, deploy, submit.

The npm package that provides `alexa-ai` is **not named** on the quickstart or
the account-linking page (read 2026-10-05); install it from the link the
Alexa+ developer console gives you rather than guessing a package name.

## Account linking: where the scopes come from

The account-linking page says Alexa+ "reads your well-known metadata document
and automatically discovers your authorization endpoint, token endpoint,
supported scopes, token scheme, and token expiry", and that the scopes are the
`scopes_supported` of the Protected Resource Metadata at
`/.well-known/oauth-protected-resource`. Deployment is blocked when the
authorization server does not support PKCE S256, and a refresh token is
expected with every access token.

The authentication page, on the other hand, names three fixed scopes —
`mcp:service` (client credentials), `mcp:tools` and `mcp:resources`
(authorization code). The two pages do not say how they combine.
`check_prm.py --alexa` reports the mismatch as `ALX054` when PRM does not
advertise all three `mcp:*` names (a warning when it advertises none at all),
so the decision is visible: advertise the `mcp:*` names your authorization
server actually accepts (a scope-rewriting façade can map them), and confirm
in the simulator which scopes the linking request carries. `ALX055` catches
the related façade trap: AS metadata whose `issuer` is not the `iss` of the
tokens the real authorization server mints.

## The order this plugin recommends

1. `lint_server.py` and `probe.py --legacy`: the server is dual-version and
   serves `tools/list` to a 2025-11-25 client.
2. `lint_auth.py`, `check_prm.py --alexa`: PKCE S256, client credentials,
   pre-registered client for Alexa+.
3. `probe.py --profile alexa --json > probe.json`; `lint_alexa.py
   --probe-report probe.json`: latency and voice shape.
4. `alexa-ai new mcp ...` (if no addon.json yet), then `validate_addon.py`.
5. **Confirm**, then `alexa-ai deploy`, then (**confirm** again)
   `alexa-ai configure-account-linking --addon-id <id> --stage development
   --client-id <client-id>` with the secret from the prompt.
6. Web simulator: say every example phrase; link the account; try a slow
   path; try an expired token (expect re-linking). Log each surprise with
   `friction_log.py`.
7. `tools_lock.py --tools-from probe.json --write` to record exactly the tools
   the deployed endpoint lists (or `--profile alexa` for the static reading).
8. **Confirm**, then `alexa-ai submit`.

## The web simulator

Use it (or a device) after each deploy and before submitting. What to check,
from the functional requirements:

- every example phrase in the listing works when spoken;
- "What can you do?" returns a useful summary;
- account linking reaches a confirmed-linked state; an expired token triggers
  re-authentication (401);
- voice-only: at most five options, read-back and an explicit "yes" before any
  commitment;
- no API codes, tool names, JSON or internal ids in anything spoken.

## Redeploy triggers

Any change to tools (names, descriptions, schemas), to `addon.json`, or to the
endpoint. `tools_lock.py` reports tool changes since the last recorded deploy.

---

Sources: https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html,
https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-account-linking.html,
https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-authentication.html,
https://developer.amazon.com/docs/alexaplus/add-ons/alexa-plus-add-on-development-stages.html,
https://developer.amazon.com/docs/alexaplus/add-ons/functional-requirements.html (read 2026-10-05).
