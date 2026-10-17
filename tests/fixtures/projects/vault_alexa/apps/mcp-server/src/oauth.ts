/**
 * OAuth discovery documents and the optional scope-rewriting façade.
 *
 * Cognito registers custom scopes as `<resourceServerId>/<scope>` and serves
 * only OIDC discovery (`/.well-known/openid-configuration`), while Alexa+
 * reads RFC 8414 authorization-server metadata and — per its authentication
 * page — asks for the bare scopes `mcp:service`, `mcp:tools`, `mcp:resources`.
 * Its account-linking page instead says it requests whatever the protected
 * resource metadata lists in `scopes_supported`. The two pages disagree, so:
 *
 * 1. **Default (`AUTH_FACADE=off`)**: serve PRM and AS metadata that list the
 *    Cognito-qualified scopes and point at Cognito's own endpoints. Nothing
 *    sits between Alexa and Cognito; nothing is rewritten.
 * 2. **Fallback (`AUTH_FACADE=rewrite`)**: if the simulator shows Alexa+
 *    requesting bare `mcp:*` scopes, this function also answers
 *    `/oauth2/authorize` (302 to Cognito with qualified scopes) and
 *    `/oauth2/token` (POST relayed to Cognito with qualified scopes, `resource`
 *    dropped for `client_credentials`, which Cognito does not bind). Tokens are
 *    still minted and signed by Cognito; this code never sees a password and
 *    never stores a token.
 *
 * See docs/identity-passthrough.md and docs/alexa-scopes.md for sources.
 */
import type { Profile } from "./profile.js";

export interface MetadataInput {
  profile: Profile;
  resource: string;
  cognitoIssuer: string;
}

const bareAlexaScopes = new Set(["mcp:service", "mcp:tools", "mcp:resources"]);

export function protectedResourceMetadata({ profile, resource, cognitoIssuer }: MetadataInput) {
  return {
    resource,
    // Alexa+ needs RFC 8414 metadata, which Cognito does not serve; this
    // deployment serves it itself and names itself as the authorization server.
    authorization_servers: [profile.alexa ? profile.asIssuer : cognitoIssuer],
    scopes_supported: profile.advertisedScopes,
    bearer_methods_supported: ["header"],
    resource_documentation: `${profile.publicBaseUrl}/docs/authentication`
  };
}

export function authorizationServerMetadata({ profile }: Pick<MetadataInput, "profile">) {
  const viaFacade = profile.facade === "rewrite";
  const authorization = viaFacade
    ? `${profile.publicBaseUrl}/oauth2/authorize`
    : profile.authorizationEndpoint;
  const token = viaFacade ? `${profile.publicBaseUrl}/oauth2/token` : profile.tokenEndpoint;
  return {
    issuer: profile.asIssuer,
    authorization_endpoint: authorization,
    token_endpoint: token,
    response_types_supported: ["code"],
    grant_types_supported: ["authorization_code", "refresh_token", "client_credentials"],
    code_challenge_methods_supported: ["S256"],
    token_endpoint_auth_methods_supported: ["client_secret_basic", "client_secret_post"],
    scopes_supported: viaFacade
      ? [...profile.advertisedScopes, ...bareAlexaScopes].filter(
          (v, i, all) => all.indexOf(v) === i
        )
      : profile.advertisedScopes
  };
}

/** Rewrite each bare `mcp:*` scope to `<resource>/<scope>`; leave every other scope alone. */
export function qualifyScopes(
  scope: string | null | undefined,
  resource: string
): string | undefined {
  if (!scope) return undefined;
  return scope
    .split(/\s+/u)
    .filter(Boolean)
    .map((item) => (bareAlexaScopes.has(item) ? `${resource}/${item}` : item))
    .join(" ");
}

/** `GET /oauth2/authorize` on the façade: a 302 to Cognito with qualified scopes. */
export function facadeAuthorizeLocation(
  query: URLSearchParams,
  cognitoAuthorizationEndpoint: string,
  resource: string
): string {
  const target = new URL(cognitoAuthorizationEndpoint);
  for (const [key, value] of query) {
    target.searchParams.set(
      key,
      key === "scope" ? (qualifyScopes(value, resource) ?? value) : value
    );
  }
  return target.toString();
}

/** `POST /oauth2/token` on the façade: the form body to relay to Cognito. */
export function facadeTokenBody(form: URLSearchParams, resource: string): URLSearchParams {
  const relay = new URLSearchParams(form);
  const scope = qualifyScopes(relay.get("scope"), resource);
  if (scope) relay.set("scope", scope);
  // Cognito resource binding applies to managed-login (authorization code)
  // flows only; a client_credentials request carrying `resource` is relayed without it.
  if (relay.get("grant_type") === "client_credentials") relay.delete("resource");
  return relay;
}
