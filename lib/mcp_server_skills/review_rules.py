"""The `MCP0xx` review: what a server's code does against a pinned spec revision.

Every rule reads a :class:`~mcp_server_skills.inventory.UnitInventory` and adds
findings to a report; none opens a file. The target revision changes what is
an error: against `2025-11-25` a handshake-only server is correct, against
`2026-07-28` it cannot answer a modern client at all. Rules that only make
sense for the modern revision are skipped for a legacy target.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from . import (
    DRAFT_CODES, ERROR_CODES, LATEST_VERSIONS, MODERN_REVISIONS, SPEC_TARGET, TOOL_NAME_PATTERN,
    TS_V2_MIN_NODE, TS_V2_MIN_ZOD,
)
from .inventory import UnitInventory
from .report import GapReport


def _ver_tuple(version: str | None) -> tuple[int, ...]:
    if not version:
        return ()
    parts = [int(p) for p in re.findall(r"\d+", version)[:3]]
    return tuple(parts + [0] * (3 - len(parts)))


def _where(report: GapReport, hits, finding_id: str, message: str, **kw) -> None:
    for path, line in (hits or [])[:5]:
        report.add(finding_id, message, path=path, locator=f"line {line}", **kw)


def cache_key_of(u: UnitInventory, path: str, line: int) -> str | None:
    """The method a cache hint belongs to: the nearest `'tools/list': {` style key at or above `line`."""
    window = u.window(path, line, before=4, after=0).splitlines()
    for text in reversed(window):
        keys = re.findall(r"['\"]((?:server|tools|prompts|resources)/[a-z/]+)['\"]\s*:", text)
        if keys:
            return keys[-1]
    return None


def review(u: UnitInventory, report: GapReport, *, target: str = SPEC_TARGET) -> None:
    modern = target in MODERN_REVISIONS
    s = u.signals
    sdk = u.sdk
    lang = sdk.get("language", u.unit.language)
    manifest = str(u.unit.path / u.unit.manifest) if u.unit.manifest != "(none)" else str(u.unit.path)

    # -- SDK ------------------------------------------------------------
    major = sdk.get("major")
    if major is None and sdk.get("package"):
        report.add("DSC003", f"{sdk.get('package')} is declared as {sdk.get('declared')!r} and could not be "
                   "resolved to a version", path=manifest)
    if modern and major is not None and major < 2:
        report.add("MCP001", f"{sdk.get('package')} {sdk.get('resolved')} is a 1.x release; the 2.x line is "
                   f"the one that implements {target}", path=manifest,
                   locator=sdk.get("package"))
    elif not modern and major is not None and major < 2:
        pass
    latest_key = sdk.get("package") if major != 1 or lang != "python" else "mcp@1"
    latest = LATEST_VERSIONS.get(latest_key or "")
    if latest and major is not None and _ver_tuple(sdk.get("resolved")) and \
            _ver_tuple(sdk.get("resolved"))[0] == _ver_tuple(latest)[0] and \
            _ver_tuple(sdk.get("resolved")) < _ver_tuple(latest):
        report.add("MCP002", f"{sdk.get('package')} {sdk.get('resolved')} is older than {latest}, "
                   "the newest release of that major", path=manifest, locator=sdk.get("package"))
    if sdk.get("v1_imported") and sdk.get("v2_imported"):
        report.add("MCP003", "both @modelcontextprotocol/sdk (v1) and v2 packages are imported", path=manifest)
    apps = sdk.get("ext_apps")
    if apps and apps.get("major") is not None and major is not None and apps["major"] != major:
        report.add("MCP004", f"@modelcontextprotocol/ext-apps {apps.get('resolved')} with SDK major {major}",
                   path=manifest, locator="@modelcontextprotocol/ext-apps")
    if lang == "typescript" and (major == 2 or modern) and sdk.get("zod"):
        if _ver_tuple(sdk["zod"]) and _ver_tuple(sdk["zod"]) < _ver_tuple(TS_V2_MIN_ZOD):
            report.add("MCP005", f"zod {sdk['zod']} is below {TS_V2_MIN_ZOD}", path=manifest, locator="zod")
    if lang == "typescript" and (major == 2 or modern):
        node = u.unit.engines_node or None
        if node and _ver_tuple(node) and _ver_tuple(node)[0] < TS_V2_MIN_NODE:
            report.add("MCP006", f"engines.node is {node}", path=manifest)

    # -- era ----------------------------------------------------------------
    if modern:
        if u.era == "handshake":
            hits = (u.code_hits("ts.webstandard_transport") or u.code_hits("ts.streamable_v1")
                    or u.code_hits("ts.stdio_transport") or u.code_hits("ts.sse_transport"))
            if hits:
                _where(report, hits[:1], "MCP011",
                       "this transport speaks the handshake era only: a 2026-07-28 client's request is "
                       "rejected before any tool runs")
            else:
                report.add("MCP011", "the server is built on a handshake-era SDK API "
                           f"({', '.join(u.py_apis) or sdk.get('package')})", path=manifest)
        if u.era in ("handshake", "unknown") and not s.get("lit.server_discover"):
            report.add("MCP012", "nothing in this server answers `server/discover`", path=manifest)
    if s.get("legacy.reject"):
        _where(report, s["legacy.reject"], "MCP013",
               "`legacy: 'reject'` makes the endpoint modern-only")
    _where(report, s.get("lit.old_revision"), "MCP014", "a handshake-era revision is pinned as a literal")
    if modern and s.get("route.body_method") and not s.get("ts.create_mcp_handler"):
        _where(report, s["route.body_method"][:1], "MCP015",
               "the HTTP handler routes on the JSON-RPC body before the SDK sees it")

    # -- sessions and streams ----------------------------------------------------
    if modern:
        _where(report, s.get("session.generator"), "MCP010", "`sessionIdGenerator` configures protocol sessions")
        _where(report, s.get("session.header"), "MCP010", "`Mcp-Session-Id` is read or written")
        _where(report, s.get("session.event_store"), "MCP042", "SSE resumability is configured")

    # -- headers ---------------------------------------------------------
    custom_http = bool(s.get("route.body_method") or s.get("result.jsonrpc_literal"))
    sdk_validates = bool(s.get("ts.create_mcp_handler")) or (lang == "python" and major == 2)
    if modern and "streamable-http" in u.transports and not sdk_validates and not s.get("header.mcp_method"):
        where = (s.get("route.body_method") or s.get("ts.handle_request") or [(manifest, 0)])[0]
        report.add("MCP020", "nothing compares `Mcp-Method` / `Mcp-Name` with the request body"
                   + (" (the custom router reads the body itself)" if custom_http else ""),
                   path=where[0], locator=f"line {where[1]}" if where[1] else None)
    _where(report, s.get("header.x_mcp_header"), "MCP021", "`x-mcp-header` mirrors a parameter into a header")

    # -- results and caching --------------------------------------------------------
    if modern and s.get("result.jsonrpc_literal") and not s.get("result.result_type"):
        _where(report, s["result.jsonrpc_literal"], "MCP030", "a JSON-RPC result is built by hand")
    if modern and (major == 2 or u.era in ("dual", "stateless")) and not s.get("cache.hints") \
            and not s.get("cache.ttl"):
        report.add("MCP031", "no cache hints are set, so every list and read result goes out with "
                   "`ttlMs: 0` (immediately stale)", path=manifest,
                   severity="info" if lang == "python" else None)
    elif modern and u.era == "handshake":
        report.add("MCP031", "results carry no `ttlMs` / `cacheScope` (the 1.x SDK predates them)",
                   path=manifest)
    if s.get("cache.public") and (u.auth.get("token_verification") or u.auth.get("protected_resource_metadata")):
        # `server/discover` is built by the SDK from the static server info
        # (versions, capabilities, serverInfo): identical for every caller, so
        # a public scope on it carries no caller data.
        caller_hits = [h for h in s["cache.public"] if cache_key_of(u, *h) != "server/discover"]
        _where(report, caller_hits, "MCP032", "`cacheScope: 'public'` on a server that authenticates callers")

    # -- deprecated and removed ----------------------------------------------------------
    deprecated = (
        ("mrtr.roots", "Roots"), ("mrtr.sampling", "Sampling"), ("logging.send", "Logging"),
    )
    for key, feature in deprecated:
        _where(report, s.get(key), "MCP040", f"{feature} is Deprecated in 2026-07-28")
    if s.get("ts.sse_transport"):
        _where(report, u.code_hits("ts.sse_transport")[:1], "MCP082", "`SSEServerTransport` serves HTTP+SSE")
    for f in u.files:
        if f.py:
            for transport, line in f.py.run_transports:
                if transport == "sse":
                    report.add("MCP082", "`run(transport=\"sse\")` serves HTTP+SSE", path=str(f.path),
                               locator=f"line {line}")
            for app, line in f.py.http_apps:
                if app == "sse_app":
                    report.add("MCP082", "`sse_app()` serves HTTP+SSE", path=str(f.path), locator=f"line {line}")
    if modern:
        _where(report, s.get("removed.methods"), "MCP041", "a method removed by 2026-07-28 appears")
        _where(report, s.get("removed.schemas"), "MCP041", "a handler for a method removed by 2026-07-28")

    # -- error codes ------------------------------------------------------------
    if modern:
        defined = set(ERROR_CODES.values())
        for value, path, line in u.error_codes:
            if value == -32002:
                report.add("MCP050", "-32002 is emitted for a missing resource", path=path, locator=f"line {line}")
            elif -32099 <= value <= -32020 and value not in defined:
                report.add("MCP052", f"{value} is in the range reserved for the specification", path=path,
                           locator=f"line {line}")
        for path, line in s.get("code.draft", [])[:5]:
            report.add("MCP051", "an error is numbered with the pre-final draft code", path=path,
                       locator=f"line {line}")

    # -- tools -------------------------------------------------------------
    counts = Counter(t.name for t in u.tools if t.name_kind == "literal")
    for tool in u.tools:
        where = dict(path=tool.path, locator=f"line {tool.line} tool {tool.name}")
        if not tool.has_input_schema:
            report.add("MCP060", f"`{tool.name}` has no inputSchema", **where)
        elif tool.schema_kind == "raw-shape" and lang == "typescript":
            report.add("MCP061", f"`{tool.name}` passes a raw zod shape", **where)
        elif tool.schema_kind == "derived-untyped":
            report.add("MCP060", f"`{tool.name}` has untyped parameters, so the derived schema says nothing "
                       "about them", severity="info", **where)
        if tool.name_kind == "literal" and not re.match(TOOL_NAME_PATTERN, tool.name):
            report.add("MCP064", f"`{tool.name}` has characters outside A-Z a-z 0-9 _ - .", **where)
        if not tool.description:
            report.add("MCP066", f"`{tool.name}` has no description", **where)
        if tool.api == "tool-variadic":
            report.add("MCP067", f"`{tool.name}` is registered with `server.tool(...)`", **where)
        if tool.in_loop:
            report.add("MCP062", f"`{tool.name}` is registered inside a loop", **where)
        if tool.conditional:
            report.add("MCP063", f"`{tool.name}` is registered conditionally", **where)
    for name, count in counts.items():
        if count > 1:
            first = next(t for t in u.tools if t.name == name)
            report.add("MCP065", f"`{name}` is registered {count} times", path=first.path,
                       locator=f"line {first.line}")

    # -- server-initiated requests ------------------------------------------------------
    if modern and not s.get("mrtr.input_required"):
        for key, what in (("mrtr.elicit", "elicitation"), ("mrtr.sampling", "sampling"), ("mrtr.roots", "roots")):
            _where(report, s.get(key), "MCP070", f"{what} is requested from the server side")
    if modern:
        _where(report, s.get("notify.list_changed"), "MCP071", "list-changed is sent unsolicited")

    # -- transport hygiene ------------------------------------------------------
    if "stdio" in u.transports:
        _where(report, s.get("stdout.write"), "MCP080", "stdout is written by a stdio server")
        for f in u.files:
            if f.py and f.py.name_calls.get("print") and f.py.server_vars:
                for line in f.py.name_calls["print"][:3]:
                    report.add("MCP080", "`print()` writes to stdout in a stdio server", path=str(f.path),
                               locator=f"line {line}")
    if not any(h.startswith(("aws-lambda", "lambda")) for h in u.hosting):
        _where(report, s.get("bind.all"), "MCP081", "the server binds 0.0.0.0")

    # -- extensions ------------------------------------------------------
    if modern:
        _where(report, s.get("tasks.experimental"), "MCP090", "2025-11-25 experimental tasks are used")
    resource_uris = {r.uri for r in u.resources}
    for tool in u.tools:
        if tool.ui_resource and tool.ui_resource not in resource_uris:
            report.add("MCP091", f"`{tool.name}` names UI resource `{tool.ui_resource}`, which is not "
                       "registered", path=tool.path, locator=f"line {tool.line}")


def known_draft_codes() -> dict[int, tuple[str, int]]:
    return DRAFT_CODES


def unit_label(u: UnitInventory, root: Path) -> str:
    try:
        rel = u.path.resolve().relative_to(root.resolve())
        return str(rel) if str(rel) != "." else u.unit.name or root.name
    except ValueError:
        return str(u.path)
