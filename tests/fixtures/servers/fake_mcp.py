"""A tiny in-process MCP server for probing, in several deliberately different shapes.

Modes:

- ``dual``        2026-07-28 per request (headers validated, resultType, cache
                  hints, serverInfo) and the 2025-11-25 handshake; GET -> 405.
- ``legacy``      handshake only, like a 1.x SDK transport: modern requests get
                  a 400 whose body is not a recognised modern error.
- ``lax``         answers modern requests but validates no headers and omits
                  resultType and cache hints.
- ``modern``      2026-07-28 only; `initialize` is refused with -32022.

``token`` makes every MCP request require ``Authorization: Bearer <token>``;
the Protected Resource Metadata and authorization server metadata stay public.
``challenge=False`` answers 401 without ``WWW-Authenticate`` (the Alexa+ shape).
``delay`` adds seconds to every MCP response, for latency-budget tests.
``auth_get=True`` authenticates GET on /mcp too (auth before method): an
anonymous GET gets 401, a GET with the token gets 405.

Run standalone: ``python3 fake_mcp.py --mode dual --port 8765``.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOOLS = [
    {"name": "search_books", "description": "Use this when a reader asks for books by title or author. "
     "Returns up to five matches.", "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string"}, "limit": {"type": "integer", "maximum": 5}}, "required": ["query"]}},
    {"name": "reserve_book", "description": "Use this to reserve one copy of a book for the reader.",
     "inputSchema": {"type": "object", "properties": {"isbn": {"type": "string"}}, "required": ["isbn"]}},
]


def make_handler(mode: str, token: str | None, challenge: bool, delay: float, auth_get: bool = False):
    class Handler(BaseHTTPRequestHandler):
        server_version = "fake-mcp/1"

        def log_message(self, *args):  # silence
            pass

        def _send(self, status: int, body: dict | None = None, headers: dict | None = None):
            data = json.dumps(body).encode() if body is not None else b""
            self.send_response(status)
            if body is not None:
                self.send_header("Content-Type", "application/json")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        @property
        def base(self) -> str:
            return f"http://{self.headers.get('Host')}"

        def do_GET(self):
            if self.path in ("/.well-known/oauth-protected-resource/mcp", "/.well-known/oauth-protected-resource"):
                return self._send(200, {"resource": f"{self.base}/mcp", "authorization_servers": [f"{self.base}/as"],
                                        "scopes_supported": ["books.read"], "bearer_methods_supported": ["header"]})
            if self.path == "/.well-known/oauth-authorization-server/as":
                return self._send(200, {"issuer": f"{self.base}/as", "authorization_endpoint": f"{self.base}/as/authorize",
                                        "token_endpoint": f"{self.base}/as/token",
                                        "code_challenge_methods_supported": ["S256"],
                                        "grant_types_supported": ["authorization_code", "refresh_token"],
                                        "registration_endpoint": f"{self.base}/as/register"})
            if self.path == "/mcp" and auth_get and token and self.headers.get("Authorization") != f"Bearer {token}":
                return self._send(401, {"error": "unauthorized"})
            if self.path == "/mcp":
                return self._send(405, {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Method not allowed"}},
                                  {"Allow": "POST"})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            if delay:
                time.sleep(delay)
            if token and self.headers.get("Authorization") != f"Bearer {token}":
                hdrs = {"WWW-Authenticate": f'Bearer resource_metadata="{self.base}/.well-known/oauth-protected-resource/mcp"'} \
                    if challenge else {}
                return self._send(401, {"error": "unauthorized"}, hdrs)
            try:
                msg = json.loads(raw)
            except ValueError:
                return self._send(400, {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}})
            method = msg.get("method")
            rid = msg.get("id")
            params = msg.get("params") or {}
            meta = params.get("_meta") or {}
            modern = "io.modelcontextprotocol/protocolVersion" in meta
            if rid is None:
                return self._send(202)
            if method == "initialize":
                if mode == "modern":
                    return self._send(400, {"jsonrpc": "2.0", "id": rid, "error": {
                        "code": -32022, "message": "Unsupported protocol version",
                        "data": {"supported": ["2026-07-28"], "requested": params.get("protocolVersion")}}})
                return self._send(200, {"jsonrpc": "2.0", "id": rid, "result": {
                    "protocolVersion": params.get("protocolVersion", "2025-11-25"),
                    "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "1"}}})
            if not modern:
                if mode == "modern":
                    return self._send(400, {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": "missing _meta"}})
                if method == "tools/list":
                    return self._send(200, {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
                return self._send(404, {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}})
            if mode == "legacy":
                return self._send(400, {"jsonrpc": "2.0", "id": None, "error": {
                    "code": -32000, "message": "Bad Request: Server not initialized"}})
            if mode != "lax":
                header_method = self.headers.get("Mcp-Method")
                if header_method != method:
                    return self._send(400, {"jsonrpc": "2.0", "id": rid, "error": {
                        "code": -32020, "message": f"Header mismatch: Mcp-Method {header_method!r} vs {method!r}"}})
            extra = {} if mode == "lax" else {"resultType": "complete", "ttlMs": 60000, "cacheScope": "private",
                                               "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "fake", "version": "1"}}}
            if method == "server/discover":
                result = {"supportedVersions": ["2026-07-28", "2025-11-25"] if mode == "dual" else ["2026-07-28"],
                          "capabilities": {"tools": {}}, **extra}
            elif method == "tools/list":
                result = {"tools": TOOLS, **extra}
            else:
                return self._send(404, {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}})
            return self._send(200, {"jsonrpc": "2.0", "id": rid, "result": result})

    return Handler


def serve(mode: str = "dual", *, token: str | None = None, challenge: bool = True, delay: float = 0.0,
          port: int = 0, auth_get: bool = False) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(mode, token, challenge, delay, auth_get))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/mcp"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", default="dual", choices=("dual", "legacy", "lax", "modern"))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--token")
    args = ap.parse_args()
    srv, url = serve(args.mode, token=args.token, port=args.port)
    print(url, flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        srv.shutdown()
