"""Stdlib-only helpers shared by the `mcp-server` plugin's skill scripts.

Nothing in this package imports an MCP SDK, Node, or any third-party Python
package. Server code is *read* — Python with `ast`, TypeScript and JavaScript
with a small comment- and string-aware scanner — and never executed, so every
check runs on a bare Python 3.10+ interpreter even when the project under
review does not build. Live checks (`probe.py`, `check_prm.py`,
`check_spec.py`) use `urllib` only.

Every constant below that describes the protocol, an SDK or the Alexa+ add-on
requirements was read from the page named beside it on the date in
`CHECKED_ON`, and is recorded with its URL in the maintainer's verified-facts
ledger. They are
re-pinned by the upgrade loop (`/mcp-server:mcp-upgrade`), not by hand.
"""

__version__ = "0.2.0"

#: The date every pinned fact below was last read from its source.
CHECKED_ON = "2026-10-05"

# -- protocol revisions -----------------------------------------------------

#: The revision the review targets by default: current per
#: https://modelcontextprotocol.io/specification/versioning (read 2026-10-05).
SPEC_TARGET = "2026-07-28"
#: The newest handshake-era ("legacy") revision. Alexa+ add-ons target it.
SPEC_LEGACY = "2025-11-25"
#: Every published revision, oldest first.
KNOWN_REVISIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28")
#: Revisions that carry version and capabilities per request (no `initialize`).
MODERN_REVISIONS = ("2026-07-28",)
LEGACY_REVISIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")

SPEC_BASE = "https://modelcontextprotocol.io/specification"
SPEC_VERSIONING_URL = f"{SPEC_BASE}/versioning"


def changelog_url(revision: str) -> str:
    return f"{SPEC_BASE}/{revision}/changelog"


# -- wire vocabulary of 2026-07-28 -----------------------------------------

META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
META_LOG_LEVEL = "io.modelcontextprotocol/logLevel"

HEADER_PROTOCOL_VERSION = "MCP-Protocol-Version"
HEADER_METHOD = "Mcp-Method"
HEADER_NAME = "Mcp-Name"
HEADER_SESSION = "Mcp-Session-Id"

#: Requests whose `Mcp-Name` header mirrors `params.name` / `params.uri`.
MCP_NAME_METHODS = ("tools/call", "resources/read", "prompts/get")

#: Results that MUST carry `ttlMs` and `cacheScope` (basic/utilities/caching).
CACHEABLE_METHODS = (
    "server/discover", "tools/list", "prompts/list", "resources/list",
    "resources/templates/list", "resources/read",
)
CACHE_SCOPES = ("public", "private")
#: `resultType` values defined by the core protocol; the tasks extension adds "task".
RESULT_TYPES = ("complete", "input_required")
EXTENSION_RESULT_TYPES = {"io.modelcontextprotocol/tasks": "task"}

#: Error codes defined by 2026-07-28 (basic/index#error-codes).
ERROR_CODES = {
    "HeaderMismatch": -32020,
    "MissingRequiredClientCapability": -32021,
    "UnsupportedProtocolVersion": -32022,
}
#: Codes a 2026-07-28 implementation MUST NOT emit.
RETIRED_CODES = {
    -32002: "resource not found (2025-11-25 and earlier); 2026-07-28 uses -32602",
    -32042: "URL elicitation required (2025-11-25 only)",
}
#: Draft numbering renumbered before 2026-07-28 went final (changelog minor 12).
DRAFT_CODES = {
    -32001: ("HeaderMismatch", -32020),
    -32003: ("MissingRequiredClientCapability", -32021),
    -32004: ("UnsupportedProtocolVersion", -32022),
}
#: Sub-range reserved for codes the specification defines.
SPEC_RESERVED_RANGE = (-32099, -32020)

#: Methods and notifications removed by 2026-07-28 (changelog major 4, 5, 6, minor 11).
REMOVED_METHODS = (
    "ping", "logging/setLevel", "notifications/roots/list_changed",
    "resources/subscribe", "resources/unsubscribe",
    "notifications/elicitation/complete", "tasks/result", "tasks/list",
)
#: Server-initiated requests that MRTR replaces (changelog major 7).
SERVER_INITIATED_METHODS = ("roots/list", "sampling/createMessage", "elicitation/create")

#: Features in the Deprecated state (specification/2026-07-28/deprecated).
DEPRECATED_FEATURES = ("roots", "sampling", "logging", "dynamic-client-registration",
                       "http+sse-transport", "includeContext")

