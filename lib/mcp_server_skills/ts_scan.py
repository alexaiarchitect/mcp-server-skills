"""Read TypeScript and JavaScript MCP servers without Node, npm or a parser package.

A full TypeScript parser is out of reach for a stdlib-only plugin, and regexes
over raw source are fooled by comments and strings. This module sits between
the two: one pass over the source produces two same-length *masks* —

- ``nocomment``: comments replaced by spaces (newlines kept);
- ``code``: comments *and* the contents of string, template and regex literals
  replaced by spaces, the delimiters kept.

Because the masks keep every offset, a match in ``code`` (where a brace inside
a string can no longer unbalance anything) maps straight back to the source
text, the literal values in ``nocomment`` and a line number. On top of that sit
balanced-bracket matching, top-level argument splitting, object-literal keys,
import extraction and the MCP-specific readers: tool, resource and prompt
registrations for both SDK majors and the MCP Apps helpers.

It reads; it never evaluates. Values that are not literals are reported as
identifiers (``value_kind == "expr"``) rather than guessed.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from pathlib import Path

TS_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs", ".jsx")

_REGEX_PRECEDERS = set("(,=:[!&|?{};+-*%<>~^")
_REGEX_KEYWORDS = ("return", "typeof", "case", "do", "else", "in", "of", "void", "yield", "await")


@dataclass
class Masked:
    text: str
    nocomment: str
    code: str
    #: (start, end) of every string-like literal's contents, in source offsets.
    literals: list[tuple[int, int]]
    _newlines: list[int] = field(default_factory=list, repr=False)

    def line_of(self, pos: int) -> int:
        if not self._newlines:
            self._newlines = [i for i, ch in enumerate(self.text) if ch == "\n"]
        return bisect.bisect_right(self._newlines, pos - 1) + 1

    def literal_values(self) -> list[str]:
        return [self.text[s:e] for s, e in self.literals]


def mask(text: str) -> Masked:
    """Produce the comment-free and literal-free masks of `text`."""
    n = len(text)
    nocomment = list(text)
    code = list(text)
    literals: list[tuple[int, int]] = []
    i = 0
    # Each entry is the brace depth at which a `${` opened inside a template.
    template_stack: list[int] = []
    depth = 0
    last_sig = ""  # last significant code character, for regex detection
    last_word = ""

    def blank(start: int, end: int, *, comment: bool) -> None:
        for j in range(start, end):
            if text[j] != "\n":
                code[j] = " "
                if comment:
                    nocomment[j] = " "

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            end = text.find("\n", i)
            end = n if end == -1 else end
            blank(i, end, comment=True)
            i = end
            continue
        if ch == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            end = n if end == -1 else end + 2
            blank(i, end, comment=True)
            i = end
            continue
        if ch in "\"'":
            j = i + 1
            while j < n and text[j] != ch and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            literals.append((i + 1, min(j, n)))
            blank(i + 1, min(j, n), comment=False)
            i = j + 1
            last_sig, last_word = ch, ""
            continue
        if ch == "`" or (ch == "}" and template_stack and template_stack[-1] == depth):
            if ch == "}":
                template_stack.pop()
            j = i + 1
            start = j
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "`":
                    break
                if text[j] == "$" and j + 1 < n and text[j + 1] == "{":
                    break
                j += 1
            literals.append((start, min(j, n)))
            blank(start, min(j, n), comment=False)
            if j < n and text[j] == "$":
                template_stack.append(depth)
                i = j + 2
                last_sig = "{"
                continue
            i = j + 1
            last_sig, last_word = "`", ""
            continue
        if ch == "/" and (last_sig in _REGEX_PRECEDERS or last_sig == "" or last_word in _REGEX_KEYWORDS):
            j = i + 1
            in_class = False
            while j < n and text[j] != "\n":
                c = text[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "[":
                    in_class = True
                elif c == "]":
                    in_class = False
                elif c == "/" and not in_class:
                    break
                j += 1
            if j < n and text[j] == "/":
                literals.append((i + 1, j))
                blank(i + 1, j, comment=False)
                i = j + 1
                while i < n and text[i].isalpha():
                    i += 1
                last_sig, last_word = "/", ""
                continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if not ch.isspace():
            if ch.isalnum() or ch in "_$":
                j = i
                while j < n and (text[j].isalnum() or text[j] in "_$"):
                    j += 1
                last_word = text[i:j]
                last_sig = "a"
                i = j
                continue
            last_sig, last_word = ch, ""
        i += 1
    return Masked(text, "".join(nocomment), "".join(code), literals)


_PAIRS = {"(": ")", "{": "}", "[": "]"}


def matching(code: str, open_pos: int) -> int:
    """Index of the bracket closing the one at `open_pos` (in the code mask), or -1."""
    opener = code[open_pos]
    closer = _PAIRS[opener]
    level = 0
    for j in range(open_pos, len(code)):
        c = code[j]
        if c == opener:
            level += 1
        elif c == closer:
            level -= 1
            if level == 0:
                return j
    return -1


def split_top(code: str, start: int, end: int) -> list[tuple[int, int]]:
    """Split code[start:end] on commas at bracket depth 0 (absolute offsets)."""
    parts: list[tuple[int, int]] = []
    level = 0
    seg = start
    for j in range(start, end):
        c = code[j]
        if c in "({[":
            level += 1
        elif c in ")}]":
            level -= 1
        elif c == "," and level == 0:
            parts.append((seg, j))
            seg = j + 1
    if code[seg:end].strip():
        parts.append((seg, end))
    return parts


def trim(code: str, start: int, end: int) -> tuple[int, int]:
    while start < end and code[start].isspace():
        start += 1
    while end > start and code[end - 1].isspace():
        end -= 1
    return start, end


@dataclass
class Call:
    callee: str
    start: int
    open: int
    close: int
    line: int
    args: list[tuple[int, int]]


def calls(m: Masked, callee_pattern: str) -> list[Call]:
    """Every call whose callee matches `callee_pattern` (a regex over the code mask)."""
    found: list[Call] = []
    for match in re.finditer(rf"(?<![\w$.])(?:[\w$]+\s*\.\s*)*(?:{callee_pattern})\s*(?:<[^()]*?>)?\s*\(", m.code):
        open_pos = match.end() - 1
        close = matching(m.code, open_pos)
        if close == -1:
            continue
        callee = re.sub(r"\s+", "", m.code[match.start():open_pos])
        found.append(Call(callee, match.start(), open_pos, close, m.line_of(match.start()),
                          split_top(m.code, open_pos + 1, close)))
    return found


def string_value(m: Masked, start: int, end: int) -> str | None:
    """The value of a literal string (or a `+` concatenation of them), else None."""
    s, e = trim(m.code, start, end)
    if s >= e:
        return None
    pieces = []
    for part_s, part_e in _split_plus(m.code, s, e):
        ps, pe = trim(m.code, part_s, part_e)
        if pe - ps < 2 or m.code[ps] not in "\"'`" or m.code[pe - 1] != m.code[ps]:
            return None
        inner = m.text[ps + 1:pe - 1]
        if m.code[ps] == "`" and "${" in inner:
            return None
        pieces.append(inner)
    return "".join(pieces)


def _split_plus(code: str, start: int, end: int) -> list[tuple[int, int]]:
    parts, level, seg = [], 0, start
    for j in range(start, end):
        c = code[j]
        if c in "({[":
            level += 1
        elif c in ")}]":
            level -= 1
        elif c == "+" and level == 0:
            parts.append((seg, j))
            seg = j + 1
    parts.append((seg, end))
    return parts


def object_entries(m: Masked, start: int, end: int) -> dict[str, tuple[int, int]]:
    """Top-level `key -> (value_start, value_end)` of the object literal spanning start..end.

    `start` may point at the `{` or anywhere before it inside the span. Spread
    elements are recorded under `"..."` (the last one wins); shorthand
    properties map to their own name.
    """
    s, e = trim(m.code, start, end)
    if s >= e or m.code[s] != "{":
        return {}
    close = matching(m.code, s)
    if close == -1:
        return {}
    entries: dict[str, tuple[int, int]] = {}
    for ps, pe in split_top(m.code, s + 1, close):
        ps, pe = trim(m.code, ps, pe)
        if ps >= pe:
            continue
        segment = m.code[ps:pe]
        if segment.startswith("..."):
            entries["..."] = (ps + 3, pe)
            continue
        key_match = re.match(r"(?:async\s+)?(?:get\s+|set\s+)?([\w$]+|\"\s*\"|'\s*'|\[[^\]]*\])\s*", segment)
        if not key_match:
            continue
        raw_key = key_match.group(1)
        if raw_key[0] in "\"'":
            key = m.text[ps + 1:ps + len(raw_key) - 1]
        else:
            key = raw_key
        after = ps + key_match.end()
        if after < pe and m.code[after] == ":":
            entries[key] = trim(m.code, after + 1, pe)
        elif after < pe and m.code[after] in "(<":
            entries[key] = (after, pe)  # method shorthand
        else:
            entries[key] = (ps, pe)  # shorthand property
    return entries


def source_of(m: Masked, span: tuple[int, int]) -> str:
    return m.text[span[0]:span[1]]


# -- imports -----------------------------------------------------------------

@dataclass
class Import:
    module: str
    names: list[str]
    line: int
    type_only: bool = False


_IMPORT_FROM = re.compile(r"\bimport\s+(type\s+)?([\w$*{}\s,]+?)\s+from\s*(['\"])")
_IMPORT_BARE = re.compile(r"\bimport\s*(['\"])")
_DYNAMIC = re.compile(r"\b(?:require|import)\s*\(\s*(['\"])")
_EXPORT_FROM = re.compile(r"\bexport\s+(?:type\s+)?[\w$*{}\s,]+?\s+from\s*(['\"])")


def _module_at(m: Masked, quote_pos: int) -> str:
    end = m.text.find(m.text[quote_pos], quote_pos + 1)
    return m.text[quote_pos + 1:end] if end != -1 else ""


def imports(m: Masked) -> list[Import]:
    found: list[Import] = []
    for match in _IMPORT_FROM.finditer(m.code):
        names_raw = match.group(2)
        names = [n.strip().split(" as ")[-1].strip() for n in re.split(r"[{},]", names_raw) if n.strip()]
        names = [re.sub(r"^type\s+", "", n) for n in names]
        found.append(Import(_module_at(m, match.end() - 1), names, m.line_of(match.start()),
                            bool(match.group(1))))
    for regex in (_IMPORT_BARE, _DYNAMIC, _EXPORT_FROM):
        for match in regex.finditer(m.code):
            found.append(Import(_module_at(m, match.end() - 1), [], m.line_of(match.start())))
    return found


# -- MCP readers ---------------------------------------------------------------

@dataclass
class ToolDef:
    name: str
    path: str
    line: int
    api: str                      # registerTool | registerAppTool | tool-variadic | decorator | literal
    name_kind: str = "literal"    # literal | expr
    description: str | None = None
    has_input_schema: bool = False
    schema_kind: str = "none"     # zod-object | raw-shape | json | derived | expr | none
    schema_source: str = ""
    has_output_schema: bool = False
    annotations: list[str] = field(default_factory=list)
    security: bool = False
    ui_resource: str | None = None
    in_loop: bool = False
    conditional: bool = False
    list_limit_max: int | None = None
    params: list[str] = field(default_factory=list)
    #: Conditions of the `if (...)` blocks the registration sits in, as written
    #: (a leading `!` kept), innermost last.
    guards: list[str] = field(default_factory=list)
    #: Conditions of earlier `if (cond) { ... return }` blocks in the same body:
    #: the registration only runs when each of them is false.
    exclusions: list[str] = field(default_factory=list)
    #: Name of the nearest enclosing named function (`registerAlexaTools`).
    function: str | None = None
    #: Page sizes the handler passes to its data source (`limit: 5`,
    #: `limit: MAX_VOICE_OPTIONS`), as written; resolved by the caller.
    page_sizes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "path": self.path, "line": self.line, "api": self.api,
            "description": (self.description or "")[:160], "input_schema": self.schema_kind,
            "output_schema": self.has_output_schema, "security": self.security,
            "ui_resource": self.ui_resource, "params": ", ".join(self.params),
        }


@dataclass
class ResourceDef:
    name: str
    uri: str
    path: str
    line: int
    api: str
    app: bool = False


@dataclass
class PromptDef:
    name: str
    path: str
    line: int
    api: str


def enclosing_headers(m: Masked, pos: int) -> list[str]:
    """The text before each `{` that is still open at `pos`, innermost last."""
    stack: list[int] = []
    for j in range(pos):
        c = m.code[j]
        if c == "{":
            stack.append(j)
        elif c == "}" and stack:
            stack.pop()
    return [m.code[max(0, s - 160):s] for s in stack]


_LOOP_HEADER = re.compile(r"(?:\bfor\s*\([^{};]*\)\s*$|\.(?:forEach|map|flatMap)\s*\([^{};]*=>\s*$|"
                          r"\bwhile\s*\([^{};]*\)\s*$)")
_COND_HEADER = re.compile(r"\bif\s*\((?P<cond>[^{};]*)\)\s*$")


def _schema_kind(m: Masked, span: tuple[int, int]) -> str:
    text = m.code[span[0]:span[1]].strip()
    if re.match(r"z\s*\.\s*(?:strictObject|object|looseObject)\s*\(", text) or re.match(r"z\s*\.\s*object", text):
        return "zod-object"
    if text.startswith("{"):
        entries = object_entries(m, *span)
        if "type" in entries or "properties" in entries or "$schema" in entries:
            return "json"
        return "raw-shape"
    return "expr"


def _limit_max(source: str) -> int | None:
    """The largest `.max(N)` on a parameter that looks like a page size."""
    best = None
    for match in re.finditer(r"\b(limit|max_?results|page_?size|count|top|n)\b[^,\n]*?\.max\((\d+)\)", source, re.I):
        value = int(match.group(2))
        best = value if best is None else max(best, value)
    return best


def _description(m: Masked, entries: dict[str, tuple[int, int]]) -> str | None:
    if "description" not in entries:
        return None
    value = string_value(m, *entries["description"])
    return value if value is not None else "<expr>"


_FUNCTION_HEADER = re.compile(r"(?:\bfunction\s*\*?\s*([\w$]+)\s*(?:<[^{}]*>)?\s*\([^{}]*\)\s*(?::[^{}=]*)?$|"
                              r"\b(?:const|let|var)\s+([\w$]+)\s*(?::[^=]*)?=\s*(?:async\s*)?"
                              r"(?:function\b[^{}]*|\([^{}]*\)\s*(?::[^{}=]*)?=>)\s*$)")
_PAGE_SIZE = re.compile(r"\b(?:limit|pageSize|page_size|maxResults|max_results|Limit|MaxItems|first|take)\s*:\s*"
                        r"([0-9]+|[A-Za-z_$][\w$.]*)")


def _guards(m: Masked, position: int) -> tuple[list[str], list[str], str | None]:
    """(enclosing if-conditions, earlier early-return conditions, enclosing function)."""
    stack: list[int] = []
    for j in range(position):
        c = m.code[j]
        if c == "{":
            stack.append(j)
        elif c == "}" and stack:
            stack.pop()
    guards: list[str] = []
    function = None
    for brace in stack:
        head_start = max(0, brace - 200)
        head = m.code[head_start:brace]
        cond = _COND_HEADER.search(head)
        if cond:
            guards.append(" ".join(m.nocomment[head_start + cond.start("cond"):head_start + cond.end("cond")].split()))
        fn = _FUNCTION_HEADER.search(head)
        if fn:
            function = fn.group(1) or fn.group(2)
    exclusions: list[str] = []
    body_start = stack[-1] + 1 if stack else 0
    j = body_start
    pattern = re.compile(r"\bif\s*\(")
    while True:
        match = pattern.search(m.code, j, position)
        if not match:
            break
        open_paren = match.end() - 1
        close_paren = matching(m.code, open_paren)
        if close_paren == -1 or close_paren >= position:
            break
        k = close_paren + 1
        while k < position and m.code[k].isspace():
            k += 1
        depth_ok = m.code[body_start:match.start()].count("{") == m.code[body_start:match.start()].count("}")
        if k < position and m.code[k] == "{":
            end = matching(m.code, k)
            if end != -1 and end < position:
                if depth_ok and re.search(r"\breturn\b|\bthrow\b", m.code[k:end]):
                    exclusions.append(" ".join(m.nocomment[open_paren + 1:close_paren].split()))
                j = end + 1
                continue
        j = close_paren + 1
    return guards, exclusions, function


def _tool_from_config(m: Masked, path: str, line: int, api: str, name_span: tuple[int, int],
                      config_span: tuple[int, int] | None, position: int,
                      handler_span: tuple[int, int] | None = None) -> ToolDef:
    literal = string_value(m, *name_span)
    tool = ToolDef(name=literal if literal is not None else source_of(m, trim(m.code, *name_span)),
                   path=path, line=line, api=api, name_kind="literal" if literal is not None else "expr")
    if config_span is not None:
        entries = object_entries(m, *config_span)
        tool.description = _description(m, entries)
        if "inputSchema" in entries:
            tool.has_input_schema = True
            tool.schema_kind = _schema_kind(m, entries["inputSchema"])
            tool.schema_source = source_of(m, entries["inputSchema"])
            tool.list_limit_max = _limit_max(tool.schema_source)
            tool.params = _param_names(m, entries["inputSchema"])
        tool.has_output_schema = "outputSchema" in entries
        if "annotations" in entries:
            tool.annotations = sorted(k for k in object_entries(m, *entries["annotations"]) if k != "...")
        meta_text = source_of(m, entries["_meta"]) if "_meta" in entries else ""
        tool.security = "securitySchemes" in meta_text or "toolMeta(" in meta_text or "security(" in meta_text
        ui = re.search(r"resourceUri\s*:\s*([\w$.]+|['\"][^'\"]+['\"])", meta_text)
        if ui:
            tool.ui_resource = ui.group(1).strip("'\"")
        elif re.search(r"toolMeta\([^,)]*,\s*([\w$.]+)", meta_text):
            tool.ui_resource = re.search(r"toolMeta\([^,)]*,\s*([\w$.]+)", meta_text).group(1)
    headers = enclosing_headers(m, position)
    tool.in_loop = any(_LOOP_HEADER.search(h) for h in headers)
    tool.guards, tool.exclusions, tool.function = _guards(m, position)
    tool.conditional = any(_COND_HEADER.search(h) for h in headers)
    if handler_span is not None:
        tool.page_sizes = [g.group(1) for g in _PAGE_SIZE.finditer(m.nocomment[handler_span[0]:handler_span[1]])]
    return tool


def _param_names(m: Masked, span: tuple[int, int]) -> list[str]:
    text = m.code[span[0]:span[1]]
    brace = text.find("{")
    if brace == -1:
        return []
    entries = object_entries(m, span[0] + brace, span[1])
    if "properties" in entries:
        entries = object_entries(m, *entries["properties"])
    return [k for k in entries if k != "..."]


def extract_tools(m: Masked, path: str) -> list[ToolDef]:
    tools: list[ToolDef] = []
    for call in calls(m, r"registerTool"):
        if len(call.args) < 2:
            continue
        tools.append(_tool_from_config(m, path, call.line, "registerTool", call.args[0], call.args[1], call.start,
                                       call.args[2] if len(call.args) > 2 else None))
    for call in calls(m, r"registerAppTool"):
        if len(call.args) < 3:
            continue
        tools.append(_tool_from_config(m, path, call.line, "registerAppTool", call.args[1], call.args[2], call.start,
                                       call.args[3] if len(call.args) > 3 else None))
    for call in calls(m, r"tool"):
        if not re.search(r"\.\s*tool$", call.callee) or not call.args:
            continue
        name = string_value(m, *call.args[0])
        if name is None:
            continue
        tool = ToolDef(name=name, path=path, line=call.line, api="tool-variadic")
        for span in call.args[1:-1]:
            value = string_value(m, *span)
            if value is not None and tool.description is None:
                tool.description = value
            elif m.code[trim(m.code, *span)[0]] == "{":
                tool.has_input_schema = True
                tool.schema_kind = "raw-shape"
                tool.schema_source = source_of(m, span)
                tool.params = [k for k in object_entries(m, *span) if k != "..."]
                tool.list_limit_max = _limit_max(tool.schema_source)
        headers = enclosing_headers(m, call.start)
        tool.in_loop = any(_LOOP_HEADER.search(h) for h in headers)
        tool.guards, tool.exclusions, tool.function = _guards(m, call.start)
        tool.conditional = any(_COND_HEADER.search(h) for h in headers)
        tool.page_sizes = [g.group(1) for g in _PAGE_SIZE.finditer(m.nocomment[call.args[-1][0]:call.args[-1][1]])]
        tools.append(tool)
    return tools


def extract_resources(m: Masked, path: str) -> list[ResourceDef]:
    out: list[ResourceDef] = []
    for call in calls(m, r"registerAppResource"):
        if len(call.args) >= 3:
            name = string_value(m, *call.args[1]) or source_of(m, trim(m.code, *call.args[1]))
            uri = string_value(m, *call.args[2]) or source_of(m, trim(m.code, *call.args[2]))
            out.append(ResourceDef(name, uri, path, call.line, "registerAppResource", app=True))
    for call in calls(m, r"registerResource|resource"):
        if call.callee.endswith("registerAppResource") or not re.search(r"\.\s*(?:registerResource|resource)$", call.callee):
            continue
        if len(call.args) >= 2:
            name = string_value(m, *call.args[0]) or source_of(m, trim(m.code, *call.args[0]))
            uri = string_value(m, *call.args[1]) or source_of(m, trim(m.code, *call.args[1]))
            out.append(ResourceDef(name, uri, path, call.line, call.callee.split(".")[-1]))
    return out


def extract_prompts(m: Masked, path: str) -> list[PromptDef]:
    out: list[PromptDef] = []
    for call in calls(m, r"registerPrompt|prompt"):
        if not re.search(r"\.\s*(?:registerPrompt|prompt)$", call.callee) or not call.args:
            continue
        name = string_value(m, *call.args[0])
        if name is not None:
            out.append(PromptDef(name, path, call.line, call.callee.split(".")[-1]))
    return out


def read(path: Path) -> Masked:
    return mask(path.read_text(encoding="utf-8", errors="replace"))
