import { protectedResourceMetadata, TokenVerifier, wwwAuthenticate, type AuthContext } from "@bookshelf/auth";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import type { APIGatewayProxyEventV2, APIGatewayProxyStructuredResultV2 } from "aws-lambda";
import { createShelfServer } from "./server.js";

const issuer = process.env.SHELF_ISSUER ?? "https://auth.example.org";
const resource = "https://mcp.bookshelf.example/mcp";
const metadataUrl = "https://mcp.bookshelf.example/.well-known/oauth-protected-resource/mcp";
const verifier = new TokenVerifier({ issuer, jwksUri: `${issuer}/.well-known/jwks.json`, resource });

function json(statusCode: number, body: unknown, headers: Record<string, string> = {}): APIGatewayProxyStructuredResultV2 {
  return { statusCode, headers: { "content-type": "application/json", ...headers }, body: JSON.stringify(body) };
}

// The gate only needs the JSON-RPC method name, so it peeks at the body.
function requestMethod(body: string | undefined): string | undefined {
  try {
    const parsed = JSON.parse(body ?? "null") as unknown;
    return parsed && typeof parsed === "object" && "method" in parsed ? String(parsed.method) : undefined;
  } catch {
    return undefined;
  }
}

export async function handler(event: APIGatewayProxyEventV2): Promise<APIGatewayProxyStructuredResultV2> {
  const path = event.rawPath;
  const method = event.requestContext.http.method;
  if (method === "GET" && path === "/.well-known/oauth-protected-resource/mcp") {
    return json(200, protectedResourceMetadata(issuer, resource), { "cache-control": "public, max-age=300" });
  }
  if (path !== "/mcp") return json(404, { message: "not found" });
  if (method !== "POST") return json(405, { message: "Only POST is supported" }, { allow: "POST" });

  let auth: AuthContext | undefined;
  const authorization = event.headers["authorization"];
  if (authorization) {
    try {
      auth = await verifier.verifyAuthorizationHeader(authorization);
    } catch {
      return json(401, { message: "invalid token" }, { "www-authenticate": wwwAuthenticate(metadataUrl) });
    }
  } else if (requestMethod(event.body) === "tools/call") {
    return json(401, { message: "token required" }, { "www-authenticate": wwwAuthenticate(metadataUrl) });
  }

  const server = createShelfServer({ ...(auth ? { auth } : {}) });
  const transport = new WebStandardStreamableHTTPServerTransport({ enableJsonResponse: true });
  await server.connect(transport);
  try {
    const request = new Request(new URL(path, "https://mcp.bookshelf.example"), {
      method,
      headers: event.headers as Record<string, string>,
      body: event.body ?? ""
    });
    const response = await transport.handleRequest(request);
    return {
      statusCode: response.status,
      headers: Object.fromEntries(response.headers.entries()),
      body: await response.text()
    };
  } finally {
    await server.close();
  }
}
