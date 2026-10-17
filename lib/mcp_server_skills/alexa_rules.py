"""The `ALX0xx` overlay: is this MCP server ready to be an Alexa+ add-on?

Alexa+ consumes an ordinary remote MCP server, so most of readiness is the
protocol review and the auth review. This overlay adds what Alexa+ documents on
top (read 2026-10-05, URLs in the maintainer's verified-facts ledger):

- a 2025-11-25 Streamable HTTP endpoint (a modern-only server is unreachable);
- round-trip latency under 500 ms, measured, not assumed;
- tools that read as voice: intent-shaped names and descriptions, at most five
  options per answer, no screen-only paths;
- an account-linking profile that differs from the MCP spec in two places
  (no `WWW-Authenticate` on 401, `client_credentials` alongside PKCE) — which
  this overlay reports as a conflict to confirm in the simulator, not a fix;
- the add-on manifest (:mod:`addon`) and a tool-signature lock, because Alexa+
  refreshes tools only on `alexa-ai deploy`.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import ALEXA_LATENCY_BUDGET_MS, ALEXA_MAX_OPTIONS
from .inventory import UnitInventory
from .report import GapReport
from .ts_scan import ToolDef

SCREEN_WORDS = re.compile(r"\b(click|tap|scroll|see below|see above|on screen|the table|the chart|"
                          r"the widget|the card|displayed|button)\b", re.I)
LIST_NAME = re.compile(r"^(list|search|find|query|browse|get_all|lookup)_|_(list|search|results)$|^(list|search)")
GENERIC_NAME = re.compile(r"^(get|post|put|patch|delete|do|run|call|execute)_[a-z0-9]+$")


# -- which tools Alexa+ will actually see ------------------------------------------

def tool_names_from_file(path: Path) -> list[str]:
    """Tool names from `probe.py --json` (discovered.tool_names), a tools/list result, or a list.

    A name probed through an AgentCore Gateway (`<target>___<tool>`) is reduced
    to the server's own tool name.
    """
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    names: list = []
    if isinstance(doc, dict):
        discovered = doc.get("discovered") or {}
        names = (discovered.get("tool_names") or doc.get("tools") or (doc.get("result") or {}).get("tools")
                 or doc.get("tool_names") or [])
    elif isinstance(doc, list):
        names = doc
    out = []
    for item in names:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str) and name:
            out.append(name.split("___", 1)[-1])
    if not out:
        raise ValueError(f"{path}: no tool names (expected probe.py --json output, a tools/list result or a list)")
    return out


def _mentions(condition: str, word: str) -> bool:
    return re.search(rf"(?i)\b{re.escape(word)}\b|{re.escape(word)}", condition, re.I) is not None


def _negated(condition: str) -> bool:
    text = condition.strip()
    return text.startswith("!") or "!==" in text or "!=" in text


def profile_status(tool: ToolDef, profile: str) -> tuple[str, str]:
    """('in' | 'out' | 'any', why) for a tool under a deployment profile such as `alexa`.

    Read statically: an enclosing `if (alexa)` or a function / file named for the
    profile puts the tool *in*; an enclosing `if (!alexa)`, or an earlier
    `if (alexa) { ... return }` in the same body, puts it *out*; anything else is
    registered on every profile.
    """
    for cond in tool.guards:
        if _mentions(cond, profile):
            return ("out", f"inside `if ({cond})`") if _negated(cond) else ("in", f"inside `if ({cond})`")
    for cond in tool.exclusions:
        if _mentions(cond, profile) and not _negated(cond):
            return "out", f"after `if ({cond}) {{ ... return }}`"
        if _mentions(cond, profile) and _negated(cond):
            return "in", f"after `if ({cond}) {{ ... return }}`"
    if tool.function and profile.lower() in tool.function.lower():
        return "in", f"registered by `{tool.function}()`"
    near = [part.lower() for part in Path(tool.path).with_suffix("").parts[-3:]]
    if any(profile.lower() in part for part in near):
        return "in", f"defined under a `{profile}` path"
    return "any", "registered unconditionally"


def select_tools(tools: list[ToolDef], *, profile: str | None = None, allow: list[str] | None = None,
                 exclude: list[str] | None = None) -> tuple[list[ToolDef], list[dict]]:
    """The tools a deployment serves, and why each other one was left out.

    `allow` (an explicit list or the names a probe saw) wins over the static
    profile reading; `exclude` always applies.
    """
    kept: list[ToolDef] = []
    dropped: list[dict] = []
    allowed = set(allow) if allow else None
    excluded = set(exclude or [])
    for tool in tools:
        if tool.name in excluded:
            dropped.append({"tool": tool.name, "why": "--exclude-tools"})
            continue
        if allowed is not None:
            if tool.name in allowed:
                kept.append(tool)
            else:
                dropped.append({"tool": tool.name, "why": "not in the allow-list / probed tools/list"})
            continue
        if profile:
            status, why = profile_status(tool, profile)
            if status == "out":
                dropped.append({"tool": tool.name, "why": f"not registered on the {profile} profile ({why})"})
                continue
        kept.append(tool)
    if allowed is not None:
        known = {t.name for t in tools}
        for name in sorted(allowed - known):
            dropped.append({"tool": name, "why": "listed but not found in the source (dynamic registration?)"})
    return kept, dropped


def add_scope_arguments(p) -> None:
    """`--profile`, `--tools`, `--tools-from`, `--exclude-tools`: review only what Alexa+ will list."""
    p.add_argument("--profile", choices=("alexa",), help="keep only the tools the Alexa deployment registers "
                   "(read statically: `if (alexa)` guards, early returns, register*Alexa* functions, alexa/ paths)")
    p.add_argument("--tools", help="comma-separated allow-list of tool names (wins over --profile)")
    p.add_argument("--tools-from", help="the tools a live server listed: probe.py --json output, a tools/list "
                   "result, or a JSON list of names (wins over --profile)")
    p.add_argument("--exclude-tools", help="comma-separated tool names to leave out")


def scope_from_args(args, tools: list[ToolDef]) -> tuple[list[ToolDef], dict]:
    """Apply the scope arguments; returns (tools, a description for `discovered`). Raises ValueError."""
    allow = None
    source = None
    if args.tools_from:
        allow = tool_names_from_file(Path(args.tools_from))
        source = f"--tools-from {args.tools_from}"
    if args.tools:
        listed = [t.strip() for t in args.tools.split(",") if t.strip()]
        allow = listed if allow is None else [t for t in allow if t in listed]
        source = "--tools" if source is None else f"{source} and --tools"
    exclude = [t.strip() for t in (args.exclude_tools or "").split(",") if t.strip()]
    kept, dropped = select_tools(tools, profile=args.profile, allow=allow, exclude=exclude)
    scope = {"profile": args.profile or "all registrations", "selected_by": source or
             (f"--profile {args.profile}" if args.profile else "every registerTool in the source"),
             "tools_reviewed": sorted(t.name for t in kept), "tools_left_out": dropped}
    return kept, scope


def _resolve_number(u: UnitInventory, expr: str) -> int | None:
    """A page size as written (`5`, `MAX_VOICE_OPTIONS`, `limits.MAX`) resolved through `const X = N`."""
    if expr.isdigit():
        return int(expr)
    name = expr.split(".")[-1]
    pattern = re.compile(rf"\b(?:const|let|var)\s+{re.escape(name)}\s*(?::\s*\w+\s*)?=\s*(\d+)\b|"
                         rf"^\s*{re.escape(name)}\s*(?::\s*\w+\s*)?=\s*(\d+)\b", re.M)
    for f in u.files + u.support_files:
        text = f.masked.nocomment if f.masked else (f.py.nocomment if f.py else "")
        match = pattern.search(text)
        if match:
            return int(match.group(1) or match.group(2))
    return None


PAGINATION_PARAMS = ("page_token", "pageToken", "cursor", "next_token", "nextToken", "page")
LIMIT_PARAMS = ("limit", "page_size", "pageSize", "max_results", "maxResults", "count", "top", "n")


def voice_page_cap(u: UnitInventory, tool: ToolDef) -> tuple[bool, str]:
    """(within 5, how it was judged) for a list-returning tool."""
    if tool.list_limit_max is not None:
        return tool.list_limit_max <= ALEXA_MAX_OPTIONS, f"limit up to {tool.list_limit_max}"
    has_limit_input = any(p in LIMIT_PARAMS for p in tool.params)
    resolved = [(expr, _resolve_number(u, expr)) for expr in tool.page_sizes]
    caps = [value for _, value in resolved if value is not None]
    if caps and not has_limit_input:
        worst = max(caps)
        expr = next(e for e, v in resolved if v == worst)
        shown = expr if expr.isdigit() else f"{expr} = {worst}"
        return worst <= ALEXA_MAX_OPTIONS, f"server-side page size {shown}"
    if not has_limit_input and any(p in PAGINATION_PARAMS for p in tool.params):
        return True, "paginated with a token and no limit input"
    if has_limit_input:
        return False, "a limit parameter with no upper bound"
    return False, "no limit parameter"


def _guarded(u: UnitInventory, path: str, line: int) -> str | None:
    """The guard on a statement, when it is visibly conditional (a ternary or an if on the same or previous line)."""
    for offset in (0, -1, -2):
        text = u.line_text(path, line + offset) if line + offset > 0 else ""
        match = re.search(r"(\S[^?\n]{0,80}?)\s\?\s", text) if offset == 0 else None
        if match:
            return match.group(1).strip().lstrip("(,{[ ")
        cond = re.search(r"\bif\s*\(([^)]{1,80})\)", text)
        if cond:
            return cond.group(1).strip()
    return None


def review_project(u: UnitInventory, report: GapReport, *, probe: dict | None = None,
                   budget_ms: int = ALEXA_LATENCY_BUDGET_MS, tools: list[ToolDef] | None = None,
                   profile: str | None = None) -> None:
    """Add the ALX overlay for one unit.

    `tools` limits the voice checks to the tools Alexa+ will see (see
    :func:`select_tools`); `profile` says the review is scoped to a deployment
    profile, which lowers conditional findings that belong to another profile.
    """
    tools = u.tools if tools is None else tools
    s = u.signals
    manifest = str(u.unit.path / u.unit.manifest) if u.unit.manifest != "(none)" else str(u.unit.path)

    # -- protocol and transport --------------------------------------------
    if "streamable-http" not in u.transports:
        report.add("ALX061", f"transports found: {', '.join(u.transports) or 'none'}", path=manifest)
    if u.era == "stateless":
        hit = (s.get("legacy.reject") or [(manifest, 0)])[0]
        report.add("ALX060", "the endpoint serves 2026-07-28 only", path=hit[0],
                   locator=f"line {hit[1]}" if hit[1] else None)

    # -- latency ---------------------------------------------------------------
    if probe is None:
        report.add("ALX031", "pass --probe-report with the JSON from probe.py", path=manifest)
    else:
        latency = (probe.get("discovered") or {}).get("latency") or {}
        worst = None
        for method, stats in latency.items():
            p95 = stats.get("p95_ms")
            if isinstance(p95, (int, float)) and (worst is None or p95 > worst[1]):
                worst = (method, p95)
        if worst and worst[1] >= budget_ms:
            report.add("ALX030", f"p95 of {worst[0]} is {worst[1]:.0f} ms (budget {budget_ms} ms)",
                       path=str(probe.get("subject", "probe")))
    if any("lambda" in h for h in u.hosting):
        report.add("ALX032", "the server runs on AWS Lambda", path=manifest)

    # -- tools as voice ----------------------------------------------------------
    for tool in tools:
        where = dict(path=tool.path, locator=f"line {tool.line} tool {tool.name}")
        desc = tool.description or ""
        if desc and desc != "<expr>":
            problems = []
            if SCREEN_WORDS.search(desc):
                problems.append(f"refers to a screen ({SCREEN_WORDS.search(desc).group(0)!r})")
            if len(desc) > 400:
                problems.append(f"{len(desc)} characters")
            if problems:
                report.add("ALX040", f"`{tool.name}`: {'; '.join(problems)}", **where)
        if _returns_list(tool):
            within, how = voice_page_cap(u, tool)
            if not within:
                report.add("ALX041", f"`{tool.name}` returns a list ({how}); voice answers present at most "
                           f"{ALEXA_MAX_OPTIONS} options", **where)
        if tool.name_kind == "literal" and GENERIC_NAME.match(tool.name):
            report.add("ALX042", f"`{tool.name}` is named after an operation, not an intent", **where)
        if tool.ui_resource or tool.api == "registerAppTool":
            report.add("ALX043", f"`{tool.name}` renders an MCP App; confirm the voice-only path completes "
                       "the task on a headless device", **where)

    # -- account linking -----------------------------------------------------------
    both = lambda k: s.get(k) or u.support_signals.get(k)  # noqa: E731
    if both("auth.www_authenticate") and both("auth.status_401"):
        hits = [h for h in (s.get("auth.www_authenticate") or []) if not u.in_import(*h)] or \
            both("auth.www_authenticate")
        guards = [(h, _guarded(u, *h)) for h in hits]
        unguarded = [h for h, g in guards if g is None]
        if unguarded:
            hit = unguarded[0]
            report.add("ALX050", "401 responses carry WWW-Authenticate", path=hit[0], locator=f"line {hit[1]}")
        else:
            hit, guard = guards[0]
            live = ((probe or {}).get("discovered") or {}).get("auth") or {}
            bare = live.get("unauthenticated_status") == 401 and live.get("www_authenticate") is False
            if bare:
                tail = " — and the probed endpoint answered 401 without it, so this deployment takes the other branch"
            elif profile:
                tail = f" — a setting the {profile} deployment is expected to turn off; confirm it does"
            else:
                tail = "; confirm which branch the Alexa deployment takes"
            report.add("ALX050", f"401 responses carry WWW-Authenticate only when `{guard}` holds" + tail,
                       severity="info" if (profile or bare) else None, path=hit[0], locator=f"line {hit[1]}")
    if both("auth.registration_endpoint"):
        hit = both("auth.registration_endpoint")[0]
        report.add("ALX052", "Dynamic Client Registration is configured", path=hit[0], locator=f"line {hit[1]}")
    if s.get("route.tools_call_literal") and s.get("route.body_method") and s.get("auth.status_401"):
        hit = s["route.tools_call_literal"][0]
        report.add("ALX053", "only `tools/call` without a token gets 401", path=hit[0], locator=f"line {hit[1]}")
    if (both("auth.as_path") or both("auth.oidc_path")) and not both("auth.client_credentials"):
        hit = (both("auth.as_path") or both("auth.oidc_path"))[0]
        report.add("ALX051", "self-hosted authorization server metadata never mentions client_credentials",
                   path=hit[0], locator=f"line {hit[1]}")


def _returns_list(tool: ToolDef) -> bool:
    if tool.name_kind != "literal":
        return False
    if LIST_NAME.search(tool.name):
        return True
    return any(p in ("limit", "page_size", "max_results", "cursor") for p in tool.params)


# -- tool-signature lock --------------------------------------------------------------

LOCK_SCHEMA = "mcp-server-skills.alexa-tools-lock/1"


def signatures(tools: list[ToolDef]) -> dict[str, dict]:
    out = {}
    for tool in sorted(tools, key=lambda t: t.name):
        schema = re.sub(r"\s+", " ", tool.schema_source or tool.schema_kind)
        out[tool.name] = {
            "params": sorted(tool.params),
            "schema_sha256": hashlib.sha256(schema.encode("utf-8")).hexdigest()[:16],
            "description_sha256": hashlib.sha256((tool.description or "").encode("utf-8")).hexdigest()[:16],
        }
    return out


def compare_lock(lock: dict, current: dict[str, dict]) -> list[str]:
    before = lock.get("tools") or {}
    changes = []
    for name in sorted(set(before) | set(current)):
        if name not in current:
            changes.append(f"removed `{name}`")
        elif name not in before:
            changes.append(f"added `{name}`")
        else:
            if before[name].get("params") != current[name]["params"]:
                changes.append(f"`{name}` parameters {before[name].get('params')} -> {current[name]['params']}")
            elif before[name].get("schema_sha256") != current[name]["schema_sha256"]:
                changes.append(f"`{name}` input schema changed")
            if before[name].get("description_sha256") != current[name]["description_sha256"]:
                changes.append(f"`{name}` description changed")
    return changes


def lock_document(tools: list[ToolDef], *, date: str, scope: dict | None = None) -> str:
    doc = {"schema": LOCK_SCHEMA, "recorded": date}
    if scope:
        doc["scope"] = scope
    doc["tools"] = signatures(tools)
    return json.dumps(doc, indent=2) + "\n"


def find_addon(root: Path, unit_path: Path) -> Path | None:
    for candidate in (unit_path / "addon.json", root / "addon.json"):
        if candidate.is_file():
            return candidate
    for path in sorted(root.rglob("addon.json")):
        if "node_modules" not in path.parts:
            return path
    return None