EXT_APPS_ID = "io.modelcontextprotocol/ui"
EXT_APPS_MIME = "text/html;profile=mcp-app"
EXT_TASKS_ID = "io.modelcontextprotocol/tasks"

#: SEP-986 tool name guidance (2025-11-25).
TOOL_NAME_PATTERN = r"^[A-Za-z0-9_.\-]{1,128}$"

# -- SDKs -------------------------------------------------------------------

TS_V1_PACKAGE = "@modelcontextprotocol/sdk"
TS_V2_SERVER = "@modelcontextprotocol/server"
TS_V2_PACKAGES = (
    "@modelcontextprotocol/server", "@modelcontextprotocol/client", "@modelcontextprotocol/core",
    "@modelcontextprotocol/node", "@modelcontextprotocol/express", "@modelcontextprotocol/hono",
    "@modelcontextprotocol/fastify", "@modelcontextprotocol/server-legacy",
)
TS_EXT_APPS = "@modelcontextprotocol/ext-apps"
PY_PACKAGE = "mcp"

#: Newest published versions on CHECKED_ON (npm registry and PyPI).
LATEST_VERSIONS = {
    "@modelcontextprotocol/sdk": "1.32.0",
    "@modelcontextprotocol/server": "2.3.1",
    "@modelcontextprotocol/node": "2.1.1",
    "@modelcontextprotocol/ext-apps": "2.0.3",
    "mcp": "2.3.0",
    "mcp@1": "1.30.0",
}
#: Newest v2 companions the ext-apps 2.x peers name (npm registry; the SDK
#: monorepo tags 2.3.1 for both on CHECKED_ON).
LATEST_VERSIONS.update({"@modelcontextprotocol/client": "2.3.1", "@modelcontextprotocol/core": "2.3.1"})
#: peerDependencies of the release a migration moves to, keyed by "<package>@<major>".
#: `required` peers must be installed next to the package (pnpm with
#: `strict-peer-dependencies=true` refuses to install without them); `optional`
#: ones are marked optional in peerDependenciesMeta. Read from the published
#: package.json of @modelcontextprotocol/ext-apps 2.0.3 and @modelcontextprotocol/node 2.1.1.
PEER_DEPENDENCIES = {
    "@modelcontextprotocol/ext-apps@2": {
        "required": {"@modelcontextprotocol/client": "^2.0.0", "@modelcontextprotocol/core": "^2.0.0",
                     "zod": "^4.2.0"},
        "optional": {"@modelcontextprotocol/server": "^2.0.0", "react": "^17.0.0 || ^18.0.0 || ^19.0.0",
                     "react-dom": "^17.0.0 || ^18.0.0 || ^19.0.0"},
    },
    "@modelcontextprotocol/node@2": {
        "required": {"@modelcontextprotocol/server": "^2.3.0"},
        "optional": {},
    },
}

#: The major that implements 2026-07-28, per SDK and language.
TARGET_MAJOR = {"typescript": 2, "python": 2}
#: Minimums the v2 TypeScript line declares (upgrade-to-v2 guide, npm metadata).
TS_V2_MIN_NODE = 20
TS_V2_MIN_ZOD = "4.2.0"

# -- Alexa+ add-ons ---------------------------------------------------------

ALEXA_LATENCY_BUDGET_MS = 500          # mcp-toolkit-quickstart: "less than 500 ms"
ALEXA_SEARCH_BUDGET_MS = 3000          # functional-requirements 7: "within 3 seconds"
ALEXA_MAX_OPTIONS = 5                  # functional-requirements 9: "a maximum of 5 options"
ALEXA_SPEC_REVISION = "2025-11-25"     # mcp-toolkit-overview: "supports the 2025-11-25 version"
ALEXA_NAME_MAX = 30
ALEXA_SHORT_DESCRIPTION_MAX = 123
ALEXA_FULL_DESCRIPTION_MAX = 4000
ALEXA_EXAMPLE_PHRASES = (3, 4)
ALEXA_EXAMPLE_PHRASE_MAX = 200
ALEXA_ICON_SIZES = ("72x72", "64x64", "88x88", "126x126", "180x180", "241x241")
ALEXA_CAROUSEL_SIZE = "600x900"
ALEXA_ALT_TEXT_MAX = 250
ALEXA_MEDIA_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
ALEXA_COUNTRIES_AVAILABLE = ("US",)    # mcp-toolkit-overview: "available in the United States"
ALEXA_SCOPES = ("mcp:service", "mcp:tools", "mcp:resources")

PLUGIN_NAME = "mcp-server"
REPOSITORY = "https://github.com/alexaiarchitect/mcp-server-skills"
