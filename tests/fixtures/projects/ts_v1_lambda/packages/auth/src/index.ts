import { createRemoteJWKSet, jwtVerify } from "jose";

export type ShelfScope = "books.read" | "books.write";
export const shelfScopes: ShelfScope[] = ["books.read", "books.write"];

export interface AuthContext {
  reader: string;
  scopes: string[];
}

export class TokenVerifier {
  private readonly jwks;
  constructor(private readonly options: { issuer: string; jwksUri: string; resource: string }) {
    this.jwks = createRemoteJWKSet(new URL(options.jwksUri));
  }

  async verifyAuthorizationHeader(header: string): Promise<AuthContext> {
    const token = header.replace(/^Bearer\s+/i, "");
    const { payload } = await jwtVerify(token, this.jwks, {
      issuer: this.options.issuer,
      audience: this.options.resource
    });
    return { reader: String(payload.sub), scopes: String(payload.scope ?? "").split(" ") };
  }
}

export function protectedResourceMetadata(issuer: string, resource: string) {
  return {
    resource,
    authorization_servers: [issuer],
    scopes_supported: shelfScopes,
    bearer_methods_supported: ["header"]
  };
}

export function wwwAuthenticate(resourceMetadataUrl: string, scope?: ShelfScope): string {
  return `Bearer resource_metadata="${resourceMetadataUrl}"${scope ? `, scope="${scope}"` : ""}`;
}
