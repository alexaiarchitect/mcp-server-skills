#!/usr/bin/env python3
"""Fetch and validate an MCP server's OAuth metadata documents, the way a client finds them.

Starting from the MCP endpoint URL it follows the discovery chain of the
2026-07-28 authorization spec:

1. Protected Resource Metadata (RFC 9728) at the path-inserted well-known URL
   (`/.well-known/oauth-protected-resource/<path>`), then the root one;
2. the first `authorization_servers` entry's metadata: RFC 8414 path insertion,
   then OpenID Connect Discovery.

It checks `resource` against the endpoint, `authorization_servers`, PKCE `S256`,
`authorization_response_iss_parameter_supported`, DCR (`registration_endpoint`,
Deprecated) versus Client ID Metadata Documents, and `offline_access`. With
`--alexa` it applies the Alexa+ account-linking profile instead of the generic
advice that does not fit it: `client_credentials` alongside `authorization_code`
and S256 (ALX051); scopes discovered from PRM `scopes_supported` against the
fixed `mcp:*` names of the authentication page (ALX054); an AS metadata
`issuer` that is not the `iss` the tokens carry (ALX055 — pass `--token-iss`
to compare with a real token's issuer); and no CIMD recommendation (AUT031),
because Alexa+ does not support CIMD.

No token is sent. Offline, pass saved documents with `--prm-file` / `--as-file`.

    check_prm.py <mcp-url> [--alexa [--token-iss URL]] [--json] [--strict] [--timeout s]
    check_prm.py --prm-file prm.json [--as-file as.json] [--endpoint url] [--alexa] [--json]

Exit codes: 0 no errors, 1 errors, 2 usage, 3 a document could not be fetched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from mcp_server_skills.auth_rules import review_documents, well_known_as_urls, well_known_prm_urls  # noqa: E402
from mcp_server_skills.cli import add_output, emit, fail, parser  # noqa: E402
from mcp_server_skills.jsonrpc import get_json  # noqa: E402
from mcp_server_skills.report import EXIT_INCONCLUSIVE, GapReport, Option  # noqa: E402


def _load(path: str) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    p = parser(__doc__)
    p.add_argument("url", nargs="?", help="the MCP endpoint, e.g. https://mcp.example.com/mcp")
    p.add_argument("--prm-file", help="a saved Protected Resource Metadata document")
    p.add_argument("--as-file", help="a saved authorization server metadata document")
    p.add_argument("--endpoint", help="the MCP endpoint the PRM should name (with --prm-file)")
    p.add_argument("--alexa", action="store_true", help="also apply the Alexa+ account-linking profile")
    p.add_argument("--token-iss", help="the `iss` claim of a real access token (with --alexa: compared with the "
                   "AS metadata issuer)")
    p.add_argument("--timeout", type=float, default=15.0)
    add_output(p)
    args = p.parse_args(argv)
    if not args.url and not args.prm_file:
        return fail("give an MCP endpoint URL or --prm-file")

    endpoint = args.url or args.endpoint
    report = GapReport(subject=endpoint or args.prm_file, skill="mcp-auth")
    tried: list[dict] = []
    prm = as_meta = None
    prm_where = as_where = ""
    inconclusive = False
    if args.prm_file:
        prm, prm_where = _load(args.prm_file), args.prm_file
    else:
        for url in well_known_prm_urls(args.url):
            data, reply = get_json(url, timeout=args.timeout)
            tried.append({"url": url, "status": reply.status or reply.error})
            if data is not None:
                prm, prm_where = data, url
                break
        if prm is None:
            prm_where = tried[0]["url"] if tried else ""
            inconclusive = all(t["status"] == 0 or isinstance(t["status"], str) for t in tried)
    if args.as_file:
        as_meta, as_where = _load(args.as_file), args.as_file
    elif prm and prm.get("authorization_servers"):
        issuer = prm["authorization_servers"][0]
        for url in well_known_as_urls(issuer):
            data, reply = get_json(url, timeout=args.timeout)
            tried.append({"url": url, "status": reply.status or reply.error})
            if data is not None:
                as_meta, as_where = data, url
                break
        as_where = as_where or issuer
    review_documents(report, endpoint=endpoint, prm=prm, prm_where=prm_where, as_meta=as_meta,
                     as_where=as_where, alexa=args.alexa, token_iss=args.token_iss)
    report.discovered = {
        "endpoint": endpoint,
        "prm": {k: prm.get(k) for k in ("resource", "authorization_servers", "scopes_supported",
                                        "bearer_methods_supported")} if prm else None,
        "prm_location": prm_where,
        "authorization_server": {k: as_meta.get(k) for k in (
            "issuer", "code_challenge_methods_supported", "grant_types_supported", "registration_endpoint",
            "authorization_response_iss_parameter_supported", "client_id_metadata_document_supported",
            "token_endpoint_auth_methods_supported", "jwks_uri", "token_endpoint")} if as_meta else None,
        "as_location": as_where,
        "fetched": tried,
    }
    report.add_option(Option("1", "Fix the metadata at its source (the route that serves it, or the "
                             "authorization server's settings)", cost="write"))
    report.add_option(Option("2", "Re-check end to end with the probe", skill="/mcp-server:mcp-verify",
                             cost="probe", runs=["probe.py <url>"]))
    if inconclusive:
        report.discovered["note"] = "nothing could be fetched; the server's metadata was not judged"
        return emit(report, args, code=EXIT_INCONCLUSIVE)
    return emit(report, args)


if __name__ == "__main__":
    raise SystemExit(main())
