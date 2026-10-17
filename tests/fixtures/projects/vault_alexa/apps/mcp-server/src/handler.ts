import {
  CognitoJwtVerifier,
  protectedResourceMetadata as productionPrm,
  wwwAuthenticate,
  type AuthContext
} from "@bookshelf-vault/auth";
import { loadConfig, loadSecrets, type VaultSecrets } from "@bookshelf-vault/config";
import { asVaultError, VaultError } from "@bookshelf-vault/domain";
import { createTelemetry, XRayRecorder } from "@bookshelf-vault/observability";
import { DynamoVaultRepository } from "@bookshelf-vault/storage";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { S3Client } from "@aws-sdk/client-s3";
import { SQSClient } from "@aws-sdk/client-sqs";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import { createMcpHandler, type AuthInfo } from "@modelcontextprotocol/server";
import type { APIGatewayProxyResult } from "aws-lambda";
import {
  fromResponse,
  json,
  normalizeEvent,
  respond,
  type ApiEvent,
  type NormalizedRequest
} from "./http-event.js";
import {
  authorizationServerMetadata,
  facadeAuthorizeLocation,
  facadeTokenBody,
  protectedResourceMetadata
} from "./oauth.js";
import { alexaAssets } from "./alexa/assets.js";
import { privacyPolicyHtml, termsOfUseHtml } from "./alexa/legal.js";
import { expandAlexaScopes, loadProfile } from "./profile.js";
import { createMcpServer } from "./server.js";

/**
 * `_meta` key under which an AgentCore Gateway REQUEST interceptor forwards the
 * end user's access token to this server (MCP-server targets accept body
 * transforms only). Honoured only when the bearer token itself belongs to a
 * gateway client; always stripped before the SDK sees the request.
 * See docs/identity-passthrough.md.
 */
export const END_USER_TOKEN_META_KEY = "ai.bookshelf.vault/end-user-token";

const config = loadConfig();
const profile = loadProfile(process.env, config.oauthResource);
const metadataUrl = `${profile.publicBaseUrl}/.well-known/oauth-protected-resource/mcp`;
const telemetry = createTelemetry({ serviceName: config.serviceName, logLevel: config.logLevel });
const xray = new XRayRecorder({
  classify: (error) =>
    error instanceof VaultError && error.code !== "INTERNAL_ERROR" ? "error" : "fault"
});

const verifier = new CognitoJwtVerifier({
  issuer: config.cognitoIssuer,
  jwksUri: config.cognitoJwksUri,
  resource: config.oauthResource,
  allowedClientIds: config.oauthAllowedClientIds
});

const repository = new DynamoVaultRepository({
  region: config.region,
  tableName: config.tableName,
  exportBucket: config.exportBucket,
  exportQueueUrl: config.exportQueueUrl,
  dynamo: DynamoDBDocumentClient.from(
    xray.instrumentAwsClient(new DynamoDBClient({ region: config.region }), "DynamoDB"),
    { marshallOptions: { removeUndefinedValues: true } }
  ),
  s3: xray.instrumentAwsClient(new S3Client({ region: config.region }), "S3"),
  sqs: xray.instrumentAwsClient(new SQSClient({ region: config.region }), "SQS")
});

// Resolved on the first invocation (not at init, where no trace is active) so
// the Secrets Manager call shows up as a subsegment of the first request.
let secretsPromise: Promise<VaultSecrets> | undefined;
function secrets(): Promise<VaultSecrets> {
  secretsPromise ??= xray
    .subsegment(
      "SecretsManager",
      (segment) => {
        segment.setAws({ operation: "GetSecretValue" });
        return loadSecrets(config);
      },
      { namespace: "aws" }
    )
    .catch((error: unknown) => {
      secretsPromise = undefined;
      throw error;
    });
  return secretsPromise;
}

/** What the per-request MCP server factory needs, carried through `authInfo.extra`. */
interface RequestScope {
  auth?: AuthContext;
  requestId: string;
  /** HTTP Accept-Language of the request. */
  acceptLanguage?: string;
  /** `params._meta.locale` of the JSON-RPC request. */
  metaLocale?: string;
}

