---
type: llm
---

PASS if the response:

- reports the probe's era for the endpoint (`dual`: `server/discover` and the
  legacy `initialize` both worked);
- reports latency as p50 / p95 per method and compares p95 with the 500 ms
  Alexa+ round-trip budget, saying the figure comes from the Alexa+ docs;
- notes where the measurement was taken (a local test server), so the numbers
  are not mistaken for production latency;
- says no tool was called.

FAIL if it:

- reports a latency it did not measure with the probe;
- calls `tools/call` on the server;
- treats an inconclusive probe (exit 3) as a pass.
