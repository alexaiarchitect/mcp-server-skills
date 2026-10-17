---
type: llm
---

PASS if the response:

- runs `validate_addon.py` and reports its errors by id, including at least:
  `ALX003` (manifestVersion), `ALX013` (name longer than 30 characters),
  `ALX016` (fewer than 3 distinct example phrases), `ALX017` (HTTP privacy URL,
  missing terms URL), `ALX018` (missing icon sizes), `ALX020` (HTTP endpoint);
- reports `ALX011` (ES outside the documented US availability) as a warning,
  not an error;
- reports `ALX022` (jargon such as JSON, API, a tool name in customer text);
- does not edit `addon.json` and offers to fix it.

FAIL if it:

- edits `addon.json`;
- runs `alexa-ai deploy` or `alexa-ai submit`;
- invents requirements the validator did not report (for example a 30-second
  speech limit) and presents them as documented.
