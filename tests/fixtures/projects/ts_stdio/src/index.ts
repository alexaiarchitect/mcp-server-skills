#!/usr/bin/env node
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { PingRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

const server = new McpServer({ name: "shelf-cli", version: "0.3.0" });

// Old-style registration with a raw shape.
server.tool("lookup", "Look a book up by ISBN", { isbn: z.string() }, async ({ isbn }) => ({
  content: [{ type: "text", text: isbn }]
}));
server.tool("lookup", "Look a book up again", { isbn: z.string() }, async ({ isbn }) => ({
  content: [{ type: "text", text: isbn }]
}));

const shelves: Record<string, string> = { fiction: "F", history: "H" };
for (const [shelf, code] of Object.entries(shelves)) {
  server.registerTool(`list_${shelf}`, { inputSchema: z.object({}) }, async () => ({
    content: [{ type: "text", text: code }]
  }));
}

server.registerTool("shelve book", { description: "Put a book back", inputSchema: z.object({ isbn: z.string() }) },
  async ({ isbn }, extra) => {
    const answer = await server.server.elicitInput({ message: "Which shelf?", requestedSchema: { type: "object", properties: {} } });
    await server.server.sendLoggingMessage({ level: "info", data: `shelved ${isbn}` });
    return { content: [{ type: "text", text: JSON.stringify(answer) }] };
  });

server.server.setRequestHandler(PingRequestSchema, async () => ({}));

console.log("shelf-cli MCP server starting");
await server.connect(new StdioServerTransport());
