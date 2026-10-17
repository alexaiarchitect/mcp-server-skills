# Latency: what is measured and what to do about it

## The figures that exist

| Source | Figure |
|---|---|
| Alexa+ MCP toolkit quickstart | "a round-trip query response latency of less than 500 ms" |
| Alexa+ MCP design guide | "Start delivering the first item within 500ms"; reduce the initial set and lazy-load behind "See more" if not |
| Alexa+ functional requirements (search) | "Return relevant results within 3 seconds", with an interim message if longer |
| MCP specification | none |

The probe's default `--budget-ms 500` is the Alexa+ figure because it is the
strictest documented one. Use your own SLO otherwise.

## What `probe.py` measures

Wall-clock time from sending the request to having read the whole response
body, per request, from the machine running the probe. That includes DNS,
TLS, the gateway, any authorizer, the cold start if there was one, the
server's work, and the network back. It excludes nothing, so it is closest to
what a client sees from *that* location.

- **p50** — the typical request.
- **p95** — nearest-rank 95th percentile; the budget is compared with this.
- **max** — usually the first request after idle: the cold start.

Run it from where the clients are (or as close as possible). A laptop on home
Wi-Fi adds tens of milliseconds and variance the cloud client never sees.

## Where the time goes on AWS Lambda

1. **Cold start**: runtime init + module load + anything at module scope.
   Bundle size, SDK clients created at import, secrets fetched at import.
   Provisioned concurrency removes it for a fixed cost.
2. **Per-request setup**: v1's pattern builds a server and a transport per
   request (`connect`, `handleRequest`, `close`); v2's `createMcpHandler`
   builds a server per request too — keep the factory cheap (no I/O in it).
3. **Auth**: JWKS fetch on first use per container; cache it at module scope.
4. **Storage**: the tool's own DynamoDB / HTTP calls.
5. **Telemetry flush**: synchronous metric flushes at the end of each
   invocation add directly to latency.

Tracing (AWS X-Ray or OpenTelemetry) attributes the time to these segments;
the probe only tells you the total.

## Reading a result

```
server/discover       n=21  p50=82   p95=140  max=1180
tools/list            n=22  p50=95   p95=160  max=170
tools/list (legacy)   n=21  p50=90   p95=150  max=160
```

A `max` an order of magnitude above p95 is a cold start; p95 inside the budget
with such a max means warm traffic is fine and the question is how often a
real user hits a cold container.

## Gating

In CI, `gen_workflow.py` runs the probe after deploys with `--budget-ms`; a
p95 over budget fails the job only under `--profile alexa` (else a warning, to
avoid flapping on shared runners). Save `--json` output as an artifact so a
regression can be compared with the last good run.

---

Sources: https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html,
https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-design-guide.html,
https://developer.amazon.com/docs/alexaplus/add-ons/functional-requirements.html
(read 2026-10-05); this plugin's `probe.py` and `jsonrpc.percentile`.
