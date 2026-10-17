import type { AuthContext } from "@bookshelf/auth";
import { registerAppResource, registerAppTool, RESOURCE_MIME_TYPE } from "@modelcontextprotocol/ext-apps/server";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpError } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

const LOAN_WIDGET_URI = "ui://bookshelf/loan-confirmation.html";

function security(scope: string) {
  return [{ type: "oauth2", scopes: [scope] }];
}

function toolMeta(scope: string, resourceUri?: string) {
  return { securitySchemes: security(scope), ...(resourceUri ? { ui: { resourceUri } } : {}) };
}

export function createShelfServer(options: { auth?: AuthContext }) {
  const server = new McpServer({ name: "Bookshelf", version: "0.1.0" }, { capabilities: { tools: {}, resources: {} } });

  server.registerTool(
    "search_books",
    {
      title: "Search books",
      description: "Use this when a reader asks for books by title, author or subject. Returns matching books.",
      inputSchema: z.object({ query: z.string().min(1), limit: z.number().int().min(1).max(50).optional() }).strict(),
      annotations: { readOnlyHint: true },
      _meta: toolMeta("books.read")
    },
    async ({ query }) => ({ content: [{ type: "text", text: `results for ${query}` }] })
  );

  server.registerTool(
    "get_book",
    {
      title: "Get book",
      description: "Read one book by its catalogue id.",
      inputSchema: z.object({ book_id: z.string() }).strict(),
      _meta: toolMeta("books.read")
    },
    async ({ book_id }) => {
      if (book_id === "missing") throw new McpError(-32002, "Book not found");
      return { content: [{ type: "text", text: book_id }] };
    }
  );

  registerAppTool(
    server,
    "prepare_loan",
    {
      title: "Prepare a loan",
      description: "Create an expiring loan preview that the reader confirms in the widget.",
      inputSchema: z.object({ book_id: z.string(), weeks: z.number().int().min(1).max(4) }).strict(),
      _meta: toolMeta("books.write", LOAN_WIDGET_URI)
    },
    async ({ book_id }) => ({ content: [{ type: "text", text: `loan for ${book_id}` }] })
  );

  registerAppResource(server, "Loan confirmation", LOAN_WIDGET_URI, { mimeType: RESOURCE_MIME_TYPE }, () =>
    Promise.resolve({ contents: [{ uri: LOAN_WIDGET_URI, mimeType: RESOURCE_MIME_TYPE, text: "<html></html>" }] })
  );

  return server;
}
