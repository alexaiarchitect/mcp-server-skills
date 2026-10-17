"""Migration plans and the codemods that apply their mechanical parts.

A plan is data (`mcp-server-skills.migration-plan/1`): ordered steps, each
either **auto** (a literal or regex edit this module can apply and show as a
diff) or **guided** (a before/after the user or the agent applies by hand,
because getting it right needs judgement — moving per-request auth into the
handler context, replacing an elicitation with `inputRequired`). Every file a
step will touch is recorded with its SHA-256 at plan time, and
:func:`apply_plan` refuses to edit a file that has changed since (`MIG002`).

The default target is **dual-version**: 2026-07-28 served per request, 2025-era
clients still answered (TypeScript `createMcpHandler` default
`legacy: 'stateless'`; Python v2 always serves both).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from . import LATEST_VERSIONS, PEER_DEPENDENCIES, SPEC_TARGET, TS_V1_PACKAGE, TS_V2_MIN_ZOD
from .inventory import UnitInventory

PLAN_SCHEMA = "mcp-server-skills.migration-plan/1"
TS_REF = "skills/mcp-migrate/references/ts-v1-to-v2.md"
PY_REF = "skills/mcp-migrate/references/python-v1-to-v2.md"


@dataclass
class Edit:
    path: str
    find: str
    replace: str
    regex: bool = False


@dataclass
class Step:
    id: str
    title: str
    kind: str                       # deps | imports | transport | results | errors | tools | mrtr | command | verify
    auto: bool
    why: str
    findings: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    edits: list[Edit] = field(default_factory=list)
    before: str = ""
    after: str = ""
    reference: str = ""
    commands: list[str] = field(default_factory=list)
    #: Facts the step relies on that the user should see before applying it
    #: (peer dependencies it adds, package-manager settings it found).
    notes: list[str] = field(default_factory=list)
    #: Structured detail for a skill to branch on (e.g. {"peers": {...}}).
    detail: dict = field(default_factory=dict)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path | str, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _lines(u: UnitInventory, key: str, root: Path) -> list[str]:
    return sorted({_rel(p, root) for p, _ in u.signals.get(key, [])})


def _snippet(path: Path, line: int, around: int = 2) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    lo, hi = max(0, line - 1 - around), min(len(lines), line + around)
    return "\n".join(lines[lo:hi])


# -- package-manager facts for TS01 ------------------------------------------------

def package_manager_settings(unit_path: Path, root: Path) -> dict[str, dict[str, str]]:
    """npm/pnpm settings that change what an install accepts, nearest file winning.

    Reads `.npmrc` (``key=value``) in every directory from the project root down
    to the unit, and the `strictPeerDependencies` setting pnpm also accepts in
    `pnpm-workspace.yaml`. Returns ``{setting: {"value": v, "source": file}}``.
    """
    chain: list[Path] = []
    here, top = unit_path.resolve(), root.resolve()
    while True:
        chain.append(here)
        if here == top or here.parent == here:
            break
        here = here.parent
    out: dict[str, dict[str, str]] = {}
    for directory in reversed(chain):
        npmrc = directory / ".npmrc"
        if npmrc.is_file():
            for raw in npmrc.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw.strip()
                if not line or line.startswith(("#", ";")) or "=" not in line:
                    continue
                key, value = (part.strip() for part in line.split("=", 1))
                out[key] = {"value": value, "source": str(npmrc)}
        workspace = directory / "pnpm-workspace.yaml"
        if workspace.is_file():
            match = re.search(r"^strictPeerDependencies\s*:\s*(true|false)\s*$",
                              workspace.read_text(encoding="utf-8", errors="replace"), re.M)
            if match:
                out["strict-peer-dependencies"] = {"value": match.group(1), "source": str(workspace)}
    return out


def strict_peers(settings: dict[str, dict[str, str]]) -> dict[str, str] | None:
    """The setting that makes missing peers an install error, if one is on."""
    for key in ("strict-peer-dependencies", "strictPeerDependencies"):
        entry = settings.get(key)
        if entry and entry["value"].lower() == "true":
            return entry
    return None


def target_peers(package: str, major: int, root: Path) -> tuple[dict[str, str], dict[str, str], str]:
    """(required, optional, where-from) peers of `package` at `major`.

    An installed copy of that major under `node_modules` is read first (its own
    `peerDependencies` / `peerDependenciesMeta`), so a newer release than the
    plugin knows is judged by what it declares; otherwise the pinned table.
    """
    candidates = list((root / "node_modules" / ".pnpm").glob(f"{package.replace('/', '+')}@{major}.*"))
    candidates = [c / "node_modules" / package / "package.json" for c in sorted(candidates)]
    candidates.append(root / "node_modules" / package / "package.json")
    for manifest in candidates:
        try:
            doc = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not str(doc.get("version", "")).startswith(f"{major}."):
            continue
        peers = doc.get("peerDependencies") or {}
        meta = doc.get("peerDependenciesMeta") or {}
        optional = {k: v for k, v in peers.items() if (meta.get(k) or {}).get("optional")}
        required = {k: v for k, v in peers.items() if k not in optional}
        return required, optional, str(manifest)
    entry = PEER_DEPENDENCIES.get(f"{package}@{major}", {"required": {}, "optional": {}})
    return dict(entry["required"]), dict(entry["optional"]), "plugin table (npm registry, read 2026-10-05)"


def _peer_version(name: str, wanted: str) -> str:
    return LATEST_VERSIONS.get(name) or re.sub(r"^[\^~>=<\s]+", "", wanted.split("||")[0]).strip()


def plan_typescript(u: UnitInventory, root: Path, finding_ids: set[str], *, modern_only: bool) -> list[Step]:
    steps: list[Step] = []
    sdk = u.sdk
    unit = u.unit
    major = sdk.get("major")
    v2 = LATEST_VERSIONS["@modelcontextprotocol/server"]
    apps_v2 = LATEST_VERSIONS["@modelcontextprotocol/ext-apps"]
    needs_node_adapter = any(h in u.hosting for h in ("express", "node:http", "fastify"))

    if major == 1 or sdk.get("v1_imported"):
        steps.append(Step(
            id="TS00", title="Run the official v1-to-v2 codemod (imports, renames, package.json)",
            kind="command", auto=False,
            why="The SDK ships a codemod for the mechanical v1->v2 changes; it covers more renames than the "
                "edits below. Run it first if you can reach npm, then re-plan.",
            commands=["npx @modelcontextprotocol/codemod@latest v1-to-v2 .",
                      "grep -rn '@mcp-codemod-error' .", "npx tsc --noEmit"],
            reference=f"{TS_REF}#the-official-codemod"))

        edits: list[Edit] = []
        files: list[str] = []
        notes: list[str] = []
        detail: dict = {}
        peer_plan: tuple[str, Path | None] | None = None
        dep = unit.dep(TS_V1_PACKAGE)
        pkg_json = unit.path / "package.json"
        if dep and dep.declared.startswith("catalog:") and dep.source.endswith("pnpm-workspace.yaml"):
            ws = Path(dep.source)
            files += [_rel(ws, root), _rel(pkg_json, root)]
            edits.append(Edit(_rel(ws, root), rf"(['\"]?){re.escape(TS_V1_PACKAGE)}\1(\s*:\s*)['\"]?[^\s'\"#]+['\"]?",
                              rf"\g<1>@modelcontextprotocol/server\g<1>\g<2>{v2}", regex=True))
            edits.append(Edit(_rel(pkg_json, root), f'"{TS_V1_PACKAGE}": "catalog:"',
                              '"@modelcontextprotocol/server": "catalog:"'))
            apps = unit.dep("@modelcontextprotocol/ext-apps")
            if apps and apps.source.endswith("pnpm-workspace.yaml") and (apps.resolved or "").startswith("1"):
                edits.append(Edit(_rel(ws, root), r"(['\"]?@modelcontextprotocol/ext-apps['\"]?\s*:\s*)['\"]?[^\s'\"#]+['\"]?",
                                  rf"\g<1>{apps_v2}", regex=True))
                peer_plan = ("catalog", ws)
            zod = unit.dep("zod")
            if zod and zod.source.endswith("pnpm-workspace.yaml") and zod.resolved and \
                    tuple(map(int, zod.resolved.split(".")[:3])) < tuple(map(int, TS_V2_MIN_ZOD.split("."))):
                edits.append(Edit(_rel(ws, root), r"(['\"]?zod['\"]?\s*:\s*)['\"]?[^\s'\"#]+['\"]?",
                                  rf"\g<1>{TS_V2_MIN_ZOD}", regex=True))
        elif pkg_json.is_file():
            files.append(_rel(pkg_json, root))
            edits.append(Edit(_rel(pkg_json, root), rf'"{re.escape(TS_V1_PACKAGE)}"\s*:\s*"[^"]*"',
                              f'"@modelcontextprotocol/server": "^{v2}"', regex=True))
            apps = unit.dep("@modelcontextprotocol/ext-apps")
            if apps and (apps.resolved or "").startswith("1"):
                edits.append(Edit(_rel(pkg_json, root), r'"@modelcontextprotocol/ext-apps"\s*:\s*"[^"]*"',
                                  f'"@modelcontextprotocol/ext-apps": "^{apps_v2}"', regex=True))
                peer_plan = ("package.json", None)
            zod = unit.dep("zod")
            if zod and zod.resolved and tuple(map(int, (zod.resolved + ".0.0").split(".")[:3])) < \
                    tuple(map(int, TS_V2_MIN_ZOD.split("."))):
                edits.append(Edit(_rel(pkg_json, root), r'"zod"\s*:\s*"[^"]*"', f'"zod": "^{TS_V2_MIN_ZOD}"',
                                  regex=True))
        if needs_node_adapter:
            edits.append(Edit(_rel(pkg_json, root), '"dependencies": {',
                              f'"dependencies": {{\n    "@modelcontextprotocol/node": "^{LATEST_VERSIONS["@modelcontextprotocol/node"]}",'))
        settings = package_manager_settings(unit.path, root)
        strict = strict_peers(settings)
        if peer_plan is not None:
            required, optional, peers_from = target_peers("@modelcontextprotocol/ext-apps", 2, root)
            provided = {"@modelcontextprotocol/server"} | ({"zod"} if unit.dep("zod") else set())
            missing = {k: v for k, v in sorted(required.items()) if not unit.dep(k) and k not in provided}
            detail["peers"] = {"package": f"@modelcontextprotocol/ext-apps@{apps_v2}", "required": required,
                               "optional": sorted(optional), "missing": sorted(missing), "read_from": peers_from,
                               "strict_peer_dependencies": bool(strict),
                               "strict_source": strict["source"] if strict else None}
            if missing:
                if peer_plan[0] == "catalog" and peer_plan[1] is not None:
                    ws_rel = _rel(peer_plan[1], root)
                    lines = "".join(f'\\n\\g<1>"{name}": {_peer_version(name, want)}' for name, want in missing.items())
                    edits.append(Edit(ws_rel, r"(?m)^(\s*)(['\"]?@modelcontextprotocol/ext-apps['\"]?\s*:[^\n]*)$",
                                      rf"\g<1>\g<2>{lines}", regex=True))
                    added = "".join(f'"{name}": "catalog:",\n    ' for name in missing)
                    edits.append(Edit(_rel(pkg_json, root), '"@modelcontextprotocol/ext-apps": "catalog:"',
                                      f'{added}"@modelcontextprotocol/ext-apps": "catalog:"'))
                else:
                    added = "".join(f'"{name}": "^{_peer_version(name, want)}",\n    ' for name, want in missing.items())
                    edits.append(Edit(_rel(pkg_json, root), rf'("@modelcontextprotocol/ext-apps"\s*:\s*"\^{re.escape(apps_v2)}")',
                                      rf"{added}\g<1>", regex=True))
                    files.append(_rel(pkg_json, root))
                notes.append(f"@modelcontextprotocol/ext-apps {apps_v2} declares non-optional peers "
                             f"{', '.join(f'{k} {v}' for k, v in missing.items())}; this step adds them "
                             f"(peers read from {peers_from}).")
            if strict:
                notes.append(f"strict-peer-dependencies=true ({_rel(strict['source'], root)}): `pnpm install` fails "
                             "on any missing non-optional peer, so apply TS01 whole, then run `pnpm install` "
                             "before building.")
        elif strict:
            detail["peers"] = {"strict_peer_dependencies": True, "strict_source": strict["source"], "missing": []}
        steps.append(Step(
            id="TS01", title="Dependencies: @modelcontextprotocol/sdk 1.x -> @modelcontextprotocol/server 2.x",
            kind="deps", auto=True, findings=sorted({"MCP001"} | (finding_ids & {"MCP002", "MCP004", "MCP005"})),
            why=f"The 2.x line implements {SPEC_TARGET}; ext-apps 2.x needs its v2 peers (client, core) "
                f"installed beside it; zod >= {TS_V2_MIN_ZOD}.",
            files=sorted(set(files)), edits=edits, reference=f"{TS_REF}#packages", notes=notes, detail=detail))

        import_edits: list[Edit] = []
        import_files: list[str] = []
        for f in u.files:
            if f.masked is None:
                continue
            text = f.masked.text
            rel = _rel(f.path, root)
            if "@modelcontextprotocol/sdk/server/mcp.js" in text:
                import_edits.append(Edit(rel, "@modelcontextprotocol/sdk/server/mcp.js", "@modelcontextprotocol/server"))
                import_files.append(rel)
        if import_edits:
            steps.append(Step(
                id="TS02", title="Imports: McpServer from @modelcontextprotocol/server",
                kind="imports", auto=True, files=sorted(set(import_files)), edits=import_edits,
                why="v2 exports McpServer from the server package root.", reference=f"{TS_REF}#imports"))

    transport_hits = u.signals.get("ts.webstandard_transport") or u.signals.get("ts.streamable_v1")
    if transport_hits and not u.signals.get("ts.create_mcp_handler"):
        path, line = transport_hits[0]
        lambda_host = any("lambda" in h for h in u.hosting)
        handle = (u.signals.get("ts.handle_request") or [(path, line)])[0]
        before = _snippet(Path(path), line, 1)
        if handle[0] == path and abs(handle[1] - line) > 1:
            before += "\n// ...\n" + _snippet(Path(handle[0]), handle[1], 1)
        legacy = "{ legacy: 'reject', responseMode: 'json' }" if modern_only else "{ responseMode: 'json' }"
        after = (
            "import { createMcpHandler } from '@modelcontextprotocol/server';\n\n"
            "// Inside the request handler: the factory runs once per request and may close over\n"
            "// per-invocation values (auth context, telemetry callbacks), exactly like before.\n"
            f"const mcp = createMcpHandler(() => createMcpServer({{ /* same options as today */ }}), {legacy});\n"
            "const response = await mcp.fetch(request);   // was: transport.handleRequest(request)\n"
            "// No server.connect(transport), no server.close(): nothing outlives the request.\n"
            + ("// Lambda: keep converting the API Gateway event to a web Request and back, as today.\n"
               if lambda_host else "")
            + ("\n// On the wire: `responseMode` shapes 2026-07-28 exchanges only. The default legacy leg\n"
               "// (legacy: 'stateless') builds WebStandardStreamableHTTPServerTransport({ sessionIdGenerator:\n"
               "// undefined }) WITHOUT enableJsonResponse, so a 2025-era POST is answered as\n"
               "// text/event-stream where a v1 `enableJsonResponse: true` server answered application/json.\n"
               "// For a buffered host (Lambda + API Gateway) or a client that wants JSON, compose instead:\n"
               "//\n"
               "// import { createMcpHandler, isLegacyRequest, WebStandardStreamableHTTPServerTransport }\n"
               "//   from '@modelcontextprotocol/server';\n"
               "// const modern = createMcpHandler(factory, { legacy: 'reject', responseMode: 'json' });\n"
               "// async function serve(request: Request): Promise<Response> {\n"
               "//   if (await isLegacyRequest(request)) {            // classifies a clone; body stays readable\n"
               "//     const server = await factory();\n"
               "//     const transport = new WebStandardStreamableHTTPServerTransport({\n"
               "//       sessionIdGenerator: undefined, enableJsonResponse: true });\n"
               "//     await server.connect(transport);\n"
               "//     try { return await transport.handleRequest(request); } finally { await server.close(); }\n"
               "//   }\n"
               "//   return modern.fetch(request);\n"
               "// }\n"
               if not modern_only else "")
        )
        steps.append(Step(
            id="TS03", title="Serving: per-request transport -> createMcpHandler(factory)",
            kind="transport", auto=False, findings=["MCP011", "MCP012", "MCP020", "MCP031"],
            files=sorted({_rel(path, root), _rel(handle[0], root)}),
            why="createMcpHandler serves 2026-07-28 per request, answers server/discover, validates "
                "MCP-Protocol-Version / Mcp-Method / Mcp-Name, emits resultType and cache hints, and (default "
                "legacy: 'stateless') still answers 2025-era initialize. The legacy leg answers POSTs as "
                "text/event-stream (no enableJsonResponse) whatever responseMode says; the `after` shows the "
                "isLegacyRequest + enableJsonResponse composition that keeps application/json. "
                + ("Modern-only was requested: legacy: 'reject' drops 2025-11-25 clients such as Alexa+."
                   if modern_only else "Dual-version is the default."),
            before=before, after=after, reference=f"{TS_REF}#serving-createmcphandler"))

    raw = [t for t in u.tools if t.schema_kind == "raw-shape" or t.api == "tool-variadic"]
    if raw:
        steps.append(Step(
            id="TS04", title=f"Tools: wrap {len(raw)} raw shape / variadic registration(s) in registerTool + z.object",
            kind="tools", auto=False, findings=["MCP061", "MCP067"],
            files=sorted({_rel(t.path, root) for t in raw}),
            why="v2 removes server.tool() and deprecates raw shapes.",
            before="server.tool('greet', 'Greet user', { name: z.string() }, handler);",
            after="server.registerTool('greet', {\n  description: 'Greet user',\n  inputSchema: z.object({ name: z.string() })\n}, handler);",
            reference=f"{TS_REF}#tools"))
    if u.signals.get("session.generator") or u.signals.get("session.header") or u.signals.get("session.event_store"):
        steps.append(Step(
            id="TS05", title="Sessions: remove sessionIdGenerator, Mcp-Session-Id and the event store",
            kind="transport", auto=False, findings=["MCP010", "MCP042"],
            files=sorted(set(_lines(u, "session.generator", root) + _lines(u, "session.header", root)
                             + _lines(u, "session.event_store", root))),
            why="2026-07-28 has no sessions and no resumability; carry state in explicit handles.",
            reference=f"{TS_REF}#sessions"))
    code_files = sorted({path for value, path, _ in u.error_codes if value == -32002})
    if code_files:
        steps.append(Step(
            id="TS06", title="Errors: resource-not-found -32002 -> -32602",
            kind="errors", auto=True, findings=["MCP050"], files=[_rel(p, root) for p in code_files],
            edits=[Edit(_rel(p, root), r"-\s*32002\b", "-32602", regex=True) for p in code_files],
            why="2026-07-28 MUST NOT emit -32002.", reference=f"{TS_REF}#errors"))
    steps.append(Step(
        id="TS07", title="Cache hints: decide ttlMs and cacheScope per list/read",
        kind="results", auto=False, findings=["MCP031", "MCP032"],
        why="v2 emits ttlMs: 0 / cacheScope: 'private' unless ServerOptions.cacheHints (or a resource's "
            "cacheHint) says otherwise. 'public' only for results identical for every caller "
            "(server/discover built from static server info qualifies). Shape, from the SDK source: "
            "cacheHints?: Partial<Record<'tools/list' | 'prompts/list' | 'resources/list' | "
            "'resources/templates/list' | 'resources/read' | 'server/discover', "
            "{ ttlMs?: number; cacheScope?: 'public' | 'private' }>>; invalid values throw a RangeError "
            "when the server is constructed.",
        after="new McpServer(info, {\n"
              "  capabilities: { tools: {} },\n"
              "  cacheHints: {\n"
              "    'server/discover': { ttlMs: 300_000, cacheScope: 'public' },  // static server info only\n"
              "    'tools/list': { ttlMs: 60_000, cacheScope: 'private' },       // per-caller if tools vary\n"
              "  },\n"
              "});",
        reference=f"{TS_REF}#cache-hints"))
    if any(u.signals.get(k) for k in ("mrtr.elicit", "mrtr.sampling", "mrtr.roots")):
        steps.append(Step(
            id="TS08", title="Server-initiated requests -> inputRequired (MRTR)",
            kind="mrtr", auto=False, findings=["MCP070", "MCP040"],
            files=sorted(set(_lines(u, "mrtr.elicit", root) + _lines(u, "mrtr.sampling", root)
                             + _lines(u, "mrtr.roots", root))),
            why="Write handlers once in the inputRequired style; the SDK shims them to push-style "
                "requests for 2025-era clients.",
            before="const answer = await ctx.mcpReq.elicitInput({ ... });",
            after="return inputRequired({ inputRequests: { id: inputRequired.elicit({ ... }) },\n"
                  "  requestState: await stateCodec.mint({ step: 'phase1' }) });",
            reference=f"{TS_REF}#mrtr"))
    if u.signals.get("route.body_method"):
        hit = u.signals["route.body_method"][0]
        steps.append(Step(
            id="TS09", title="Custom router: keep the pre-auth gate, let the handler own the protocol",
            kind="transport", auto=False, findings=["MCP015", "AUT011"], files=[_rel(hit[0], root)],
            why="A body-inspecting gate in front of the SDK sees modern and legacy requests alike; decide "
                "per method which ones need a token, and leave header validation, 405s and error bodies "
                "to createMcpHandler.",
            before=_snippet(Path(hit[0]), hit[1], 3), reference=f"{TS_REF}#custom-routing"))
    return steps


def plan_python(u: UnitInventory, root: Path, finding_ids: set[str]) -> list[Step]:
    steps: list[Step] = []
    major = u.sdk.get("major")
    dep = u.unit.dep("mcp")
    if major == 1 and dep:
        src = Path(dep.source)
        steps.append(Step(
            id="PY01", title="Dependency: mcp 1.x -> mcp>=2.3,<3", kind="deps", auto=True, findings=["MCP001"],
            files=[_rel(src, root)],
            edits=[Edit(_rel(src, root), r"(?m)(^|[\"' \t])mcp(\[[^\]]*\])?[ \t]*(?:[<>=~!]=?[ \t]*[\d.*]+(?:[ \t]*,[ \t]*)?)+",
                        r"\g<1>mcp\g<2>>=2.3,<3", regex=True)],
            why="mcp 2.x serves 2025-11-25 (initialize) and 2026-07-28 (server/discover) from one app.",
            reference=f"{PY_REF}#dependency"))
    v1_files = [f for f in u.files if f.py and f.py.sdk_api == "fastmcp-v1"]
    if v1_files:
        edits = []
        for f in v1_files:
            rel = _rel(f.path, root)
            edits.append(Edit(rel, "mcp.server.fastmcp", "mcp.server.mcpserver"))
            edits.append(Edit(rel, r"\bFastMCP\b", "MCPServer", regex=True))
        steps.append(Step(
            id="PY02", title="Imports: FastMCP -> MCPServer (mcp.server.mcpserver)", kind="imports", auto=True,
            files=[_rel(f.path, root) for f in v1_files], edits=edits,
            why="mcp.server.fastmcp is gone in v2 (ModuleNotFoundError).", reference=f"{PY_REF}#imports"))
    moved = []
    for f in u.files:
        if not f.py:
            continue
        for var, kwargs in f.py.constructor_kwargs.items():
            bad = [k for k in kwargs if k in ("host", "port", "json_response", "stateless_http", "sse_path",
                                               "streamable_http_path", "mount_path")]
            if bad:
                moved.append((f, var, bad))
    if moved:
        steps.append(Step(
            id="PY03", title="Transport settings move from the constructor to run() / streamable_http_app()",
            kind="transport", auto=False, files=sorted({_rel(f.path, root) for f, _, _ in moved}),
            why="v2 takes json_response, stateless_http, host, port on the transport, not the server.",
            before="mcp = FastMCP(\"Demo\", port=9000, stateless_http=True)",
            after="mcp = MCPServer(\"Demo\")\nmcp.run(transport=\"streamable-http\", port=9000)\n"
                  "# or: app = mcp.streamable_http_app(json_response=True, stateless_http=True)",
            reference=f"{PY_REF}#transport"))
    ctx_files = [f for f in u.files if f.py and f.py.attribute_calls.get("get_context")]
    if ctx_files:
        steps.append(Step(
            id="PY04", title="Context: mcp.get_context() -> an injected `ctx: Context` parameter",
            kind="tools", auto=False, files=[_rel(f.path, root) for f in ctx_files],
            why="get_context() was removed in v2.", before="ctx = mcp.get_context()",
            after="def my_tool(x: int, ctx: Context) -> str: ...", reference=f"{PY_REF}#context"))
    err_files = [f for f in u.files if f.py and "McpError" in f.py.text]
    if err_files:
        steps.append(Step(
            id="PY05", title="Errors: McpError -> MCPError(code, message, data=None)", kind="errors", auto=False,
            files=[_rel(f.path, root) for f in err_files],
            why="Renamed with a new constructor; raising it now produces a JSON-RPC error.",
            reference=f"{PY_REF}#errors"))
    code_files = sorted({path for value, path, _ in u.error_codes if value == -32002})
    if code_files:
        steps.append(Step(
            id="PY06", title="Errors: resource-not-found -32002 -> -32602", kind="errors", auto=True,
            findings=["MCP050"], files=[_rel(p, root) for p in code_files],
            edits=[Edit(_rel(p, root), r"-\s*32002\b", "-32602", regex=True) for p in code_files],
            why="2026-07-28 MUST NOT emit -32002.", reference=f"{PY_REF}#errors"))
    if any(u.signals.get(k) for k in ("mrtr.elicit", "mrtr.sampling", "mrtr.roots")):
        steps.append(Step(
            id="PY07", title="Server-initiated requests -> InputRequiredResult on 2026-07-28",
            kind="mrtr", auto=False, findings=["MCP070"],
            why="On modern connections there is no back-channel (NoBackChannelError); legacy still elicits.",
            reference=f"{PY_REF}#mrtr"))
    if "lowlevel" in u.py_apis:
        steps.append(Step(
            id="PY08", title="Low-level Server: decorators -> constructor handlers", kind="tools", auto=False,
            why="v2 takes on_list_tools=... etc. and returns exact protocol types.",
            reference=f"{PY_REF}#lowlevel"))
    return steps


def build_plan(u: UnitInventory, root: Path, finding_ids: set[str], *, target: str = SPEC_TARGET,
               modern_only: bool = False) -> dict:
    lang = u.sdk.get("language", u.unit.language)
    steps = plan_python(u, root, finding_ids) if lang == "python" else \
        plan_typescript(u, root, finding_ids, modern_only=modern_only)
    steps.append(Step(
        id="VERIFY", title="Verify: build, test, re-review, probe both eras", kind="verify", auto=False,
        why="A migration is done when the review is clean and the probe passes for modern and legacy clients.",
        commands=(["npx tsc --noEmit", "npm test"] if lang != "python" else ["python -m pytest"]) + [
            f"python3 ${{CLAUDE_SKILL_DIR}}/../mcp-review/scripts/lint_server.py {_rel(u.path, root)} "
            f"--target {target} --baseline review-before.json",
            "python3 ${CLAUDE_SKILL_DIR}/../mcp-verify/scripts/probe.py <url> --legacy --json"]))
    files = sorted({f for step in steps for f in step.files if (root / f).is_file()})
    return {
        "schema": PLAN_SCHEMA,
        "project": str(root),
        "unit": _rel(u.path, root),
        "language": lang,
        "target": target,
        "mode": "modern-only" if modern_only else "dual",
        "created": date.today().isoformat(),
        "sdk": {"from": u.sdk.get("resolved"), "package": u.sdk.get("package")},
        "files": {f: sha256(root / f) for f in files},
        "steps": [asdict(s) for s in steps],
    }


# -- applying -----------------------------------------------------------------------

def _apply_edit(text: str, edit: dict) -> tuple[str, int]:
    if edit.get("regex"):
        return re.subn(edit["find"], edit["replace"], text)
    count = text.count(edit["find"])
    return text.replace(edit["find"], edit["replace"]), count


def apply_plan(plan: dict, root: Path, *, write: bool, only: set[str] | None = None) -> dict:
    """Apply the auto steps of `plan`; return diffs, written files and refusals."""
    contents: dict[str, str] = {}
    refused: list[dict] = []
    skipped: list[dict] = []
    applied: list[str] = []
    for step in plan.get("steps", []):
        if not step.get("auto") or (only and step["id"] not in only):
            if not step.get("auto") and step["id"] != "VERIFY":
                skipped.append({"step": step["id"], "reason": "guided"})
            continue
        step_ok = False
        for edit in step.get("edits", []):
            rel = edit["path"]
            path = root / rel
            if rel not in contents:
                if not path.is_file():
                    refused.append({"step": step["id"], "path": rel, "reason": "missing"})
                    continue
                expected = plan.get("files", {}).get(rel)
                if expected and sha256(path) != expected:
                    refused.append({"step": step["id"], "path": rel, "reason": "changed since plan"})
                    contents[rel] = None  # type: ignore[assignment]
                    continue
                contents[rel] = path.read_text(encoding="utf-8")
            if contents[rel] is None:
                continue
            new, count = _apply_edit(contents[rel], edit)
            if count == 0:
                skipped.append({"step": step["id"], "path": rel, "reason": f"no match for {edit['find']!r}"})
                continue
            contents[rel] = new
            step_ok = True
        if step_ok:
            applied.append(step["id"])
    diffs: dict[str, str] = {}
    written: list[str] = []
    for rel, new in contents.items():
        if new is None:
            continue
        old = (root / rel).read_text(encoding="utf-8")
        if old == new:
            continue
        diffs[rel] = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                                  f"a/{rel}", f"b/{rel}"))
        if write:
            (root / rel).write_text(new, encoding="utf-8")
            written.append(rel)
    return {"applied": applied, "diffs": diffs, "written": written, "refused": refused, "skipped": skipped}


def load_plan(path: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("schema") != PLAN_SCHEMA:
        raise ValueError(f"{path} is not a {PLAN_SCHEMA} document")
    return plan
