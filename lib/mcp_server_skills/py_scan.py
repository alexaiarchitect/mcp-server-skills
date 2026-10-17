"""Read Python MCP servers from the syntax tree, without importing them.

The official Python SDK has two server APIs per major — the decorator API
(`FastMCP` in 1.x, `MCPServer` in 2.x) and the low-level `Server` — and the
third-party `fastmcp` package looks almost the same. This module tells them
apart by their imports, finds every `@<server>.tool()` / `.resource()` /
`.prompt()` registration, the transport the module runs, and the calls that
matter for a 2026-07-28 review (server-initiated requests, logging, removed
APIs, stdout writes). It parses; it never executes.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

from .ts_scan import PromptDef, ResourceDef, ToolDef


@dataclass
class PyFacts:
    path: str
    error: str | None = None
    modules: set[str] = field(default_factory=set)
    imported_names: dict[str, str] = field(default_factory=dict)   # local name -> module.name
    server_vars: dict[str, str] = field(default_factory=dict)      # var -> constructor (FastMCP/MCPServer/Server)
    constructor_kwargs: dict[str, list[str]] = field(default_factory=dict)
    run_transports: list[tuple[str, int]] = field(default_factory=list)
    http_apps: list[tuple[str, int]] = field(default_factory=list)  # streamable_http_app / sse_app / http_app
    attribute_calls: dict[str, list[int]] = field(default_factory=dict)  # last attr name -> lines
    name_calls: dict[str, list[int]] = field(default_factory=dict)
    int_literals: list[tuple[int, int]] = field(default_factory=list)
    tools: list[ToolDef] = field(default_factory=list)
    resources: list[ResourceDef] = field(default_factory=list)
    prompts: list[PromptDef] = field(default_factory=list)
    nocomment: str = ""
    text: str = ""

    @property
    def sdk_api(self) -> str | None:
        """Which server API the module uses: fastmcp-v1, mcpserver-v2, lowlevel, fastmcp-thirdparty."""
        mods = self.modules
        if any(m.startswith("mcp.server.mcpserver") for m in mods) or \
                self.imported_names.get("MCPServer", "").startswith("mcp.server"):
            return "mcpserver-v2"
        if any(m.startswith("mcp.server.fastmcp") for m in mods):
            return "fastmcp-v1"
        if any(m == "fastmcp" or m.startswith("fastmcp.") for m in mods):
            return "fastmcp-thirdparty"
        if any(m.startswith("mcp.server.lowlevel") for m in mods) or \
                self.imported_names.get("Server", "").startswith("mcp.server"):
            return "lowlevel"
        return None


def strip_comments(source: str) -> str:
    """The source with comments blanked, offsets kept."""
    lines = source.splitlines(keepends=True)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return source
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            row, col = tok.start
            line = lines[row - 1]
            lines[row - 1] = line[:col] + " " * (len(tok.string)) + line[col + len(tok.string):]
    return "".join(lines)


_REGISTER = ("tool", "resource", "prompt")


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return ""


def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def scan(path: Path) -> PyFacts:
    text = path.read_text(encoding="utf-8", errors="replace")
    facts = PyFacts(path=str(path), text=text, nocomment=strip_comments(text))
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        facts.error = f"line {exc.lineno}: {exc.msg}"
        return facts

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                facts.modules.add(alias.name)
                facts.imported_names[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            facts.modules.add(node.module)
            for alias in node.names:
                facts.imported_names[alias.asname or alias.name] = f"{node.module}.{alias.name}"
                facts.modules.add(f"{node.module}.{alias.name}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            ctor = _dotted(node.value.func).split(".")[-1]
            if ctor in ("FastMCP", "MCPServer", "Server"):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        facts.server_vars[target.id] = ctor
                        facts.constructor_kwargs[target.id] = [k.arg for k in node.value.keywords if k.arg]
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                facts.attribute_calls.setdefault(func.attr, []).append(node.lineno)
                if func.attr == "run":
                    transport = None
                    for kw in node.keywords:
                        if kw.arg == "transport":
                            transport = _const_str(kw.value)
                    if transport is None and node.args:
                        transport = _const_str(node.args[0])
                    if _dotted(func.value) in facts.server_vars or transport:
                        facts.run_transports.append((transport or "stdio", node.lineno))
                if func.attr in ("streamable_http_app", "sse_app", "http_app"):
                    facts.http_apps.append((func.attr, node.lineno))
            elif isinstance(func, ast.Name):
                facts.name_calls.setdefault(func.id, []).append(node.lineno)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and \
                isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, int):
            facts.int_literals.append((-node.operand.value, node.lineno))

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            target = deco.func if isinstance(deco, ast.Call) else deco
            if not isinstance(target, ast.Attribute) or target.attr not in _REGISTER:
                continue
            owner = _dotted(target.value)
            if owner not in facts.server_vars and not owner.endswith(("mcp", "server", "app")):
                continue
            kwargs = {k.arg: k.value for k in deco.keywords} if isinstance(deco, ast.Call) else {}
            args = deco.args if isinstance(deco, ast.Call) else []
            if target.attr == "tool":
                facts.tools.append(_tool(node, kwargs, args, str(path)))
            elif target.attr == "resource":
                uri = _const_str(args[0]) if args else _const_str(kwargs.get("uri"))
                facts.resources.append(ResourceDef(_const_str(kwargs.get("name")) or node.name,
                                                   uri or "", str(path), node.lineno, "decorator"))
            else:
                facts.prompts.append(PromptDef(_const_str(kwargs.get("name")) or node.name, str(path),
                                               node.lineno, "decorator"))
    return facts


def _tool(node: ast.FunctionDef | ast.AsyncFunctionDef, kwargs: dict, args: list, path: str) -> ToolDef:
    name = _const_str(kwargs.get("name")) or (_const_str(args[0]) if args else None) or node.name
    description = _const_str(kwargs.get("description")) or ast.get_docstring(node)
    params: list[str] = []
    untyped = False
    limit_max = None
    all_args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
    defaults = dict(zip([a.arg for a in node.args.args][-len(node.args.defaults):], node.args.defaults)) \
        if node.args.defaults else {}
    for arg in all_args:
        ann = ast.unparse(arg.annotation) if arg.annotation is not None else ""
        if arg.arg in ("self", "cls") or "Context" in ann:
            continue
        params.append(arg.arg)
        if arg.annotation is None:
            untyped = True
        if re.fullmatch(r"limit|max_?results|page_?size|count|top|n", arg.arg, re.I):
            match = re.search(r"le\s*=\s*(\d+)|lt\s*=\s*(\d+)", ann)
            if match:
                limit_max = int(match.group(1) or match.group(2))
            elif arg.arg in defaults and isinstance(defaults[arg.arg], ast.Constant) and \
                    isinstance(defaults[arg.arg].value, int):
                limit_max = limit_max or None
    has_var_kw = node.args.kwarg is not None
    tool = ToolDef(name=name, path=path, line=node.lineno, api="decorator", description=description,
                   has_input_schema=not has_var_kw, schema_kind="derived" if not has_var_kw else "none",
                   params=params, list_limit_max=limit_max)
    if untyped:
        tool.schema_kind = "derived-untyped"
    annotations = kwargs.get("annotations")
    if annotations is not None:
        tool.annotations = ["annotations"]
    return tool
