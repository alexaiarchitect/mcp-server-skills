"""The `AUT0xx` review: an MCP server as an OAuth 2.1 resource server.

Two halves. :func:`review_static` reads the inventory (the server's own
sources *and* the workspace packages it depends on, where auth code tends to
live). :func:`review_documents` validates fetched or saved metadata documents —
Protected Resource Metadata (RFC 9728) and authorization server metadata
(RFC 8414 / OpenID Connect Discovery) — and is shared by `check_prm.py` (live)
and the Alexa+ overlay.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .inventory import UnitInventory
from .report import GapReport


def review_static(u: UnitInventory, report: GapReport) -> None:
    s, sup = u.signals, u.support_signals

    def both(key: str) -> list:
        return u.code_hits(key, support=True)

    http = "streamable-http" in u.transports or "sse" in u.transports
    manifest = str(u.unit.path / u.unit.manifest) if u.unit.manifest != "(none)" else str(u.unit.path)
    if not http:
        return  # stdio servers take credentials from the environment (spec: SHOULD NOT use this profile)

    any_auth = any(both(k) for k in ("auth.verify", "auth.www_authenticate", "auth.prm_path", "auth.status_401"))
    if not any_auth:
        report.add("AUT001", "no token verification, challenge or metadata endpoint was found", path=manifest)
        return

    if not both("auth.prm_path"):
        report.add("AUT002", "no route serves `/.well-known/oauth-protected-resource`", path=manifest)
    else:
        if not both("auth.authorization_servers"):
            hit = both("auth.prm_path")[0]
            report.add("AUT003", "the PRM document never names `authorization_servers`", path=hit[0],
                       locator=f"line {hit[1]}")
        prm_hits = both("auth.prm_path")
        texts = [u.line_text(path, line) for path, line in prm_hits]
        if texts and not any("oauth-protected-resource/" in t for t in texts):
            hit = prm_hits[0]
            report.add("AUT004", "PRM is served only at the root well-known location", path=hit[0],
                       locator=f"line {hit[1]}")

    if both("auth.status_401") and not both("auth.resource_metadata"):
        hit = both("auth.status_401")[0]
        report.add("AUT010", "401 responses do not point at the PRM document", path=hit[0], locator=f"line {hit[1]}")

    if s.get("route.tools_call_literal") and s.get("route.body_method") and s.get("auth.status_401"):
        hit = s["route.tools_call_literal"][0]
        report.add("AUT011", "a missing token is rejected only when the body's method is `tools/call`; "
                   "`tools/list`, `resources/read` and the rest are served anonymously",
                   path=hit[0], locator=f"line {hit[1]}")

    if both("auth.verify") and not both("auth.insufficient_scope") and both("auth.security_schemes"):
        hit = both("auth.verify")[0]
        report.add("AUT012", "scopes are enforced per tool but the 403 `insufficient_scope` challenge "
                   "is never produced", path=hit[0], locator=f"line {hit[1]}")

    if both("auth.verify") and not both("auth.audience"):
        hit = both("auth.verify")[0]
        report.add("AUT020", "tokens are verified without an audience / resource check",
                   path=hit[0], locator=f"line {hit[1]}")
    for path, line in (both("auth.passthrough") or [])[:3]:
        kind, detail = classify_relay(u.window(path, line, before=12, after=12))
        if kind == "basic-to-token-endpoint":
            report.add("AUT021", "a token-endpoint façade relays the client's `Basic` client authentication "
                       f"(RFC 6749 §2.3.1) to {detail}; that is client authentication, not a bearer access token, "
                       "so it is allowed — keep the `^Basic ` check that guarantees it",
                       severity="info", path=path, locator=f"line {line}")
        elif kind == "token-endpoint":
            report.add("AUT021", f"the caller's Authorization header is relayed to a token endpoint ({detail}) "
                       "without checking its scheme: `Basic` client authentication is what a token-endpoint "
                       "proxy must relay, a `Bearer` access token must never be — forward it only when it "
                       "matches `^Basic `", severity="warn", path=path, locator=f"line {line}")
        else:
            report.add("AUT021", "the caller's Authorization header (a bearer access token) is forwarded in a "
                       "downstream fetch", path=path, locator=f"line {line}")
    for path, line in (both("auth.decode_only") or [])[:3]:
        report.add("AUT022", "a token is decoded without signature verification", path=path, locator=f"line {line}")
    for path, line in (both("auth.query_token") or [])[:3]:
        report.add("AUT023", "an access token is read from the query string", path=path, locator=f"line {line}")
    for path, line in (both("auth.registration_endpoint") or [])[:2]:
        report.add("AUT030", "a registration endpoint (DCR) is exposed or configured", path=path,
                   locator=f"line {line}")
    if (both("auth.as_path") or both("auth.oidc_path")):
        hit = (both("auth.as_path") or both("auth.oidc_path"))[0]
        if not both("auth.pkce") or not both("auth.s256"):
            report.add("AUT040", "self-hosted authorization server metadata without S256 PKCE",
                       path=hit[0], locator=f"line {hit[1]}")
        if not both("auth.iss_supported"):
            report.add("AUT041", "self-hosted authorization server metadata does not advertise `iss`",
                       path=hit[0], locator=f"line {hit[1]}")
        if not both("auth.cimd"):
            report.add("AUT031", "self-hosted authorization server metadata does not advertise CIMD",
                       path=hit[0], locator=f"line {hit[1]}")
    if u.tools and not both("auth.security_schemes"):
        report.add("AUT050", f"{len(u.tools)} tool(s), none with securitySchemes", path=manifest)
    for path, line in (both("auth.offline_access") or [])[:2]:
        report.add("AUT051", "`offline_access` appears in resource-server metadata or challenges",
                   path=path, locator=f"line {line}")


_TOKEN_ENDPOINT = re.compile(r"(?i)token_?endpoint|/oauth2?/token\b|/token['\"`]|grant_type")
_BASIC_ONLY = re.compile(r"(?i)\^?\s*basic\s|['\"`/]\^Basic|startsWith\(\s*['\"]Basic|\bBasic\b[^\n]{0,40}\.test\(|"
                         r"\.test\([^\n]{0,80}authorization")


def classify_relay(context: str) -> tuple[str, str]:
    """What an Authorization-forwarding fetch relays: ('basic-to-token-endpoint' | 'token-endpoint' | 'bearer', where).

    A token-endpoint façade (a scope-rewriting proxy in front of the
    authorization server's `/oauth2/token`) has to relay the client's HTTP
    Basic credentials; that is OAuth client authentication, not the token
    passthrough the MCP spec forbids.
    """
    target = _TOKEN_ENDPOINT.search(context)
    if not target:
        return "bearer", ""
    where = target.group(0)
    if re.search(r"(?i)\bBasic\b", context) and _BASIC_ONLY.search(context):
        return "basic-to-token-endpoint", where
    return "token-endpoint", where


# -- documents -------------------------------------------------------------------

def review_documents(report: GapReport, *, endpoint: str | None, prm: dict | None, prm_where: str,
                     as_meta: dict | None, as_where: str, alexa: bool = False,
                     token_iss: str | None = None) -> None:
    """Validate PRM and authorization server metadata documents.

    With `alexa`, the Alexa+ account-linking profile replaces advice that does
    not apply to it (CIMD: Alexa+ does not support it, so AUT031 is not raised)
    and adds the Alexa-specific checks: scope discovery from PRM
    `scopes_supported` (ALX054) and an AS metadata `issuer` that differs from the
    `iss` the tokens will carry (ALX055, the metadata-façade case).
    """
    if prm is None:
        report.add("AUT060", "no Protected Resource Metadata document", path=prm_where)
    else:
        missing = [k for k in ("resource", "authorization_servers") if not prm.get(k)]
        if missing:
            report.add("AUT003", f"PRM lacks {', '.join(missing)}", path=prm_where)
        if endpoint and prm.get("resource") and not _same_resource(prm["resource"], endpoint):
            report.add("AUT005", f"PRM resource {prm['resource']!r} vs endpoint {endpoint!r}", path=prm_where)
        if "offline_access" in (prm.get("scopes_supported") or []):
            report.add("AUT051", "`offline_access` is listed in PRM scopes_supported", path=prm_where)
        if alexa:
            _alexa_scopes(report, prm, prm_where)
    if as_meta is None:
        if prm is not None:
            report.add("AUT061", "authorization server metadata was not available", path=as_where)
        return
    methods = as_meta.get("code_challenge_methods_supported") or []
    if "S256" not in methods:
        report.add("AUT040", f"code_challenge_methods_supported = {methods or 'absent'}", path=as_where)
    if not as_meta.get("authorization_response_iss_parameter_supported"):
        report.add("AUT041", "authorization_response_iss_parameter_supported is not true", path=as_where)
    if as_meta.get("registration_endpoint"):
        report.add("AUT030", f"registration_endpoint {as_meta['registration_endpoint']}", path=as_where)
    if not as_meta.get("client_id_metadata_document_supported") and not alexa:
        report.add("AUT031", "client_id_metadata_document_supported is not advertised", path=as_where)
    if alexa:
        _alexa_issuer(report, as_meta, as_where, token_iss)
        grants = as_meta.get("grant_types_supported") or []
        problems = []
        if "S256" not in methods:
            problems.append("no S256")
        if "client_credentials" not in grants:
            problems.append("no client_credentials grant")
        if "authorization_code" not in grants and grants:
            problems.append("no authorization_code grant")
        if problems:
            report.add("ALX051", "; ".join(problems), path=as_where)


ALEXA_SCOPE_NAMES = ("mcp:service", "mcp:tools", "mcp:resources")


def _alexa_scopes(report: GapReport, prm: dict, where: str) -> None:
    scopes = prm.get("scopes_supported") or []
    if not scopes:
        report.add("ALX054", "PRM has no scopes_supported: Alexa+ account linking discovers the scopes it requests "
                   "from it, so it has nothing to ask for", severity="warn", path=where)
        return
    named = [sc for sc in ALEXA_SCOPE_NAMES if sc in scopes]
    if len(named) < len(ALEXA_SCOPE_NAMES):
        report.add("ALX054", f"PRM scopes_supported = {scopes}: the account-linking page says Alexa+ requests "
                   "what PRM advertises, the authentication page names fixed scopes "
                   f"{', '.join(ALEXA_SCOPE_NAMES)}; {'none' if not named else ', '.join(named)} of those are "
                   "advertised — confirm in the simulator which scopes Alexa+ asks for", path=where)


def _origin(url: str) -> str:
    parsed = urlparse(url or "")
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def _alexa_issuer(report: GapReport, as_meta: dict, where: str, token_iss: str | None) -> None:
    issuer = (as_meta.get("issuer") or "").rstrip("/")
    if not issuer:
        return
    if token_iss:
        if token_iss.rstrip("/") != issuer:
            report.add("ALX055", f"AS metadata issuer {issuer!r} but tokens carry iss {token_iss!r}: a client that "
                       "checks `iss` against the metadata it discovered rejects them", severity="warn", path=where)
        return
    elsewhere = [k for k in ("jwks_uri", "token_endpoint") if as_meta.get(k)
                 and _origin(as_meta[k]) != _origin(issuer)]
    if "jwks_uri" in elsewhere:
        report.add("ALX055", f"AS metadata issuer {issuer!r} is served in front of keys at "
                   f"{as_meta['jwks_uri']!r}: a metadata façade. Tokens minted behind it carry the upstream's "
                   "`iss`, not this issuer; check one (`--token-iss`) before linking", severity="info", path=where)


def _same_resource(a: str, b: str) -> bool:
    pa, pb = urlparse(a.rstrip("/")), urlparse(b.rstrip("/"))
    return (pa.scheme.lower(), pa.netloc.lower(), pa.path) == (pb.scheme.lower(), pb.netloc.lower(), pb.path)


def well_known_prm_urls(endpoint: str) -> list[str]:
    """RFC 9728 §3.1: insert the well-known segment between host and path, then the root form."""
    parsed = urlparse(endpoint)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    urls = []
    if path:
        urls.append(f"{base}/.well-known/oauth-protected-resource{path}")
    urls.append(f"{base}/.well-known/oauth-protected-resource")
    return urls


def well_known_as_urls(issuer: str) -> list[str]:
    """RFC 8414 path insertion, then OIDC discovery (both forms), in the order clients try them."""
    parsed = urlparse(issuer)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    urls = []
    if path:
        urls += [f"{base}/.well-known/oauth-authorization-server{path}",
                 f"{base}/.well-known/openid-configuration{path}",
                 f"{base}{path}/.well-known/openid-configuration"]
    else:
        urls += [f"{base}/.well-known/oauth-authorization-server",
                 f"{base}/.well-known/openid-configuration"]
    return urls
