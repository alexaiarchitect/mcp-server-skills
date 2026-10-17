"""Turn a directory into an inventory of MCP servers: the facts every skill reasons from.

For each unit found by :mod:`layout` this reads every source file once
(TypeScript through :mod:`ts_scan`, Python through :mod:`py_scan`) and records:

- the SDK, its declared and resolved version and major;
- *signals*: named patterns with every `(path, line)` they occur at — the
  transports constructed, the era markers, auth endpoints, deprecated calls,
  error-code literals, hosting hints;
- tools, resources and prompts with their schemas;
- the protocol era the code actually implements: `handshake` (answers only
  `initialize`), `stateless` (2026-07-28 only), `dual`, or `unknown`.

Rules (:mod:`review_rules`, :mod:`auth_rules`, :mod:`alexa_rules`) read this and
never the files directly, so one scan serves the router, the review, the auth
review and the Alexa+ overlay.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from . import PY_PACKAGE, TS_EXT_APPS, TS_V1_PACKAGE, TS_V2_PACKAGES, TS_V2_SERVER
from . import py_scan, ts_scan
from .layout import Layout, Unit, detect, workspace_sources
from .ts_scan import PromptDef, ResourceDef, ToolDef

Where = tuple[str, int]

#: name -> (regex, mask). "code" = comments and literal contents blanked
#: (identifiers and structure); "text" = comments blanked, literals kept.
SIGNALS: dict[str, tuple[str, str]] = {
    # transports and serving entry points
    "ts.streamable_v1": (r"(?<![\w$])StreamableHTTPServerTransport\b", "code"),
    "ts.webstandard_transport": (r"\bWebStandardStreamableHTTPServerTransport\b", "code"),
    "ts.node_transport_v2": (r"\bNodeStreamableHTTPServerTransport\b", "code"),
    "ts.sse_transport": (r"\bSSEServerTransport\b", "code"),
    "ts.stdio_transport": (r"\bStdioServerTransport\b", "code"),
    "ts.create_mcp_handler": (r"\bcreateMcpHandler\s*\(", "code"),
    "ts.serve_stdio": (r"\bserveStdio\s*\(", "code"),
    "ts.to_node_handler": (r"\btoNodeHandler\s*\(", "code"),
    "ts.is_legacy_request": (r"\bisLegacyRequest\b", "code"),
    "ts.handle_request": (r"\.\s*handleRequest\s*\(", "code"),
    "ts.server_connect": (r"\.\s*connect\s*\(\s*transport\b", "code"),
    "legacy.reject": (r"legacy\s*:\s*['\"]reject['\"]", "text"),
    # era markers
    "lit.server_discover": (r"['\"]server/discover['\"]", "text"),
    "lit.initialize": (r"['\"]initialize['\"]", "text"),
    "lit.old_revision": (r"['\"](2024-11-05|2025-03-26|2025-06-18|2025-11-25)['\"]", "text"),
    # sessions and streams
    "session.generator": (r"\bsessionIdGenerator\b", "code"),
    "session.header": (r"(?i)mcp-session-id", "text"),
    "session.event_store": (r"\beventStore\b|(?i:last-event-id)", "text"),
    # headers and custom routing
    "route.body_method": (r"['\"]method['\"]\s+in\s+\w+|JSON\.parse\([^)]*\)[^\n;]{0,80}\.method\b|"
                          r"\[\s*['\"]method['\"]\s*\]|\.get\(\s*['\"]method['\"]\s*\)", "text"),
    "route.tools_call_literal": (r"===?\s*['\"]tools/call['\"]|['\"]tools/call['\"]\s*===?", "text"),
    "header.mcp_method": (r"(?i)mcp-method", "text"),
    "header.x_mcp_header": (r"x-mcp-header", "text"),
    # results
    "result.jsonrpc_literal": (r"jsonrpc['\"]?\s*:\s*['\"]2\.0['\"][^\n]{0,200}\bresult\b|"
                               r"\bresult\s*:\s*\{[^\n]{0,120}jsonrpc", "text"),
    "result.result_type": (r"\bresultType\b|result_type", "text"),
    "cache.hints": (r"\bcacheHints?\b|cache_hints?", "code"),
    "cache.ttl": (r"\bttlMs\b|ttl_ms", "text"),
    "cache.public": (r"cacheScope['\"]?\s*[:=]\s*['\"]public['\"]|cache_scope\s*=\s*['\"]public['\"]", "text"),
    # server-initiated requests and notifications
    "mrtr.elicit": (r"\belicitInput\s*\(|\.elicit\s*\(", "code"),
    "mrtr.sampling": (r"\bcreateMessage\s*\(|\bcreate_message\s*\(", "code"),
    "mrtr.roots": (r"\blistRoots\s*\(|\blist_roots\s*\(", "code"),
    "mrtr.input_required": (r"\binputRequired\s*\(|\bInputRequiredResult\b", "code"),
    "logging.send": (r"\bsendLoggingMessage\s*\(|\bsend_log_message\s*\(|\bctx\.(?:debug|info|warning|error|log)\s*\(", "code"),
    "notify.list_changed": (r"\bsend(?:Tool|Resource|Prompt)ListChanged\s*\(|"
                            r"\bsend_(?:tool|resource|prompt)_list_changed\s*\(", "code"),
    "removed.methods": (r"['\"](ping|logging/setLevel|resources/subscribe|resources/unsubscribe|"
                        r"notifications/roots/list_changed|notifications/elicitation/complete|"
                        r"tasks/result|tasks/list)['\"]", "text"),
    "removed.schemas": (r"\b(SetLevelRequestSchema|SubscribeRequestSchema|UnsubscribeRequestSchema|"
                        r"PingRequestSchema)\b", "code"),
    "tasks.experimental": (r"\btaskSupport\b|experimental\s*:\s*\{[^}]*\btasks\b|\bCreateTaskResult\b|"
                           r"task_support", "text"),
    "tasks.extension": (r"io\.modelcontextprotocol/tasks", "text"),
    # transport hygiene
    "stdout.write": (r"\bconsole\.log\s*\(|\bprocess\.stdout\.write\s*\(", "code"),
    "bind.all": (r"['\"]0\.0\.0\.0['\"]", "text"),
    # error codes (numbers survive the code mask)
    "code.minus_32002": (r"-\s*32002\b", "code"),
    "code.draft": (r"(?:HeaderMismatch|UnsupportedProtocolVersion|MissingRequiredClientCapability)"
                   r"[^\n]{0,60}-\s*3200[134]\b|-\s*3200[134]\b[^\n]{0,60}"
                   r"(?:HeaderMismatch|UnsupportedProtocolVersion|MissingRequiredClientCapability)", "text"),
    "code.reserved": (r"-\s*(320(?:2[3-9]|[3-9]\d))\b", "code"),
    # hosting
    "host.lambda": (r"\bAPIGatewayProxy(?:Event|Result|Handler|Structured)\w*|['\"]aws-lambda['\"]|"
                    r"\bLambdaFunctionURL\w*|\bstreamifyResponse\b|\bMangum\s*\(", "text"),
    "host.lambda_handler": (r"\bexport\s+(?:const|async\s+function|function)\s+handler\b|"
                            r"^def\s+(?:lambda_)?handler\s*\(\s*event", "code"),
    "host.express": (r"\bexpress\s*\(\s*\)", "code"),
    "host.hono": (r"\bnew\s+Hono\b", "code"),
    "host.fastify": (r"\bfastify\s*\(|\bFastify\s*\(", "code"),
    "host.node_http": (r"\bcreateServer\s*\(", "code"),
    "host.fetch_export": (r"export\s+default\s*\{[^}]{0,200}\bfetch\b|export\s+default\s+handler\b", "code"),
    "host.fastapi": (r"\bFastAPI\s*\(", "code"),
    "host.starlette": (r"\bStarlette\s*\(", "code"),
    "host.uvicorn": (r"\buvicorn\.run\s*\(", "code"),
    # auth
    "auth.prm_path": (r"/\.well-known/oauth-protected-resource", "text"),
    "auth.as_path": (r"/\.well-known/oauth-authorization-server", "text"),
    "auth.oidc_path": (r"/\.well-known/openid-configuration", "text"),
    "auth.www_authenticate": (r"(?i)www-authenticate", "text"),
    "auth.resource_metadata": (r"resource_metadata", "text"),
    "auth.prm_resource": (r"['\"]?\bresource['\"]?\s*:", "text"),
    "auth.authorization_servers": (r"authorization_servers", "text"),
    "auth.scopes_supported": (r"scopes_supported", "text"),
    "auth.registration_endpoint": (r"registration_endpoint|/register['\"]", "text"),
    "auth.pkce": (r"code_challenge_methods_supported", "text"),
    "auth.s256": (r"['\"]S256['\"]", "text"),
    "auth.iss_supported": (r"authorization_response_iss_parameter_supported", "text"),
    "auth.cimd": (r"client_id_metadata_document_supported", "text"),
    "auth.insufficient_scope": (r"insufficient_scope", "text"),
    "auth.offline_access": (r"['\"]offline_access['\"]", "text"),
    "auth.security_schemes": (r"securitySchemes|security_schemes", "text"),
    "auth.client_credentials": (r"client_credentials", "text"),
    "auth.verify": (r"\bjwtVerify\s*\(|\bCognitoJwtVerifier\b|\bcreateRemoteJWKSet\s*\(|\bjwt\.verify\s*\(|"
                    r"\bverifyAuthorizationHeader\s*\(|\bverifyToken\s*\(|\bjwt\.decode\s*\([^)]*key|"
                    r"\bPyJWKClient\b|\bverify_token\s*\(|\bTokenVerifier\b|\bverifyAccessToken\s*\(", "code"),
    "auth.audience": (r"\baudience\b|['\"]aud['\"]|\bresource\s*:|\boauthResource\b|allowedClientIds|"
                      r"\bresource_server_url\b|\brequired_audience\b", "text"),
    "auth.decode_only": (r"\bdecodeJwt\s*\(|\bjwt_decode\s*\(|verify_signature['\"]?\s*:\s*False|"
                         r"\bjwt\.decode\s*\(\s*\w+\s*\)", "text"),
    "auth.query_token": (r"searchParams\.get\(\s*['\"](?:access_token|token)['\"]|"
                         r"queryStringParameters\??\.(?:access_token|token)\b|"
                         r"query_params\.get\(\s*['\"](?:access_token|token)['\"]", "text"),
    "auth.passthrough": (r"fetch\([^;]{0,300}?[Aa]uthorization['\"]?\s*:\s*(?:authorization\b|req\.headers|"
                         r"request\.headers|event\.headers|header\(\s*event)", "text"),
    "auth.status_401": (r"\b401\b", "code"),
    "auth.status_403": (r"\b403\b", "code"),
    "auth.as.cognito": (r"(?i)cognito", "text"),
    "auth.as.auth0": (r"(?i)\.auth0\.com|auth0", "text"),
    "auth.as.okta": (r"(?i)\.okta\.com", "text"),
    "auth.as.entra": (r"(?i)login\.microsoftonline\.com", "text"),
    "auth.as.keycloak": (r"(?i)/realms/", "text"),
    "auth.as.agentcore": (r"(?i)bedrock-agentcore|agentcore[-_ ]?identity|workload-identity", "text"),
}


@dataclass
class FileFacts:
    path: Path
    language: str
    error: str | None = None
    masked: ts_scan.Masked | None = None
    py: py_scan.PyFacts | None = None
    imports: set[str] = field(default_factory=set)


@dataclass
class UnitInventory:
    unit: Unit
    files: list[FileFacts]
    support_files: list[FileFacts]
    signals: dict[str, list[Where]]
    support_signals: dict[str, list[Where]]
    tools: list[ToolDef]
    resources: list[ResourceDef]
    prompts: list[PromptDef]
    sdk: dict
    era: str
    transports: list[str]
    hosting: list[str]
    extensions: dict
    auth: dict
    py_apis: list[str]
    error_codes: list[tuple[int, str, int]]

    @property
    def path(self) -> Path:
        return self.unit.path

    def has(self, name: str) -> bool:
        return bool(self.signals.get(name))

    def has_any(self, *names: str, support: bool = False) -> bool:
        pools = [self.signals] + ([self.support_signals] if support else [])
        return any(pool.get(n) for pool in pools for n in names)

    def first(self, name: str, *, support: bool = False) -> Where | None:
        hits = self.signals.get(name) or (self.support_signals.get(name) if support else None)
        return hits[0] if hits else None

    def line_text(self, path: str, line: int) -> str:
        for f in self.files + self.support_files:
            if str(f.path) == path:
                text = f.masked.nocomment if f.masked else (f.py.nocomment if f.py else "")
                lines = text.splitlines()
                return lines[line - 1] if 0 < line <= len(lines) else ""
        return ""

    def window(self, path: str, line: int, before: int = 3, after: int = 3) -> str:
        """Lines `line-before .. line+after` of `path`, comments removed (string literals kept)."""
        for f in self.files + self.support_files:
            if str(f.path) == path:
                text = f.masked.nocomment if f.masked else (f.py.nocomment if f.py else "")
                lines = text.splitlines()
                lo, hi = max(0, line - 1 - before), min(len(lines), line + after)
                return "\n".join(lines[lo:hi])
        return ""

    def in_import(self, path: str, line: int) -> bool:
        """Whether `line` of `path` is part of an import statement (multi-line ones included)."""
        cache = self.__dict__.setdefault("_import_lines", {})
        if path not in cache:
            spans: set[int] = set()
            for f in self.files + self.support_files:
                if str(f.path) != path:
                    continue
                if f.masked is not None:
                    for m in re.finditer(r"\b(?:import|export)\s[^;]*?\bfrom\s*['\"]", f.masked.code):
                        first, last = f.masked.line_of(m.start()), f.masked.line_of(m.end())
                        spans.update(range(first, last + 1))
                elif f.py is not None:
                    for i, text in enumerate(f.py.nocomment.splitlines(), 1):
                        if text.lstrip().startswith(("import ", "from ")):
                            spans.add(i)
            cache[path] = spans
        return line in cache[path]

    def code_hits(self, name: str, *, support: bool = False) -> list[Where]:
        """Hits of a signal outside import statements, falling back to all hits."""
        hits = self.signals.get(name) or (self.support_signals.get(name) if support else None) or []
        real = [h for h in hits if not self.in_import(*h)]
        return real or hits

    def to_dict(self, root: Path) -> dict:
        rel = lambda p: _rel(p, root)  # noqa: E731
        return {
            "path": rel(self.unit.path),
            "name": self.unit.name,
            "language": self.unit.language,
            "manifest": self.unit.manifest,
            "sdk": self.sdk,
            "era": self.era,
            "transports": self.transports or ["(none found)"],
            "hosting": self.hosting or ["(none found)"],
            "extensions": self.extensions,
            "auth": self.auth,
            "tools": [dict(t.to_dict(), path=rel(Path(t.path))) for t in self.tools],
            "resources": [{"name": r.name, "uri": r.uri, "app": r.app, "line": r.line} for r in self.resources],
            "prompts": [{"name": p.name, "line": p.line} for p in self.prompts],
            "sources": len(self.unit.sources),
            "tests": len(self.unit.test_sources),
            "workspace_packages": [rel(p) for p in self.unit.workspace_deps],
        }


@dataclass
class Inventory:
    layout: Layout
    units: list[UnitInventory]

    @property
    def root(self) -> Path:
        return self.layout.root

    def ci(self) -> dict:
        runs_lint = runs_probe = False
        names = []
        for wf in self.layout.workflows:
            text = wf.read_text(encoding="utf-8", errors="replace")
            names.append(_rel(wf, self.layout.repo_root))
            runs_lint |= "lint_server.py" in text
            runs_probe |= "probe.py" in text
        return {"workflows": names, "runs_mcp_review": runs_lint, "runs_probe": runs_probe}


def _rel(path: Path, root: Path) -> str:
    try:
        rel = str(Path(path).resolve().relative_to(root.resolve()))
        return rel or "."
    except ValueError:
        return str(path)


def _scan_file(path: Path) -> FileFacts:
    if path.suffix == ".py":
        facts = py_scan.scan(path)
        return FileFacts(path, "python", facts.error, None, facts, set(facts.modules))
    try:
        masked = ts_scan.read(path)
    except OSError as exc:
        return FileFacts(path, "typescript", str(exc))
    mods = {imp.module for imp in ts_scan.imports(masked)}
    return FileFacts(path, "typescript", None, masked, None, mods)


def _collect(files: Iterable[FileFacts]) -> dict[str, list[Where]]:
    signals: dict[str, list[Where]] = {}
    for f in files:
        if f.masked is not None:
            code, text, line_of = f.masked.code, f.masked.nocomment, f.masked.line_of
        elif f.py is not None:
            text = f.py.nocomment
            code = text
            starts = [0] + [i + 1 for i, ch in enumerate(text) if ch == "\n"]
            import bisect

            line_of = lambda pos, s=starts: bisect.bisect_right(s, pos)  # noqa: E731
        else:
            continue
        for name, (pattern, which) in SIGNALS.items():
            haystack = code if which == "code" else text
            for match in re.finditer(pattern, haystack, re.M):
                signals.setdefault(name, []).append((str(f.path), line_of(match.start())))
    return signals


def _major(version: str | None) -> int | None:
    if not version:
        return None
    match = re.match(r"(\d+)", version)
    return int(match.group(1)) if match else None


def _sdk(unit: Unit, files: list[FileFacts]) -> dict:
    imports = set().union(*(f.imports for f in files)) if files else set()
    v1 = unit.dep(TS_V1_PACKAGE)
    v2 = unit.dep(TS_V2_SERVER) or next((unit.dep(p) for p in TS_V2_PACKAGES if unit.dep(p)), None)
    py = unit.dep(PY_PACKAGE)
    third = unit.dep("fastmcp")
    ts_v1_imported = any(m.startswith(TS_V1_PACKAGE) for m in imports)
    ts_v2_imported = any(any(m == p or m.startswith(p + "/") for p in TS_V2_PACKAGES) for m in imports)
    out: dict = {}
    if unit.language in ("typescript", "mixed"):
        chosen = v2 if (v2 and (ts_v2_imported or not ts_v1_imported)) else v1
        out = {
            "language": "typescript",
            "package": chosen.name if chosen else (TS_V2_SERVER if ts_v2_imported else TS_V1_PACKAGE),
            "declared": chosen.declared if chosen else None,
            "resolved": chosen.resolved if chosen else None,
            "major": _major(chosen.resolved) if chosen else (2 if ts_v2_imported and not ts_v1_imported else None),
            "v1_imported": ts_v1_imported,
            "v2_imported": ts_v2_imported,
        }
        apps = unit.dep(TS_EXT_APPS)
        if apps:
            out["ext_apps"] = {"declared": apps.declared, "resolved": apps.resolved, "major": _major(apps.resolved)}
        zod = unit.dep("zod")
        if zod:
            out["zod"] = zod.resolved or zod.declared
    if unit.language in ("python", "mixed"):
        dep = py or third
        apis = sorted({f.py.sdk_api for f in files if f.py and f.py.sdk_api})
        major = _major(dep.resolved) if dep and dep.name == PY_PACKAGE else None
        if major is None and "mcpserver-v2" in apis:
            major = 2
        elif major is None and "fastmcp-v1" in apis:
            major = 1
        py_out = {
            "language": "python",
            "package": dep.name if dep else (PY_PACKAGE if apis else None),
            "declared": dep.declared if dep else None,
            "resolved": dep.resolved if dep else None,
            "major": major,
            "apis": apis,
        }
        out = py_out if unit.language == "python" else {**out, "python": py_out}
    return out


def _era(unit: Unit, s: dict[str, list[Where]], sdk: dict, files: list[FileFacts]) -> str:
    v2_entry = bool(s.get("ts.create_mcp_handler") or s.get("ts.serve_stdio"))
    v1_transport = any(s.get(k) for k in ("ts.streamable_v1", "ts.webstandard_transport",
                                            "ts.sse_transport", "ts.stdio_transport"))
    if unit.language == "python" or sdk.get("language") == "python":
        if sdk.get("major") == 2 or "mcpserver-v2" in sdk.get("apis", []):
            return "dual"
        if sdk.get("major") == 1 or sdk.get("apis"):
            return "handshake"
    if v2_entry:
        if s.get("legacy.reject") and not (v1_transport or s.get("ts.is_legacy_request")):
            return "stateless"
        return "dual"
    manual_discover = bool(s.get("lit.server_discover"))
    if manual_discover:
        return "dual" if s.get("lit.initialize") or v1_transport else "stateless"
    if v1_transport or sdk.get("major") == 1:
        return "handshake"
    return "unknown"


def _transports(s: dict[str, list[Where]], files: list[FileFacts]) -> list[str]:
    out: set[str] = set()
    if any(s.get(k) for k in ("ts.streamable_v1", "ts.webstandard_transport", "ts.node_transport_v2",
                              "ts.create_mcp_handler", "ts.to_node_handler")):
        out.add("streamable-http")
    if s.get("ts.serve_stdio") or s.get("ts.stdio_transport"):
        out.add("stdio")
    if s.get("ts.sse_transport"):
        out.add("sse")
    for f in files:
        if not f.py:
            continue
        for transport, _ in f.py.run_transports:
            out.add({"http": "streamable-http", "streamable-http": "streamable-http",
                     "sse": "sse"}.get(transport, transport))
        for app, _ in f.py.http_apps:
            out.add("sse" if app == "sse_app" else "streamable-http")
        if f.py.server_vars and not f.py.run_transports and not f.py.http_apps:
            pass
    return sorted(out)


def _hosting(s: dict[str, list[Where]], layout: Layout) -> list[str]:
    hints = []
    for key, label in (("host.lambda", "aws-lambda"), ("host.lambda_handler", "lambda-style handler"),
                       ("host.express", "express"), ("host.hono", "hono"), ("host.fastify", "fastify"),
                       ("host.node_http", "node:http"), ("host.fetch_export", "web-standard fetch export"),
                       ("host.fastapi", "fastapi"), ("host.starlette", "starlette"),
                       ("host.uvicorn", "uvicorn")):
        if s.get(key):
            hints.append(label)
    hints += [f"{kind} ({', '.join(files[:2])})" for kind, files in sorted(layout.hosting_files.items())]
    return hints


def _auth(s: dict[str, list[Where]], support: dict[str, list[Where]]) -> dict:
    both = lambda k: bool(s.get(k) or support.get(k))  # noqa: E731
    as_types = [name.split(".")[-1] for name in SIGNALS if name.startswith("auth.as.") and both(name)]
    return {
        "protected_resource_metadata": both("auth.prm_path"),
        "www_authenticate": both("auth.www_authenticate"),
        "resource_metadata_challenge": both("auth.resource_metadata"),
        "token_verification": both("auth.verify"),
        "audience_checked": both("auth.audience"),
        "authorization_server": as_types or (["unknown"] if both("auth.verify") else ["none found"]),
        "self_hosted_as_metadata": both("auth.as_path") or both("auth.oidc_path"),
        "dcr": both("auth.registration_endpoint"),
        "per_tool_scopes": both("auth.security_schemes"),
    }


def build_unit(layout: Layout, unit: Unit) -> UnitInventory:
    files = [_scan_file(p) for p in unit.sources]
    support = [_scan_file(p) for p in workspace_sources(unit)]
    signals = _collect(files)
    support_signals = _collect(support)
    tools: list[ToolDef] = []
    resources: list[ResourceDef] = []
    prompts: list[PromptDef] = []
    codes: list[tuple[int, str, int]] = []
    for f in files:
        if f.masked is not None:
            tools += ts_scan.extract_tools(f.masked, str(f.path))
            resources += ts_scan.extract_resources(f.masked, str(f.path))
            prompts += ts_scan.extract_prompts(f.masked, str(f.path))
            for match in re.finditer(r"-\s*(32\d{3})\b", f.masked.code):
                codes.append((-int(match.group(1)), str(f.path), f.masked.line_of(match.start())))
        elif f.py is not None:
            tools += f.py.tools
            resources += f.py.resources
            prompts += f.py.prompts
            codes += [(value, str(f.path), line) for value, line in f.py.int_literals
                      if -32768 <= value <= -32000]
    sdk = _sdk(unit, files)
    apps_used = bool(sdk.get("ext_apps")) or any(r.app for r in resources) or \
        any(t.api == "registerAppTool" for t in tools)
    extensions = {
        "apps": apps_used,
        "tasks_extension": bool(signals.get("tasks.extension")),
        "tasks_experimental": bool(signals.get("tasks.experimental")),
    }
    return UnitInventory(
        unit=unit, files=files, support_files=support, signals=signals, support_signals=support_signals,
        tools=tools, resources=resources, prompts=prompts, sdk=sdk,
        era=_era(unit, signals, sdk, files), transports=_transports(signals, files),
        hosting=_hosting({**support_signals, **signals}, layout), extensions=extensions,
        auth=_auth(signals, support_signals),
        py_apis=sorted({f.py.sdk_api for f in files if f.py and f.py.sdk_api}),
        error_codes=codes,
    )


def build(root: Path) -> Inventory:
    layout = detect(root)
    return Inventory(layout, [build_unit(layout, unit) for unit in layout.units])


def select(inventory: Inventory, name: str | None) -> list[UnitInventory]:
    """Units matching `--unit` (path suffix or package name), or all of them."""
    if not name:
        return inventory.units
    picked = [u for u in inventory.units if u.unit.name == name or str(u.path).endswith(name.rstrip("/"))]
    return picked
