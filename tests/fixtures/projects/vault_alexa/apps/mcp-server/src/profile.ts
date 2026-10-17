import { z } from "zod";
import { locales, type Locale } from "./alexa/speech.js";

const csv = z
  .string()
  .default("")
  .transform((value) =>
    value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
  );

const schema = z.object({
  ALEXA_PROFILE: z.enum(["0", "1"]).default("0"),
  /** Public origin of this deployment, e.g. https://alexa.bookshelf.example */
  PUBLIC_BASE_URL: z.url().default("https://mcp.bookshelf.example"),
  /** `omit`: 401 without WWW-Authenticate (Alexa+ quickstart); `bearer`: RFC 6750 / MCP authorization spec. */
  AUTH_CHALLENGE: z.enum(["omit", "bearer"]).optional(),
  /** Require a token for every MCP method, not only tools/call (fixes AUT011). */
  AUTH_ALL_METHODS: z.enum(["true", "false"]).optional(),
  /** Client ids whose tokens are the AgentCore Gateway's outbound credential. */
  GATEWAY_CLIENT_IDS: csv,
  /** Authorization-server metadata (RFC 8414) served at /.well-known/oauth-authorization-server. */
  AS_ISSUER: z.url().optional(),
  AUTHORIZATION_ENDPOINT: z.url().optional(),
  TOKEN_ENDPOINT: z.url().optional(),
  /** Scopes advertised in PRM and AS metadata; defaults to the resource-qualified vault scopes. */
  ADVERTISED_SCOPES: csv,
  /**
   * `off`: metadata only — the advertised endpoints are Cognito's.
   * `rewrite`: this function also serves /oauth2/authorize and /oauth2/token and
   * rewrites bare `mcp:*` scopes to Cognito's `resourceServerId/scope` form.
   */
  AUTH_FACADE: z.enum(["off", "rewrite"]).default("off"),
  /**
   * Alexa profile: the speech locale when a request carries no usable language
   * signal (no tool `locale`, no `_meta.locale`, no supported Accept-Language).
   * The Alexa+ MCP docs do not say how the user's locale reaches the server
   * (docs/ALEXA-FRICTION.md), so each market's deployment can pin its own.
   */
  ALEXA_DEFAULT_LOCALE: z.enum(locales).default("en-US")
});

export interface Profile {
  alexa: boolean;
  publicBaseUrl: string;
  challenge: "omit" | "bearer";
  authAllMethods: boolean;
  gatewayClientIds: Set<string>;
  asIssuer: string;
  authorizationEndpoint?: string;
  tokenEndpoint?: string;
  advertisedScopes: string[];
  facade: "off" | "rewrite";
  defaultLocale: Locale;
}

/** The Alexa-facing scope names (Alexa+ authentication page) and the vault scopes each implies. */
export const alexaScopeImplications: Record<string, readonly string[]> = {
  "mcp:service": [],
  "mcp:tools": ["categories.read", "records.read", "records.write"],
  "mcp:resources": []
};

/** The vault scopes the Alexa resource server registers (shares are not offered by voice). */
export const alexaVaultScopes = [
  "categories.read",
  "categories.write",
  "records.read",
  "records.write",
  "records.delete",
  "records.export"
] as const;

export function loadProfile(
  environment: NodeJS.ProcessEnv = process.env,
  resource?: string
): Profile {
  const parsed = schema.parse(environment);
  const alexa = parsed.ALEXA_PROFILE === "1";
  const base = parsed.PUBLIC_BASE_URL.replace(/\/$/u, "");
  const qualified = (scope: string) => (resource ? `${resource}/${scope}` : scope);
  return {
    alexa,
    publicBaseUrl: base,
    challenge: parsed.AUTH_CHALLENGE ?? (alexa ? "omit" : "bearer"),
    authAllMethods: parsed.AUTH_ALL_METHODS ? parsed.AUTH_ALL_METHODS === "true" : alexa,
    gatewayClientIds: new Set(parsed.GATEWAY_CLIENT_IDS),
    asIssuer: (parsed.AS_ISSUER ?? base).replace(/\/$/u, ""),
    ...(parsed.AUTHORIZATION_ENDPOINT
      ? { authorizationEndpoint: parsed.AUTHORIZATION_ENDPOINT }
      : {}),
    ...(parsed.TOKEN_ENDPOINT ? { tokenEndpoint: parsed.TOKEN_ENDPOINT } : {}),
    advertisedScopes: parsed.ADVERTISED_SCOPES.length
      ? parsed.ADVERTISED_SCOPES
      : alexa
        ? // Least privilege: exactly what the voice tools need (see alexaScopeImplications).
          [...(alexaScopeImplications["mcp:tools"] ?? [])].map(qualified)
        : [],
    facade: parsed.AUTH_FACADE,
    defaultLocale: parsed.ALEXA_DEFAULT_LOCALE
  };
}

/**
 * Add the vault scopes implied by the Alexa-facing `mcp:*` scopes. Applied
 * only on the Alexa profile; a token never gains a scope outside this map.
 */
export function expandAlexaScopes(scopes: ReadonlySet<string>): Set<string> {
  const expanded = new Set(scopes);
  for (const scope of scopes)
    for (const implied of alexaScopeImplications[scope] ?? []) expanded.add(implied);
  return expanded;
}
