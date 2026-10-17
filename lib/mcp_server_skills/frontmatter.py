"""A small frontmatter reader for `SKILL.md`, eval `prompt.md` and grader files.

The plugin is stdlib-only, so this reads a deliberate subset of YAML:

    key: scalar               strings (bare or quoted), ints, floats, true/false/null
    key: [a, "b c", 3]        inline lists
    key: >-                   a folded block scalar (indented continuation lines)
    key:                      a block list
      - item

Anything else (anchors, flow mappings, nested mappings) raises
`FrontmatterError` naming the line, rather than being misread.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:(?:\s+(.*))?$")


class FrontmatterError(ValueError):
    def __init__(self, message: str, line: int | None = None) -> None:
        self.line = line
        super().__init__(f"line {line}: {message}" if line else message)


@dataclass
class Document:
    meta: dict[str, Any]
    body: str
    has_frontmatter: bool


def split(text: str) -> tuple[list[str] | None, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[1:index], "\n".join(lines[index + 1:]).lstrip("\n")
    raise FrontmatterError("frontmatter opened with --- but never closed", len(lines))


def scalar(raw: str) -> Any:
    value = raw.strip()
    if value in ("", "null", "~"):
        return None
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        return [scalar(part) for part in _split_inline(value[1:-1]) if part.strip()]
    if value.startswith("{"):
        raise FrontmatterError("flow mappings are not supported")
    if re.fullmatch(r"[-+]?\d+", value):
        return int(value)
    if re.fullmatch(r"[-+]?\d+\.\d*", value):
        return float(value)
    return value


def _split_inline(inner: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for char in inner:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            current.append(char)
        elif char == ",":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def parse_header(lines: list[str]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line.startswith((" ", "\t")):
            raise FrontmatterError("unexpected indentation", index + 1)
        match = _KEY.match(line)
        if not match:
            raise FrontmatterError(f"not a key: {line!r}", index + 1)
        key, rest = match.group(1), (match.group(2) or "").strip()
        index += 1
        if rest in (">", ">-", "|", "|-"):
            block: list[str] = []
            while index < len(lines) and (lines[index].startswith((" ", "\t")) or not lines[index].strip()):
                block.append(lines[index].strip())
                index += 1
            joiner = "\n" if rest.startswith("|") else " "
            meta[key] = joiner.join(part for part in block if part).strip()
        elif rest == "":
            items: list[Any] = []
            while index < len(lines) and lines[index].lstrip().startswith("- "):
                items.append(scalar(lines[index].lstrip()[2:]))
                index += 1
            meta[key] = items if items else None
        else:
            meta[key] = scalar(rest)
    return meta


def parse(text: str) -> Document:
    header, body = split(text)
    if header is None:
        return Document({}, body, False)
    return Document(parse_header(header), body, True)


def read(path: str) -> Document:
    with open(path, encoding="utf-8") as handle:
        return parse(handle.read())
