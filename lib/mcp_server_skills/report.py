"""Findings, gap reports, baselines and the plugin-wide exit-code contract.

Every script that inspects something emits a `GapReport`: what was discovered,
what is wrong (`findings`), what is missing (`gaps`) and what the user could do
next (`options`). Skills render the markdown form to the user and branch on the
JSON form (`--json`).

A finding's severity, fix and source come from the catalog
(:mod:`mcp_server_skills.catalog`) unless the caller overrides them, so one id
always means one thing wherever it is emitted.

Exit codes (identical in every script):

===  ==========================================================
  0  success, no errors
  1  errors present (or any warning under ``--strict``)
  2  usage or environment error (bad path, unreachable URL)
  3  inconclusive (a check could not run: auth required, page unreachable)
===  ==========================================================
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Literal

SCHEMA = "mcp-server-skills.gap-report/1"

Severity = Literal["error", "warn", "info"]
#: `free` reads files only; `network` fetches public pages or registries;
#: `probe` sends requests to *your* server (invocations, logs, rate limits);
#: `write` edits the project; `deploy` changes something outside it.
CostTier = Literal["free", "network", "probe", "write", "deploy"]

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_INCONCLUSIVE = 3

_SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}
_SEVERITY_ICON = {"error": "\U0001f534", "warn": "\U0001f7e0", "info": "\U0001f535"}
_SEVERITY_HEADING = {"error": "Errors", "warn": "Warnings", "info": "Notes"}


@dataclass
class Finding:
    """One concrete problem, tied to a place and a fix.

    Ids are banded by area — `DSC` discovery, `MCP` protocol review, `AUT`
    authorization, `ALX` Alexa+ overlay, `PRB` live probe, `MIG` migration,
    `CI` workflows, `UPG` upgrade — and are stable across releases.
    """

    id: str
    severity: Severity
    area: str
    message: str
    path: str | None = None
    locator: str | None = None
    fix: str | None = None
    source: str | None = None
    #: The 1-based line the finding anchors to, when one is known. Taken from a
    #: `line N` locator, or found by looking the locator up in `path` (a
    #: dependency name in package.json, say). `file` in the JSON form is `path`.
    line: int | None = None

    def __post_init__(self) -> None:
        if self.line is None:
            self.line = anchor_line(self.path, self.locator)

    def key(self) -> tuple[str, str, str]:
        return (self.id, self.path or "", self.locator or "")

    def to_dict(self) -> dict[str, Any]:
        out = {k: v for k, v in asdict(self).items() if v is not None}
        if self.path:
            out["file"] = self.path
        return out

    def one_line(self, *, relative_to: str | None = None) -> str:
        path = _relative(self.path or "", relative_to)
        where = f"{path} {self.locator}".strip() if self.locator else path
        head = f"{_SEVERITY_ICON[self.severity]} `{self.id}`"
        if where:
            head = f"{head} {where}"
        return f"{head} — {self.message}"


_LINE_LOCATOR = re.compile(r"\bline (\d+)\b")


def anchor_line(path: str | None, locator: str | None) -> int | None:
    """The line a finding points at: `line N` in the locator, else the locator's first occurrence in `path`."""
    if locator:
        match = _LINE_LOCATOR.search(locator)
        if match:
            return int(match.group(1))
    if not path or not locator or not os.path.isfile(path):
        return None
    needle = locator.strip()
    if len(needle) < 3 or os.path.getsize(path) > 2_000_000:
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for number, text in enumerate(handle, 1):
                if f'"{needle}"' in text or f"'{needle}'" in text:
                    return number
    except OSError:
        return None
    return None


def _relative(path: str, base: str | None) -> str:
    if not path or not base:
        return path
    try:
        full = os.path.realpath(path)
        root = os.path.realpath(base)
    except (OSError, ValueError):
        return path
    if full == root:
        return ""
    if full.startswith(root.rstrip(os.sep) + os.sep):
        return full[len(root.rstrip(os.sep)) + 1:]
    return path


