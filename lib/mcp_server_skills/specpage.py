"""Read the MCP versioning page and the SDK registries for the upgrade loop.

The versioning page states the current revision in one sentence
("The **current** protocol version is [**2026-07-28**](...)"). The page is
served as HTML and as Markdown depending on the client, so the parser accepts
both, and falls back to the newest `/specification/YYYY-MM-DD` link when the
sentence moves. Registry readers take the npm `/<pkg>/latest` document and the
PyPI JSON API. All network access goes through :mod:`jsonrpc`'s `http()`, and
every reader also accepts a saved file so the loop can run offline and in tests.
"""

from __future__ import annotations

import json
import re
from datetime import date

from . import KNOWN_REVISIONS, LATEST_VERSIONS, SPEC_TARGET, SPEC_VERSIONING_URL, changelog_url
from .jsonrpc import http

_CURRENT = re.compile(
    r"current\W{0,12}\s*protocol\s+version\s+is\W{0,40}?(\d{4}-\d{2}-\d{2})", re.I | re.S)
_ANY_REVISION = re.compile(r"/specification/(\d{4}-\d{2}-\d{2})")
_DRAFT = re.compile(r"\bdraft\b[^\n]{0,80}?(\d{4}-\d{2}-\d{2})", re.I)


def current_revision(page: str) -> str | None:
    text = re.sub(r"<[^>]+>", " ", page)
    match = _CURRENT.search(text) or _CURRENT.search(page)
    if match:
        return match.group(1)
    revisions = sorted(set(_ANY_REVISION.findall(page)))
    return revisions[-1] if revisions else None


def revisions_mentioned(page: str) -> list[str]:
    return sorted(set(_ANY_REVISION.findall(page)) | set(re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", page)))


def fetch_versioning(url: str = SPEC_VERSIONING_URL, timeout: float = 20.0) -> tuple[str | None, str | None]:
    reply = http(url, headers={"Accept": "text/markdown, text/html;q=0.9"}, timeout=timeout)
    if reply.error or reply.status != 200:
        return None, reply.error or f"HTTP {reply.status}"
    return reply.body, None


NPM_PACKAGES = ("@modelcontextprotocol/sdk", "@modelcontextprotocol/server", "@modelcontextprotocol/node",
                "@modelcontextprotocol/ext-apps")


def fetch_latest_versions(timeout: float = 20.0) -> tuple[dict[str, str], list[str]]:
    found: dict[str, str] = {}
    errors: list[str] = []
    for pkg in NPM_PACKAGES:
        reply = http(f"https://registry.npmjs.org/{pkg}/latest", timeout=timeout)
        try:
            found[pkg] = json.loads(reply.body)["version"]
        except (ValueError, KeyError, TypeError):
            errors.append(f"{pkg}: {reply.error or reply.status}")
    reply = http("https://pypi.org/pypi/mcp/json", timeout=timeout)
    try:
        found["mcp"] = json.loads(reply.body)["info"]["version"]
    except (ValueError, KeyError, TypeError):
        errors.append(f"mcp: {reply.error or reply.status}")
    return found, errors


def _vt(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version)[:3])


def newer_versions(observed: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Packages whose observed version is newer than the one this plugin was checked against."""
    out = {}
    for pkg, version in observed.items():
        pinned = LATEST_VERSIONS.get(pkg)
        if pinned and _vt(version) > _vt(pinned):
            out[pkg] = (pinned, version)
    return out


def delta_markdown(*, pinned: str, live: str | None, newer: dict[str, tuple[str, str]],
                   source: str, today: str | None = None) -> str:
    today = today or date.today().isoformat()
    lines = [f"# MCP upgrade delta {today}", "",
             f"- Pinned revision: `{pinned}`",
             f"- Current revision on the versioning page: `{live or 'unknown'}` (read from {source})", ""]
    if live and live != pinned and live > pinned:
        lines += [f"## Protocol: {pinned} -> {live}", "",
                  f"Read the changelog first: {changelog_url(live)}", "",
                  "Then, in order:", "",
                  f"1. Re-review against the new revision and keep the old report as the baseline:",
                  f"   `lint_server.py <project> --target {live} --baseline review-{pinned}.json --json`",
                  "2. Plan only what the delta needs: `plan_migration.py <project> --target "
                  f"{live} --json`",
                  "3. Apply the auto steps after confirmation, hand-apply the guided ones.",
                  "4. Verify both eras: `probe.py <url> --legacy`.", ""]
        if live not in KNOWN_REVISIONS:
            lines += [f"> `{live}` is newer than every revision this plugin's rules know. Findings tied to "
                      f"{SPEC_TARGET} still apply; new requirements need new rules in a newer plugin release.", ""]
    else:
        lines += ["## Protocol: no change", "", f"`{pinned}` is still the current revision.", ""]
    if newer:
        lines += ["## SDK releases newer than the plugin's checked versions", ""]
        for pkg, (old, new) in sorted(newer.items()):
            lines.append(f"- `{pkg}`: {old} -> {new}")
        lines.append("")
    return "\n".join(lines)
