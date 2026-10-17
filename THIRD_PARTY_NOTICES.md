# Third-party notices

This plugin distills material from the specifications, SDK documentation and
product documentation below. No source files from any of them are
redistributed; the rules, references, fixtures and scripts are original work
written for this plugin. A copy of the Apache License 2.0, under which this
plugin is released, is in `LICENSE`.

Every claim in this plugin's references was read on the documentation pages
cited in each reference's `Sources:` footer, on the dates given there
(2026-10-05 unless stated). The maintainer's verified-facts ledger (working
notes, not shipped with the plugin) lists each fact with its URL.

## Model Context Protocol specification (`modelcontextprotocol/modelcontextprotocol`)

    The Model Context Protocol authors and contributors
    https://modelcontextprotocol.io/specification
    https://github.com/modelcontextprotocol/modelcontextprotocol

Revisions 2026-07-28 (current) and 2025-11-25 were read on
modelcontextprotocol.io: changelogs, versioning, basic protocol, Streamable
HTTP transport, `server/discover`, caching, authorization, the deprecated
features registry, and the MCP Apps and Tasks extension overviews. Short
quotations (single sentences, wire examples reduced to their fields) are used
to state requirements. The licence of the specification text is the one in its
repository; it was not re-read for this release.

## MCP TypeScript SDK (`modelcontextprotocol/typescript-sdk`)

    The MCP TypeScript SDK authors and contributors; licence per the repository's LICENSE
    https://github.com/modelcontextprotocol/typescript-sdk

Documentation at https://ts.sdk.modelcontextprotocol.io/v2/ (v2 overview, the
upgrade-to-v2 and support-2026-07-28 migration guides, serving pages, the
`createMcpHandler` API reference) and npm registry metadata for
`@modelcontextprotocol/sdk` 1.32.0, `@modelcontextprotocol/server` 2.3.1,
`@modelcontextprotocol/node` 2.1.1. Code snippets in
`skills/mcp-migrate/references/ts-v1-to-v2.md` are short, adapted
illustrations of the documented API.

## MCP Python SDK (`modelcontextprotocol/python-sdk`)

    The MCP Python SDK authors and contributors; licence per the repository's LICENSE
    https://github.com/modelcontextprotocol/python-sdk

Documentation at https://py.sdk.modelcontextprotocol.io/ (migration guide,
running servers, serving legacy clients) and PyPI metadata for `mcp` 2.3.0 and
1.30.0.

## MCP Apps extension (`modelcontextprotocol/ext-apps`)

    https://github.com/modelcontextprotocol/ext-apps

Overview at https://modelcontextprotocol.io/extensions/apps/overview and npm
metadata for `@modelcontextprotocol/ext-apps` 2.0.3. Nothing redistributed.

## Amazon Alexa+ add-on documentation

    Amazon.com, Inc. or its affiliates
    https://developer.amazon.com/docs/alexaplus/add-ons/

The MCP toolkit quickstart, overview, design guide, authentication page,
functional requirements, certification pages and development stages were read
to derive the `ALX0xx` checks and the `addon.json` validator. Requirements are
quoted in single sentences with their page; the documentation's own terms of
use apply to it.

## Amazon Cognito and Amazon Bedrock AgentCore documentation

    Amazon.com, Inc. or its affiliates
    https://docs.aws.amazon.com/cognito/
    https://docs.aws.amazon.com/bedrock-agentcore/

Access token claims, resource binding (RFC 8707), PKCE, and AgentCore Gateway
inbound authorization, distilled in `skills/mcp-auth/references/`.

## IETF RFCs

RFC 6750, RFC 8414, RFC 8707, RFC 9207, RFC 9728, the OAuth 2.1 draft and the
OAuth Client ID Metadata Document draft are cited by number; no text is
reproduced beyond parameter names.

## Not included

The test fixtures (a fictional library "bookshelf" domain; `ts_v1_lambda` is
modelled on the structure — not the code — of a real Lambda-hosted server, and
`vault_alexa` is an anonymized copy of that server with its names, domains and
product strings replaced), the eval cases, the scripts and the library are
published with this plugin under its licence.