@dataclass
class Gap:
    """Something absent rather than wrong."""

    id: str
    what: str
    why: str
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Option:
    """A next action the skill may offer, with what it costs and touches."""

    key: str
    label: str
    detail: str = ""
    recommended: bool = False
    cost: CostTier = "free"
    writes: list[str] = field(default_factory=list)
    runs: list[str] = field(default_factory=list)
    skill: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class GapReport:
    subject: str
    skill: str
    discovered: dict[str, Any] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    options: list[Option] = field(default_factory=list)
    #: Counts of findings this report summarises but does not list (the router's
    #: per-band table): {"errors": n, "warnings": n, "infos": n}. They are added
    #: to `summary` so the closing line agrees with the body.
    rollup: dict[str, int] = field(default_factory=dict)

    # -- building -------------------------------------------------------
    def add(self, id: str, message: str, *, severity: Severity | None = None,
            area: str | None = None, path: str | None = None, locator: str | None = None,
            fix: str | None = None, source: str | None = None) -> Finding:
        """Add a finding; anything not given comes from the catalog entry."""
        from .catalog import lookup

        entry = lookup(id)
        finding = Finding(
            id=id,
            severity=severity or entry.severity,
            area=area or entry.area,
            message=message,
            path=path,
            locator=locator,
            fix=fix if fix is not None else entry.fix,
            source=source if source is not None else entry.source,
        )
        if not any(f.key() == finding.key() for f in self.findings):
            self.findings.append(finding)
        return finding

    def extend(self, findings: Iterable[Finding]) -> None:
        for finding in findings:
            if not any(f.key() == finding.key() for f in self.findings):
                self.findings.append(finding)

    def add_gap(self, id: str, what: str, why: str, recommendation: str) -> Gap:
        gap = Gap(id=id, what=what, why=why, recommendation=recommendation)
        self.gaps.append(gap)
        return gap

    def add_option(self, option: Option) -> Option:
        self.options.append(option)
        return option

    # -- querying -------------------------------------------------------
    def count(self, severity: Severity) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def summary(self) -> dict[str, int]:
        out = {"errors": self.count("error") + self.rollup.get("errors", 0),
               "warnings": self.count("warn") + self.rollup.get("warnings", 0),
               "infos": self.count("info") + self.rollup.get("infos", 0)}
        if self.gaps:
            out["gaps"] = len(self.gaps)
        return out

    def has_errors(self) -> bool:
        return self.count("error") > 0

    def ids(self) -> list[str]:
        return [f.id for f in self.findings]

    def sorted_findings(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (_SEVERITY_ORDER[f.severity], f.id,
                                                    f.path or "", f.locator or ""))

    # -- rendering ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "subject": self.subject,
            "skill": self.skill,
            "discovered": self.discovered,
            "findings": [f.to_dict() for f in self.sorted_findings()],
            "gaps": [g.to_dict() for g in self.gaps],
            "options": [o.to_dict() for o in self.options],
            "summary": self.summary,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_md(self) -> str:
        lines: list[str] = [f"# {self.skill}: {self.subject}", ""]
        if self.discovered:
            lines += ["## Found", ""]
            lines.extend(render_mapping(self.discovered))
            lines.append("")
        if self.gaps:
            lines += ["## Missing", ""]
            for gap in self.gaps:
                lines.append(f"- **{gap.what}** — {gap.why}")
                lines.append(f"  - Recommendation: {gap.recommendation}")
            lines.append("")
        current: str | None = None
        for finding in self.sorted_findings():
            if finding.severity != current:
                if current is not None:
                    lines.append("")
                current = finding.severity
                lines += [f"## {_SEVERITY_HEADING[current]}", ""]
            lines.append(f"- {finding.one_line(relative_to=self.subject)}")
            if finding.fix:
                lines.append(f"  - Fix: {finding.fix}")
            if finding.source:
                lines.append(f"  - Source: {finding.source}")
        if self.findings:
            lines.append("")
        if self.options:
            lines += ["## Options", ""]
            for option in self.options:
                mark = " **(recommended)**" if option.recommended else ""
                lines.append(f"{option.key}. **{option.label}**{mark} — cost: {option.cost}")
                if option.detail:
                    lines.append(f"   - {option.detail}")
                if option.skill:
                    lines.append(f"   - Skill: `{option.skill}`")
                if option.writes:
                    lines.append(f"   - Writes: {', '.join(option.writes)}")
                if option.runs:
                    lines.append(f"   - Runs: {', '.join(option.runs)}")
            lines.append("")
        s = self.summary
        tail = f", {s['gaps']} gap(s)" if s.get("gaps") else ""
        scope = " across the review bands above" if self.rollup else ""
        lines.append(f"_Summary: {s['errors']} error(s), {s['warnings']} warning(s), "
                     f"{s['infos']} note(s){tail}{scope}._")
        return "\n".join(lines)

    def render(self, fmt: str) -> str:
        return self.to_json() if fmt == "json" else self.to_md()


