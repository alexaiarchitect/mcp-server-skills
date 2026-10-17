"""The library-desk server on the 2.x Python SDK: serves 2025-11-25 and 2026-07-28 clients."""

from mcp.server.mcpserver import Context, MCPServer

mcp = MCPServer("library-desk")


@mcp.tool()
def search_catalogue(query: str, limit: int = 5) -> list[str]:
    """Use this when a reader asks for books by title. Returns up to five titles."""
    return [query][:limit]


@mcp.tool()
async def reserve(isbn: str, ctx: Context) -> str:
    """Use this to reserve one copy of a book for the reader."""
    return f"reserved {isbn}"


app = mcp.streamable_http_app(json_response=True)
