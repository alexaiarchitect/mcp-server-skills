"""A minimal MCP-over-HTTP client on `urllib`, for probing servers from any interpreter.

It builds requests for both eras — modern (2026-07-28: `_meta` envelope plus
`MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name` headers) and legacy
(`initialize`, then requests on the negotiated version and session) — sends
them, times them, and reads either a JSON body or an SSE response stream. It
never retries and never follows a redirect to a different origin, so what the
probe reports is what the endpoint did.

Loopback URLs bypass any configured proxy, so tests against a local server
work in sandboxes that force an egress proxy.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from itertools import count
from urllib.parse import urlparse

from . import (
    HEADER_METHOD, HEADER_NAME, HEADER_PROTOCOL_VERSION, HEADER_SESSION, META_CLIENT_CAPABILITIES,
    META_CLIENT_INFO, META_PROTOCOL_VERSION, MCP_NAME_METHODS, SPEC_LEGACY, SPEC_TARGET, __version__,
)

CLIENT_INFO = {"name": "mcp-server-skills-probe", "version": __version__}
USER_AGENT = f"mcp-server-skills/{__version__} (+https://github.com/alexaiarchitect/mcp-server-skills)"
_ids = count(1)


@dataclass
class Reply:
    status: int
    headers: dict[str, str]
    body: str
    elapsed_ms: float
    message: dict | None = None      # the JSON-RPC response object, if one was read
    content_type: str = ""
    error: str | None = None         # transport-level failure (DNS, TLS, timeout)
    sse: bool = False

    @property
    def result(self) -> dict | None:
        return self.message.get("result") if isinstance(self.message, dict) else None

    @property
    def rpc_error(self) -> dict | None:
        return self.message.get("error") if isinstance(self.message, dict) else None

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


def _opener(url: str) -> urllib.request.OpenerDirector:
    host = (urlparse(url).hostname or "").lower()
    handlers: list = [_NoRedirect()]
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost"):
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


def http(url: str, *, method: str = "GET", body: bytes | None = None, headers: dict | None = None,
         timeout: float = 15.0) -> Reply:
    request = urllib.request.Request(url, data=body, method=method,
                                     headers={"User-Agent": USER_AGENT, **(headers or {})})
    started = time.perf_counter()
    try:
        with _opener(url).open(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
            hdrs = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp else b""
        status = exc.code
        hdrs = {k.lower(): v for k, v in (exc.headers or {}).items()}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return Reply(0, {}, "", (time.perf_counter() - started) * 1000, error=str(getattr(exc, "reason", exc)))
    elapsed = (time.perf_counter() - started) * 1000
    text = raw.decode("utf-8", errors="replace")
    return Reply(status, hdrs, text, elapsed, content_type=hdrs.get("content-type", ""))


def _parse_message(reply: Reply, request_id: object) -> None:
    ctype = reply.content_type.split(";")[0].strip().lower()
    if ctype == "text/event-stream":
        reply.sse = True
        last = None
        for block in reply.body.replace("\r\n", "\n").split("\n\n"):
            data = "\n".join(line[5:].lstrip() for line in block.split("\n") if line.startswith("data:"))
            if not data:
                continue
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict) and ("result" in msg or "error" in msg):
                last = msg
                if msg.get("id") == request_id:
                    break
        reply.message = last
        return
    if reply.body.strip().startswith("{"):
        try:
            reply.message = json.loads(reply.body)
        except json.JSONDecodeError:
            reply.message = None


def modern_request(url: str, method: str, params: dict | None = None, *, token: str | None = None,
                   version: str = SPEC_TARGET, header_overrides: dict | None = None,
                   drop_headers: tuple[str, ...] = (), timeout: float = 15.0) -> Reply:
    request_id = next(_ids)
    params = dict(params or {})
    params["_meta"] = {
        META_PROTOCOL_VERSION: version,
        META_CLIENT_INFO: CLIENT_INFO,
        META_CLIENT_CAPABILITIES: {},
        **(params.get("_meta") or {}),
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        HEADER_PROTOCOL_VERSION: version,
        HEADER_METHOD: method,
    }
    if method in MCP_NAME_METHODS:
        headers[HEADER_NAME] = str(params.get("name") or params.get("uri") or "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers.update(header_overrides or {})
    for name in drop_headers:
        headers.pop(name, None)
    body = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}).encode()
    reply = http(url, method="POST", body=body, headers=headers, timeout=timeout)
    _parse_message(reply, request_id)
    return reply


@dataclass
class LegacySession:
    url: str
    token: str | None = None
    version: str = SPEC_LEGACY
    session_id: str | None = None
    negotiated: str | None = None
    timeout: float = 15.0
    log: list[str] = field(default_factory=list)

    def _headers(self, *, after_init: bool) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if after_init and self.negotiated:
            headers[HEADER_PROTOCOL_VERSION] = self.negotiated
        if self.session_id:
            headers[HEADER_SESSION] = self.session_id
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def initialize(self) -> Reply:
        request_id = next(_ids)
        body = {"jsonrpc": "2.0", "id": request_id, "method": "initialize", "params": {
            "protocolVersion": self.version, "capabilities": {}, "clientInfo": CLIENT_INFO}}
        reply = http(self.url, method="POST", body=json.dumps(body).encode(),
                     headers=self._headers(after_init=False), timeout=self.timeout)
        _parse_message(reply, request_id)
        result = reply.result or {}
        self.negotiated = result.get("protocolVersion")
        self.session_id = reply.header(HEADER_SESSION) or self.session_id
        if reply.result is not None:
            note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            http(self.url, method="POST", body=json.dumps(note).encode(),
                 headers=self._headers(after_init=True), timeout=self.timeout)
        return reply

    def request(self, method: str, params: dict | None = None) -> Reply:
        request_id = next(_ids)
        body = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        reply = http(self.url, method="POST", body=json.dumps(body).encode(),
                     headers=self._headers(after_init=True), timeout=self.timeout)
        _parse_message(reply, request_id)
        return reply


def get_json(url: str, *, timeout: float = 15.0) -> tuple[dict | None, Reply]:
    reply = http(url, headers={"Accept": "application/json"}, timeout=timeout)
    if reply.status == 200:
        try:
            data = json.loads(reply.body)
            return (data if isinstance(data, dict) else None), reply
        except json.JSONDecodeError:
            return None, reply
    return None, reply


def parse_www_authenticate(value: str | None) -> dict[str, str]:
    """`Bearer a="b", c=d` -> {"scheme": "Bearer", "a": "b", "c": "d"}."""
    if not value:
        return {}
    import re

    scheme, _, rest = value.strip().partition(" ")
    out = {"scheme": scheme}
    for match in re.finditer(r'([A-Za-z_][\w-]*)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^\s,]+))', rest):
        out[match.group(1)] = match.group(2) if match.group(2) is not None else match.group(3)
    return out


def percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile; None for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    import math

    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]