def render_mapping(data: dict[str, Any], depth: int = 0) -> list[str]:
    """Render nested discovery data as an indented markdown list."""
    pad = "  " * depth
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, dict):
            if not value:
                lines.append(f"{pad}- **{key}**: (none)")
                continue
            lines.append(f"{pad}- **{key}**")
            lines.extend(render_mapping(value, depth + 1))
        elif isinstance(value, list):
            if not value:
                lines.append(f"{pad}- **{key}**: (none)")
            elif all(not isinstance(v, (dict, list)) for v in value):
                lines.append(f"{pad}- **{key}**: {', '.join(str(v) for v in value)}")
            else:
                lines.append(f"{pad}- **{key}**: {len(value)} item(s)")
                for item in value:
                    if isinstance(item, dict):
                        inline = ", ".join(f"{k}={v}" for k, v in item.items()
                                           if not isinstance(v, (dict, list)) and v not in (None, ""))
                        lines.append(f"{pad}  - {inline}")
                        nested = {k: v for k, v in item.items() if isinstance(v, (dict, list))}
                        if nested:
                            lines.extend(render_mapping(nested, depth + 2))
                    else:
                        lines.append(f"{pad}  - {item}")
        else:
            shown = "(none)" if value in (None, "") else value
            lines.append(f"{pad}- **{key}**: {shown}")
    return lines


def exit_code_for(report: GapReport, *, strict: bool = False, inconclusive: bool = False) -> int:
    """Map a report to the plugin-wide exit-code contract."""
    if report.has_errors():
        return EXIT_FINDINGS
    if strict and report.count("warn"):
        return EXIT_FINDINGS
    if inconclusive:
        return EXIT_INCONCLUSIVE
    return EXIT_OK


# -- baselines ----------------------------------------------------------------

def load_findings(path: str) -> list[Finding]:
    """Read the findings of a previously saved `--json` report."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    out: list[Finding] = []
    for raw in data.get("findings", []):
        out.append(Finding(
            id=raw["id"], severity=raw.get("severity", "info"), area=raw.get("area", ""),
            message=raw.get("message", ""), path=raw.get("path") or raw.get("file"),
            locator=raw.get("locator"), fix=raw.get("fix"), source=raw.get("source"), line=raw.get("line"),
        ))
    return out


def diff_findings(before: Iterable[Finding], after: Iterable[Finding],
                  *, relative_to: str | None = None) -> dict[str, list[str]]:
    """Which findings are new, resolved and unchanged between two reports.

    Findings are matched on id, path relative to the subject, and locator, so
    the same project reviewed from two checkouts still lines up.
    """
    def keyed(items: Iterable[Finding]) -> dict[tuple[str, str, str], Finding]:
        return {(f.id, _relative(f.path or "", relative_to) or (f.path or ""), f.locator or ""): f
                for f in items}

    old, new = keyed(before), keyed(after)
    label = lambda k: " ".join(part for part in k if part)  # noqa: E731
    return {
        "new": sorted(label(k) for k in new.keys() - old.keys()),
        "resolved": sorted(label(k) for k in old.keys() - new.keys()),
        "unchanged": sorted(label(k) for k in new.keys() & old.keys()),
    }
