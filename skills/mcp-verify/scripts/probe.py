#!/usr/bin/env python3
"""Probe a live MCP endpoint for 2026-07-28 conformance, legacy reachability, auth and latency.

What it sends, in order (every request is read-only: discovery and listings;
no tool is ever called):

1. `server/discover` with the modern `_meta` envelope and headers — the
   result must carry `resultType`, `supportedVersions` (with the target),
   `capabilities`, `ttlMs` and `cacheScope`;
2. `tools/list` twice — `resultType`, cache hints, a stable order, and an
   object `inputSchema` on every tool;
3. header validation — `tools/list` with a mismatched `Mcp-Method`, then with
   none: both must be refused with HTTP 400 and JSON-RPC -32020 (HeaderMismatch);
4. with `--legacy`, the 2025-11-25 handshake: `initialize`, then `tools/list`
   on the negotiated version (and session, if the server mints one);
5. auth — the same listing without a token must be 401; the challenge should
   carry `resource_metadata`, and that Protected Resource Metadata must load;
6. latency — `--n` round trips per method, reported as p50 / p95 / max against
   `--budget-ms` (Alexa+ asks for under 500 ms round trip);
7. a GET on the endpoint (with the token, when one was given), which a
   2026-07-28 server answers with 405; an anonymous GET answered 401 is
   recorded as "auth before method", not as PRB051.

Under `--profile alexa` a bare 401 (no `WWW-Authenticate`, which the Alexa+
quickstart asks for) lowers PRB041 to a note that cites the ALX050 conflict.
`discovered.tool_names` lists what `tools/list` returned; `lint_alexa.py` and
`tools_lock.py` take this report with `--tools-from`.

The `PRB0xx` findings: PRB00x reachability, PRB01x discover and legacy,
PRB02x headers, PRB03x results, PRB04x auth, PRB05x latency and transport.

The token is read from `--token` or, better, `--token-env NAME`, and is never
printed. Only `urllib` is used; loopback URLs bypass any proxy.

    probe.py <url> [--token-env VAR | --token T] [--n 20] [--legacy] [--budget-ms 500]
             [--profile generic|alexa] [--target 2026-07-28] [--timeout 15] [--json] [--strict]

Exit codes: 0 no errors, 1 errors (or warnings under --strict), 2 unreachable,
3 inconclusive (the server wants a token and none was given).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from mcp_server_skills import (  # noqa: E402
    ALEXA_LATENCY_BUDGET_MS, ERROR_CODES, EXTENSION_RESULT_TYPES, META_SERVER_INFO, RESULT_TYPES, SPEC_LEGACY,
    SPEC_TARGET,
)
from mcp_server_skills.auth_rules import well_known_prm_urls  # noqa: E402
from mcp_server_skills.cli import add_output, emit, fail, parser  # noqa: E402
from mcp_server_skills.jsonrpc import (  # noqa: E402
    LegacySession, Reply, get_json, http, modern_request, parse_www_authenticate, percentile,
)
from mcp_server_skills.report import EXIT_USAGE, GapReport, Option  # noqa: E402

HEADER_MISMATCH = ERROR_CODES["HeaderMismatch"]


class Probe:
    def __init__(self, args, report: GapReport):
        self.args = args
        self.url = args.url
        self.token = args.token
        self.report = report
        self.checks: list[dict] = []
        self.samples: dict[str, list[float]] = {}
        self.errors: dict[str, int] = {}

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append({"check": name, "ok": ok, "detail": detail})
        return ok

    def sample(self, label: str, reply: Reply) -> None:
        if reply.error:
            self.errors[label] = self.errors.get(label, 0) + 1
        else:
            self.samples.setdefault(label, []).append(reply.elapsed_ms)

    def modern(self, method: str, params: dict | None = None, *, token: str | None | bool = True, **kw) -> Reply:
        tok = self.token if token is True else (token or None)
        return modern_request(self.url, method, params, token=tok, version=self.args.target,
                              timeout=self.args.timeout, **kw)

    # -- checks ---------------------------------------------------------------
    def cacheable(self, label: str, result: dict) -> None:
        if result.get("resultType") is None:
            self.report.add("PRB030", f"{label} result has no resultType", path=self.url, locator=label)
        elif result.get("resultType") not in RESULT_TYPES + tuple(EXTENSION_RESULT_TYPES.values()):
            self.report.add("PRB030", f"{label} resultType is {result.get('resultType')!r}", path=self.url,
                            locator=label)
        missing = [k for k in ("ttlMs", "cacheScope") if k not in result]
        bad_scope = result.get("cacheScope") not in (None, "public", "private")
        if missing or bad_scope:
            what = f"missing {', '.join(missing)}" if missing else f"cacheScope {result.get('cacheScope')!r}"
            self.report.add("PRB031", f"{label}: {what}", path=self.url, locator=label)
        self.check(f"{label} cache hints", not missing and not bad_scope,
                   f"ttlMs={result.get('ttlMs')} cacheScope={result.get('cacheScope')}")

    def discover(self) -> str:
        """Returns 'ok', 'auth' (401), 'absent' (not a modern server) or 'down'."""
        reply = self.modern("server/discover")
        self.sample("server/discover", reply)
        if reply.error:
            self.report.add("PRB001", f"{reply.error}", path=self.url)
            return "down"
        if reply.status == 401:
            self.check("server/discover", False, "401 (authorization required)")
            return "auth"
        result = reply.result
        if reply.status != 200 or result is None:
            err = reply.rpc_error or {}
            detail = f"HTTP {reply.status}" + (f", JSON-RPC {err.get('code')} {err.get('message', '')}" if err else "")
            self.report.add("PRB010", detail, path=self.url, locator="server/discover")
            self.check("server/discover", False, detail)
            return "absent"
        versions = result.get("supportedVersions") or []
        self.check("server/discover", True, f"supportedVersions={versions}")
        if self.args.target not in versions or not isinstance(result.get("capabilities"), dict):
            self.report.add("PRB011", f"supportedVersions={versions}, capabilities="
                            f"{'present' if isinstance(result.get('capabilities'), dict) else 'missing'}",
                            path=self.url, locator="server/discover")
        self.cacheable("server/discover", result)
        if META_SERVER_INFO not in (result.get("_meta") or {}):
            self.report.add("PRB032", "server/discover result _meta has no serverInfo", path=self.url)
        if reply.sse:
            self.report.add("PRB052", "server/discover answered as an SSE stream", path=self.url)
        return "ok"

    def tools(self) -> None:
        first = self.modern("tools/list")
        self.sample("tools/list", first)
        result = first.result
        if result is None:
            self.check("tools/list", False, f"HTTP {first.status} {first.rpc_error or ''}".strip())
            return
        self.cacheable("tools/list", result)
        tools = result.get("tools") or []
        self.discovered_tools = [t.get("name") for t in tools]
        for tool in tools:
            schema = tool.get("inputSchema")
            if not isinstance(schema, dict) or schema.get("type") != "object":
                self.report.add("PRB034", f"`{tool.get('name')}` inputSchema is {type(schema).__name__ if not isinstance(schema, dict) else schema.get('type')!r}",
                                path=self.url, locator=f"tool {tool.get('name')}")
        second = self.modern("tools/list")
        self.sample("tools/list", second)
        names2 = [t.get("name") for t in ((second.result or {}).get("tools") or [])]
        if second.result is not None and names2 != self.discovered_tools:
            self.report.add("PRB033", "two consecutive tools/list calls returned different orders", path=self.url)
        self.check("tools/list", True, f"{len(tools)} tool(s)")

    def headers(self) -> None:
        mismatch = self.modern("tools/list", header_overrides={"Mcp-Method": "prompts/list"})
        self._header_case("Mcp-Method mismatch", mismatch, "PRB020")
        missing = self.modern("tools/list", drop_headers=("Mcp-Method",))
        self._header_case("Mcp-Method missing", missing, "PRB021")

    def _header_case(self, label: str, reply: Reply, accepted_id: str) -> None:
        code = (reply.rpc_error or {}).get("code")
        if reply.result is not None and reply.status < 400:
            self.report.add(accepted_id, f"{label}: HTTP {reply.status} with a result", path=self.url, locator=label)
            self.check(label, False, f"accepted (HTTP {reply.status})")
        elif reply.status != 400 or code != HEADER_MISMATCH:
            self.report.add("PRB022", f"{label}: HTTP {reply.status}, JSON-RPC code {code}", path=self.url,
                            locator=label)
            self.check(label, False, f"HTTP {reply.status} code {code}")
        else:
            self.check(label, True, "400 / -32020")

    def legacy(self) -> bool:
        session = LegacySession(self.url, token=self.token, version=self.args.legacy_version,
                                timeout=self.args.timeout)
        init = session.initialize()
        self.sample("initialize (legacy)", init)
        if init.result is None or not init.result.get("protocolVersion"):
            err = init.rpc_error or {}
            detail = f"HTTP {init.status}" + (f", JSON-RPC {err.get('code')} {err.get('message', '')}" if err else "")
            self.report.add("PRB012", detail, path=self.url, locator="initialize")
            self.check("legacy initialize", False, detail)
            return False
        self.check("legacy initialize", True, f"protocolVersion={session.negotiated}"
                   + (", session minted" if session.session_id else ", no session"))
        listing = session.request("tools/list")
        self.sample("tools/list (legacy)", listing)
        if listing.result is None:
            self.report.add("PRB013", f"HTTP {listing.status} {listing.rpc_error or ''}".strip(), path=self.url,
                            locator="tools/list (legacy)")
            self.check("legacy tools/list", False, f"HTTP {listing.status}")
            return False
        self.check("legacy tools/list", True, f"{len(listing.result.get('tools') or [])} tool(s)")
        if not getattr(self, "discovered_tools", None):
            self.discovered_tools = [t.get("name") for t in (listing.result.get("tools") or [])]
        self.legacy_session = session
        return True

    def auth(self, discover_state: str) -> dict:
        info: dict = {}
        if not self.token and discover_state != "auth":
            info["required"] = "no (anonymous requests were served)"
            return info
        anon = self.modern("tools/list", token=None)
        info["unauthenticated_status"] = anon.status
        if anon.status != 401:
            if self.token:
                self.report.add("PRB040", f"tools/list without a token: HTTP {anon.status}", path=self.url)
            return info
        challenge = anon.header("www-authenticate")
        info["www_authenticate"] = bool(challenge)
        params = parse_www_authenticate(challenge)
        prm_url = params.get("resource_metadata")
        if not prm_url:
            if self.args.profile == "alexa" and not challenge:
                # The Alexa+ quickstart asks for exactly this: 401 *without* WWW-Authenticate.
                # The MCP spec wants the challenge; that conflict is ALX050, not a probe defect.
                self.report.add("PRB041", "401 without WWW-Authenticate, as the Alexa+ quickstart requires; the MCP "
                                "authorization spec wants a resource_metadata challenge (the ALX050 conflict: "
                                "confirm in the simulator which one account linking accepts)",
                                severity="info", path=self.url, locator="alexa profile")
                info["alexa_bare_401"] = True
            else:
                self.report.add("PRB041", "401 without a resource_metadata challenge"
                                + (" (no WWW-Authenticate at all)" if not challenge else ""), path=self.url)
        candidates = [prm_url] if prm_url else well_known_prm_urls(self.url)
        prm = None
        for candidate in candidates:
            prm, _ = get_json(candidate, timeout=self.args.timeout)
            if prm is not None:
                info["prm_url"] = candidate
                break
        if prm is None or not prm.get("resource") or not prm.get("authorization_servers"):
            self.report.add("PRB042", f"tried {', '.join(candidates)}", path=self.url)
            info["prm_ok"] = False
        else:
            info["prm_ok"] = True
            info["authorization_servers"] = prm.get("authorization_servers")
        return info

    def latency(self, modern_ok: bool, legacy_ok: bool) -> dict:
        n = max(1, self.args.n)
        for _ in range(n):
            if modern_ok:
                self.sample("server/discover", self.modern("server/discover"))
                self.sample("tools/list", self.modern("tools/list"))
            if legacy_ok:
                self.sample("tools/list (legacy)", self.legacy_session.request("tools/list"))
        out = {}
        for label, values in self.samples.items():
            out[label] = {"n": len(values), "p50_ms": round(percentile(values, 50) or 0, 1),
                          "p95_ms": round(percentile(values, 95) or 0, 1),
                          "max_ms": round(max(values), 1) if values else None,
                          "errors": self.errors.get(label, 0)}
            p95 = out[label]["p95_ms"]
            if values and p95 > self.args.budget_ms:
                self.report.add("PRB050", f"{label}: p95 {p95} ms > budget {self.args.budget_ms} ms",
                                severity="error" if self.args.profile == "alexa" else None,
                                path=self.url, locator=label)
        return out


def main(argv: list[str] | None = None) -> int:
    p = parser(__doc__)
    p.add_argument("url", help="the MCP endpoint, e.g. https://mcp.example.com/mcp")
    p.add_argument("--token", help="bearer token (prefer --token-env)")
    p.add_argument("--token-env", help="read the bearer token from this environment variable")
    p.add_argument("--n", type=int, default=20, help="round trips per method for latency (default 20)")
    p.add_argument("--legacy", action="store_true", help="also probe the 2025-11-25 initialize handshake")
    p.add_argument("--legacy-version", default=SPEC_LEGACY, help=f"legacy revision to offer (default {SPEC_LEGACY})")
    p.add_argument("--budget-ms", type=float, default=ALEXA_LATENCY_BUDGET_MS,
                   help=f"p95 latency budget in ms (default {ALEXA_LATENCY_BUDGET_MS}, the Alexa+ figure)")
    p.add_argument("--profile", choices=("generic", "alexa"), default="generic",
                   help="alexa makes the latency budget an error and implies --legacy")
    p.add_argument("--target", default=SPEC_TARGET, help=f"modern revision to request (default {SPEC_TARGET})")
    p.add_argument("--timeout", type=float, default=15.0)
    add_output(p)
    args = p.parse_args(argv)
    if args.token_env:
        args.token = os.environ.get(args.token_env)
        if not args.token:
            return fail(f"${args.token_env} is empty")
    if args.profile == "alexa":
        args.legacy = True
    if not args.url.startswith(("http://", "https://")):
        return fail("the URL must start with http:// or https://")

    report = GapReport(subject=args.url, skill="mcp-verify")
    probe = Probe(args, report)
    state = probe.discover()
    if state == "down":
        report.discovered = {"url": args.url, "reachable": False}
        return emit(report, args, code=EXIT_USAGE)
    modern_ok = state == "ok"
    probe.discovered_tools = []
    if modern_ok:
        probe.tools()
        probe.headers()
    legacy_ok = probe.legacy() if args.legacy else False
    auth = probe.auth(state)
    inconclusive = state == "auth" and not args.token
    latency = probe.latency(modern_ok, legacy_ok) if (modern_ok or legacy_ok) else {}
    # The GET check measures transport behaviour, so it carries the token when one
    # was given; an auth-everything server answers an anonymous GET with 401
    # before it looks at the method, which is its own outcome, not PRB051.
    get_headers = {"Accept": "text/event-stream"}
    if args.token:
        get_headers["Authorization"] = f"Bearer {args.token}"
    get = http(args.url, headers=get_headers, timeout=args.timeout)
    if get.status == 405:
        probe.check("GET on the endpoint", True, "405" + (" (with the token)" if args.token else ""))
    elif get.status == 401 and not args.token:
        probe.check("GET on the endpoint", True, "401 (auth before method; pass --token-env to see the method check)")
    else:
        probe.check("GET on the endpoint", False, f"HTTP {get.status or get.error}")
        report.add("PRB051", f"GET answered with HTTP {get.status or get.error}"
                   + (" (with the token)" if args.token else ""), path=args.url)
    era = "dual" if modern_ok and legacy_ok else "stateless" if modern_ok and args.legacy else \
        "modern" if modern_ok else "handshake" if legacy_ok else "unknown"
    report.discovered = {
        "url": args.url, "target": args.target, "profile": args.profile, "era": era,
        "tools": len(probe.discovered_tools), "tool_names": list(probe.discovered_tools),
        "checks": probe.checks, "auth": auth,
        "latency": latency, "budget_ms": args.budget_ms,
    }
    if inconclusive:
        report.discovered["note"] = "the endpoint requires a token; pass --token-env to run the modern checks"
    report.add_option(Option("1", "Fix what failed in the server code", skill="/mcp-server:mcp-migrate",
                             cost="write", recommended=report.has_errors()))
    report.add_option(Option("2", "Run this probe after every deploy", skill="/mcp-server:mcp-ci", cost="write",
                             writes=[".github/workflows/mcp-conformance.yml"]))
    report.add_option(Option("3", "Feed the latency into the Alexa+ overlay", skill="/mcp-server:mcp-alexa",
                             cost="free", runs=["lint_alexa.py --probe-report probe.json"]))
    return emit(report, args, inconclusive=inconclusive)


if __name__ == "__main__":
    raise SystemExit(main())
