import express from "express";
import { createRemoteJWKSet, jwtVerify } from "jose";
import { createMcpHandler, McpServer } from "@modelcontextprotocol/server";
import { toNodeHandler } from "@modelcontextprotocol/node";
import * as z from "zod/v4";

const RESOURCE = "https://reading-room.example/mcp";
const ISSUER = "https://auth.reading-room.example";
const jwks = createRemoteJWKSet(new URL(`${ISSUER}/.well-known/jwks.json`));
const challenge = `Bearer resource_metadata="https://reading-room.example/.well-known/oauth-protected-resource/mcp"`;

function buildServer(): McpServer {
  const server = new McpServer(
    { name: "reading-room", version: "1.0.0" },
    { capabilities: { tools: {} }, cacheHints: { "tools/list": { ttlMs: 300_000, cacheScope: "private" } } }
  );
  server.registerTool(
    "find_seat",
    {
      description: "Use this when a reader wants a free seat in the reading room. Returns up to five seats.",
      inputSchema: z.object({ zone: z.string().optional(), limit: z.number().int().min(1).max(5).optional() }),
      _meta: { securitySchemes: [{ type: "oauth2", scopes: ["seats.read"] }] }
    },
    async ({ zone }) => ({ content: [{ type: "text", text: `seat in ${zone ?? "any zone"}` }] })
  );
  return server;
}

const mcp = createMcpHandler(buildServer);
const app = express();

app.get("/.well-known/oauth-protected-resource/mcp", (_req, res) => {
  res.json({ resource: RESOURCE, authorization_servers: [ISSUER], scopes_supported: ["seats.read"] });
});

app.all("/mcp", async (req, res, next) => {
  const header = req.headers.authorization ?? "";
  try {
    const { payload } = await jwtVerify(header.replace(/^Bearer /, ""), jwks, { issuer: ISSUER, audience: RESOURCE });
    if (!String(payload.scope ?? "").includes("seats.read")) {
      res.status(403).set("www-authenticate", `${challenge}, error="insufficient_scope", scope="seats.read"`).end();
      return;
    }
    next();
  } catch {
    res.status(401).set("www-authenticate", challenge).end();
  }
}, toNodeHandler(mcp));

app.listen(3000, "127.0.0.1");