const mcp = createMcpHandler(
  async (ctx) => {
    const scope = ctx.authInfo?.extra?.vault as RequestScope | undefined;
    const loaded = await secrets();
    return createMcpServer({
      repository,
      signingSecret: loaded.signingSecrets,
      signingKeyVersion: loaded.signingKeyVersion,
      pairingSecret: loaded.pairingSecret,
      sharingEnabled: config.sharingEnabled,
      ...(scope?.auth ? { auth: scope.auth } : {}),
      ...(scope?.acceptLanguage ? { acceptLanguage: scope.acceptLanguage } : {}),
      ...(scope?.metaLocale ? { metaLocale: scope.metaLocale } : {}),
      defaultLocale: profile.defaultLocale,
      resourceMetadataUrl: metadataUrl,
      profile: profile.alexa ? "alexa" : "chatgpt",
      onToolCall: (toolEvent) => {
        telemetry.recordToolCall(
          toolEvent.tool,
          toolEvent.outcome,
          toolEvent.durationMs,
          toolEvent.errorCode
        );
        if (
          toolEvent.errorCode === "AUTH_REQUIRED" ||
          toolEvent.errorCode === "INSUFFICIENT_SCOPE"
        ) {
          telemetry.recordAuthFailure(toolEvent.errorCode);
        }
        telemetry.logger.info("MCP tool call", {
          tool: toolEvent.tool,
          outcome: toolEvent.outcome,
          requestId: scope?.requestId,
          correlationId: toolEvent.correlationId,
          durationMs: toolEvent.durationMs,
          ...(toolEvent.errorCode ? { errorCode: toolEvent.errorCode } : {}),
          ...(toolEvent.errorName ? { errorName: toolEvent.errorName } : {}),
          ...(toolEvent.locale
            ? { locale: toolEvent.locale, localeSource: toolEvent.localeSource }
            : {})
        });
      }
    });
  },
  {
    legacy: "stateless",
    responseMode: "json",
    onerror: (error) =>
      telemetry.logger.warn("MCP handler error", {
        errorName: error.name,
        message: error.message.slice(0, 300)
      })
  }
);

interface ParsedBody {
  value: unknown;
  method?: string;
  name?: string;
  /** `params._meta.locale`, when the client sends one (Alexa+ does not document it). */
  metaLocale?: string;
  era: "modern" | "legacy" | "unknown";
}

export function parseBody(body: string): ParsedBody {
  try {
    const value = JSON.parse(body || "null") as unknown;
    if (!value || Array.isArray(value) || typeof value !== "object")
      return { value, era: "unknown" };
    const message = value as {
      method?: unknown;
      params?: { name?: unknown; uri?: unknown; _meta?: Record<string, unknown> };
    };
    const meta = message.params?._meta;
    return {
      value,
      ...(typeof message.method === "string" ? { method: message.method } : {}),
      ...(typeof message.params?.name === "string"
        ? { name: message.params.name }
        : typeof message.params?.uri === "string"
          ? { name: message.params.uri }
          : {}),
      ...(typeof meta?.locale === "string" && meta.locale ? { metaLocale: meta.locale } : {}),
      era: meta && "io.modelcontextprotocol/protocolVersion" in meta ? "modern" : "legacy"
    };
  } catch {
    return { value: undefined, era: "unknown" };
  }
}

/** Remove (and return) the gateway-forwarded end-user token from a parsed JSON-RPC request. */
function takeEndUserToken(parsed: ParsedBody): string | undefined {
  const params = (parsed.value as { params?: { _meta?: Record<string, unknown> } } | undefined)
    ?.params;
  const meta = params?._meta;
  if (!meta || !(END_USER_TOKEN_META_KEY in meta)) return undefined;
  const token = meta[END_USER_TOKEN_META_KEY];
  Reflect.deleteProperty(meta, END_USER_TOKEN_META_KEY);
  return typeof token === "string" ? token.replace(/^Bearer\s+/iu, "") : undefined;
}

