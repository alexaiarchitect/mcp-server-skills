"""A small library-desk MCP server on the 1.x Python SDK (FastMCP)."""

from mcp.server.fastmcp import Context, FastMCP
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

mcp = FastMCP("library-desk", host="127.0.0.1", port=8000, stateless_http=True, json_response=True)

BOOKS = {"9780141439518": "Pride and Prejudice"}


@mcp.tool()
def search_catalogue(query: str, limit: int = 10) -> list[str]:
    """Use this when a reader asks for books by title. Returns matching titles."""
    return [title for title in BOOKS.values() if query.lower() in title.lower()][:limit]


@mcp.tool()
async def reserve(isbn: str, ctx: Context) -> str:
    """Reserve one copy of a book for the reader."""
    await ctx.info(f"reserving {isbn}")
    answer = await ctx.elicit("How many weeks?", schema=dict)
    return f"reserved {isbn} for {answer}"


@mcp.tool()
def debug_dump(**kwargs) -> str:
    return repr(kwargs)


@mcp.resource("book://{isbn}")
def book(isbn: str) -> str:
    """One book by ISBN."""
    if isbn not in BOOKS:
        raise McpError(ErrorData(code=-32002, message="Book not found"))
    return BOOKS[isbn]


def whoami() -> str:
    ctx = mcp.get_context()
    return str(ctx.request_id)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
