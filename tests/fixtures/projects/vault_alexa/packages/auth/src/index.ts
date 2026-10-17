import { deriveOwnerReference, VaultError } from "@bookshelf-vault/domain";
import { createRemoteJWKSet, jwtVerify, type JWTPayload, type JWTVerifyGetKey } from "jose";

export const vaultScopes = [
  "categories.read",
  "categories.write",
  "records.read",
  "records.write",
  "records.delete",
  "records.export",
  "shares.read",
  "shares.write"
] as const;

export type VaultScope = (typeof vaultScopes)[number];

export interface AuthContext {
  owner: string;
  issuer: string;
  subject: string;
  clientId: string;
  scopes: Set<string>;
  claims: JWTPayload;
}

export interface JwtVerifierOptions {
  issuer: string;
  jwksUri: string;
  resource: string;
  allowedClientIds: string[];
  jwks?: JWTVerifyGetKey;
}

export class CognitoJwtVerifier {
  private readonly issuer: string;
  private readonly resource: string;
  private readonly clients: Set<string>;
  private readonly jwks: JWTVerifyGetKey;

  constructor(options: JwtVerifierOptions) {
    this.issuer = options.issuer.replace(/\/$/u, "");
    this.resource = options.resource;
    this.clients = new Set(options.allowedClientIds);
    this.jwks =
      options.jwks ??
      createRemoteJWKSet(new URL(options.jwksUri), {
        cooldownDuration: 30_000,
        cacheMaxAge: 10 * 60_000,
        timeoutDuration: 3_000
      });
  }

  async verifyAuthorizationHeader(header: string | undefined): Promise<AuthContext> {
    const match = /^Bearer ([A-Za-z0-9._~-]+)$/u.exec(header ?? "");
    if (!match?.[1])
      throw new VaultError("AUTH_REQUIRED", "A valid bearer access token is required");
    return this.verifyToken(match[1]);
  }

  /**
   * Verify a bare access token (no `Bearer ` prefix). Used for the end-user
   * token an AgentCore Gateway interceptor forwards inside the request, which
   * is held to exactly the same checks as a header token.
   */
  async verifyToken(token: string): Promise<AuthContext> {
    if (!/^[A-Za-z0-9._~-]+$/u.test(token))
      throw new VaultError("AUTH_REQUIRED", "A valid bearer access token is required");
    try {
      const { payload } = await jwtVerify(token, this.jwks, {
        issuer: this.issuer,
        algorithms: ["RS256"],
        clockTolerance: 5,
        requiredClaims: ["sub", "iss", "exp", "iat"]
      });
      if (payload.token_use !== "access")
        throw new VaultError("AUTH_REQUIRED", "Only access tokens are accepted");
      const subject = payload.sub;
      if (typeof subject !== "string" || !subject)
        throw new VaultError("AUTH_REQUIRED", "The access token subject is invalid");
      const clientId =
        typeof payload.client_id === "string"
          ? payload.client_id
          : typeof payload.azp === "string"
            ? payload.azp
            : "";
      if (!clientId || !this.clients.has(clientId))
        throw new VaultError("AUTH_REQUIRED", "The OAuth client is not authorized");
      const scopeClaim = typeof payload.scope === "string" ? payload.scope : "";
      const granted = scopeClaim.split(/\s+/u).filter(Boolean);
      this.assertAudience(payload, granted);
      return {
        owner: deriveOwnerReference(this.issuer, subject),
        issuer: this.issuer,
        subject,
        clientId,
        scopes: this.normalizeScopes(granted),
        claims: payload
      };
    } catch (error) {
      if (error instanceof VaultError) throw error;
      throw new VaultError("AUTH_REQUIRED", "The bearer access token is invalid or expired");
    }
  }

  /**
   * Cognito registers custom scopes fully qualified by the resource server
   * identifier, so the token carries `https://mcp.example/mcp/records.read`
   * while the application reasons about `records.read`. Scopes belonging to a
   * different resource server are dropped rather than shortened, so they can
   * never satisfy a requirement here.
   */
  private normalizeScopes(granted: readonly string[]): Set<string> {
    const prefix = `${this.resource}/`;
    const scopes = new Set<string>();
    for (const scope of granted) {
      if (scope.startsWith(prefix)) scopes.add(scope.slice(prefix.length));
      else if (!scope.includes("/")) scopes.add(scope);
    }
    return scopes;
  }

  /**
   * Authorization-code tokens carry `aud`; Cognito machine-to-machine tokens
   * omit it entirely. For those, requiring every granted scope to belong to this
   * resource server is equivalent evidence that the token was minted for this
   * API, which is what RFC 8707 audience restriction is protecting against.
   */
  private assertAudience(payload: JWTPayload, granted: readonly string[]): void {
    const claim = payload.aud;
    const audiences = typeof claim === "string" ? [claim] : Array.isArray(claim) ? claim : [];
    const wrongResource = new VaultError(
      "AUTH_REQUIRED",
      "The access token was issued for another resource"
    );
    if (audiences.length) {
      if (!audiences.includes(this.resource)) throw wrongResource;
      return;
    }
    const prefix = `${this.resource}/`;
    if (!granted.length || !granted.every((scope) => scope.startsWith(prefix))) throw wrongResource;
  }
}

export function requireScopes(
  context: AuthContext | undefined,
  scopes: readonly VaultScope[]
): AuthContext {
  if (!context) throw new VaultError("AUTH_REQUIRED", "Authentication is required");
  const missing = scopes.filter((scope) => !context.scopes.has(scope));
  if (missing.length) {
    throw new VaultError("INSUFFICIENT_SCOPE", "The access token lacks a required scope", {
      details: { required: missing }
    });
  }
  return context;
}

export function protectedResourceMetadata(issuer: string, resource: string) {
  return {
    resource,
    authorization_servers: [issuer],
    scopes_supported: vaultScopes,
    bearer_methods_supported: ["header"],
    resource_documentation: "https://mcp.bookshelf.example/docs/authentication"
  };
}

export function wwwAuthenticate(resourceMetadataUrl: string, scope?: VaultScope): string {
  return `Bearer resource_metadata="${resourceMetadataUrl}"${scope ? `, scope="${scope}"` : ""}`;
}