function unauthorized(
  request: NormalizedRequest,
  reason: "missing" | "invalid"
): APIGatewayProxyResult {
  const envelope = new VaultError(
    "AUTH_REQUIRED",
    reason === "missing"
      ? "A bearer access token is required"
      : "The bearer access token is invalid or expired"
  ).toEnvelope(request.requestId);
  telemetry.recordAuthFailure(envelope.code);
  telemetry.logger.warn("Authentication failed", {
    requestId: request.requestId,
    errorCode: envelope.code
  });
  // Alexa+ wants a bare 401; the MCP authorization spec wants the challenge.
  // AUTH_CHALLENGE picks one per deployment (docs: ALX050).
  return json(
    401,
    envelope,
    profile.challenge === "bearer" ? { "www-authenticate": wwwAuthenticate(metadataUrl) } : {}
  );
}

export async function authenticate(
  request: NormalizedRequest,
  parsed: ParsedBody
): Promise<{ auth?: AuthContext; rejection?: APIGatewayProxyResult }> {
  const header = request.headers.authorization;
  const forwarded = takeEndUserToken(parsed);
  if (!header) {
    const mustAuthenticate = profile.authAllMethods || parsed.method === "tools/call";
    return mustAuthenticate ? { rejection: unauthorized(request, "missing") } : {};
  }
  try {
    let auth = await xray.subsegment("auth.verify", () =>
      verifier.verifyAuthorizationHeader(header)
    );
    if (forwarded !== undefined) {
      if (!profile.gatewayClientIds.has(auth.clientId)) {
        // A client that is not the gateway cannot speak for somebody else.
        telemetry.logger.warn("Ignored a forwarded end-user token from a non-gateway client", {
          requestId: request.requestId
        });
      } else {
        const user = await xray.subsegment("auth.verify-end-user", () =>
          verifier.verifyToken(forwarded)
        );
        if (profile.gatewayClientIds.has(user.clientId))
          throw new VaultError("AUTH_REQUIRED", "Not an end-user token");
        auth = user;
      }
    }
    if (profile.alexa) auth = { ...auth, scopes: expandAlexaScopes(auth.scopes) };
    return { auth };
  } catch {
    return { rejection: unauthorized(request, "invalid") };
  }
}

async function serveMcp(request: NormalizedRequest): Promise<APIGatewayProxyResult> {
  const parsed = parseBody(request.body);
  const { auth, rejection } = await authenticate(request, parsed);
  if (rejection) return rejection;
  const label = parsed.method
    ? `${parsed.method}${parsed.name ? ` ${parsed.name}` : ""}`
    : request.method;
  return xray.subsegment(`MCP ${label}`, async (segment) => {
    segment.annotate("mcp_method", parsed.method ?? "none");
    segment.annotate("mcp_era", parsed.era);
    segment.annotate("profile", profile.alexa ? "alexa" : "chatgpt");
    if (parsed.name && parsed.method === "tools/call") segment.annotate("tool", parsed.name);
    const headers = new Headers(request.headers);
    headers.delete("content-length");
    headers.delete("host");
    const body = parsed.value === undefined ? request.body : JSON.stringify(parsed.value);
    const webRequest = new Request(new URL("/mcp", profile.publicBaseUrl), {
      method: request.method,
      headers,
      ...(request.method === "GET" || request.method === "HEAD" || request.method === "DELETE"
        ? {}
        : { body })
    });
    const authInfo: AuthInfo = {
      token: "",
      clientId: auth?.clientId ?? "",
      scopes: auth ? [...auth.scopes] : [],
      extra: {
        vault: {
          ...(auth ? { auth } : {}),
          requestId: request.requestId,
          ...(request.headers["accept-language"]
            ? { acceptLanguage: request.headers["accept-language"] }
            : {}),
          ...(parsed.metaLocale ? { metaLocale: parsed.metaLocale } : {})
        } satisfies RequestScope
      }
    };
    const result = await fromResponse(await mcp.fetch(webRequest, { authInfo }));
    segment.setHttpStatus(result.statusCode);
    return result;
  });
}

async function serveFacade(request: NormalizedRequest): Promise<APIGatewayProxyResult | undefined> {
  if (profile.facade !== "rewrite") return undefined;
  if (
    request.method === "GET" &&
    request.path === "/oauth2/authorize" &&
    profile.authorizationEndpoint
  ) {
    return respond(302, "", {
      location: facadeAuthorizeLocation(
        request.query,
        profile.authorizationEndpoint,
        config.oauthResource
      ),
      "cache-control": "no-store"
    });
  }
  if (request.method === "POST" && request.path === "/oauth2/token" && profile.tokenEndpoint) {
    const tokenEndpoint = profile.tokenEndpoint;
    const form = facadeTokenBody(new URLSearchParams(request.body), config.oauthResource);
    const clientBasic = /^Basic [A-Za-z0-9+/=]+$/u.test(request.headers.authorization ?? "")
      ? request.headers.authorization
      : undefined;
    return xray.subsegment(
      "Cognito token",
      async (segment) => {
        segment.document.http = { request: { method: "POST", url: tokenEndpoint } };
        const relayed = await fetch(tokenEndpoint, {
          method: "POST",
          headers: {
            "content-type": "application/x-www-form-urlencoded",
            // OAuth client authentication (RFC 6749 §2.3.1) for the token
            // endpoint itself — never a bearer access token.
            ...(clientBasic ? { authorization: clientBasic } : {})
          },
          body: form.toString(),
          signal: AbortSignal.timeout(3_000)
        });
        segment.setHttpStatus(relayed.status);
        const result = await fromResponse(relayed);
        return {
          ...result,
          headers: { "content-type": "application/json", "cache-control": "no-store" }
        };
      },
      { namespace: "remote" }
    );
  }
  return undefined;
}

async function route(request: NormalizedRequest): Promise<APIGatewayProxyResult> {
  const { method, path } = request;
  if (method === "GET" && path === "/health") return json(200, { status: "ok" });
  if (method === "GET" && path === "/ready") return json(200, { status: "ready" });
  if (
    method === "GET" &&
    ["/.well-known/oauth-protected-resource/mcp", "/.well-known/oauth-protected-resource"].includes(
      path
    )
  ) {
    const document = profile.alexa
      ? protectedResourceMetadata({
          profile,
          resource: config.oauthResource,
          cognitoIssuer: config.cognitoIssuer
        })
      : productionPrm(config.cognitoIssuer, config.oauthResource);
    return json(200, document, { "cache-control": "public, max-age=300" });
  }
  if (
    method === "GET" &&
    profile.alexa &&
    [
      "/.well-known/oauth-authorization-server",
      "/.well-known/oauth-authorization-server/mcp"
    ].includes(path)
  ) {
    return json(200, authorizationServerMetadata({ profile }), {
      "cache-control": "public, max-age=300"
    });
  }
  // Store-listing images for addon.json (HTTPS required). Placeholders today.
  const asset = method === "GET" && profile.alexa && /^\/assets\/([\w.-]+\.png)$/u.exec(path)?.[1];
  if (asset && alexaAssets[asset]) {
    return {
      statusCode: 200,
      headers: { "content-type": "image/png", "cache-control": "public, max-age=86400" },
      body: alexaAssets[asset],
      isBase64Encoded: true
    };
  }
  if (method === "GET" && profile.alexa && (path === "/legal/privacy" || path === "/legal/terms")) {
    return respond(200, path === "/legal/privacy" ? privacyPolicyHtml : termsOfUseHtml, {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "public, max-age=3600"
    });
  }
  const facade = await serveFacade(request);
  if (facade) return facade;
  if (path === "/mcp") return serveMcp(request);
  return json(404, {
    code: "NOT_FOUND",
    message: "Endpoint not found",
    retryable: false,
    correlation_id: request.requestId
  });
}

export async function handler(event: ApiEvent): Promise<APIGatewayProxyResult> {
  const request = normalizeEvent(event);
  try {
    return await route(request);
  } catch (error) {
    telemetry.logger.error("Request failed", {
      requestId: request.requestId,
      errorName: error instanceof Error ? error.name : "Unknown"
    });
    return json(500, asVaultError(error).toEnvelope(request.requestId));
  } finally {
    telemetry.metrics.publishStoredMetrics();
    await xray.flush();
  }
}
