/**
 * MCP Apps (`io.modelcontextprotocol/ui`) registration without the
 * `@modelcontextprotocol/ext-apps` package.
 *
 * ext-apps 2.x is compatible with `@modelcontextprotocol/server` 2.x, but it
 * declares `@modelcontextprotocol/client` and `@modelcontextprotocol/core` as
 * required peers, and this workspace installs with
 * `strict-peer-dependencies=true`. Its server helpers are thin: they set the
 * tool's `_meta.ui.resourceUri` together with the flat legacy key
 * `ui/resourceUri`, and default a resource's MIME type to the MCP App profile.
 * The two functions below do exactly that, so the ChatGPT widgets keep working
 * and swapping back to `@modelcontextprotocol/ext-apps/server` is a drop-in.
 */

/** Same value as ext-apps `RESOURCE_MIME_TYPE`. */
export const RESOURCE_MIME_TYPE = "text/html;profile=mcp-app";
/** Same value as ext-apps `RESOURCE_URI_META_KEY` (the pre-namespaced key some hosts still read). */
export const RESOURCE_URI_META_KEY = "ui/resourceUri";
/** Extension id advertised under `capabilities.extensions`. */
export const MCP_APPS_EXTENSION_ID = "io.modelcontextprotocol/ui";

interface UiMeta {
  resourceUri?: string;
  visibility?: string[];
  [key: string]: unknown;
}

/**
 * Normalise a tool's `_meta` the way ext-apps `registerAppTool` does: a tool
 * that names a UI resource carries both the namespaced and the flat key.
 */
export function appToolMeta<T extends Record<string, unknown>>(meta: T): T {
  const ui = meta.ui as UiMeta | undefined;
  const legacyUri = meta[RESOURCE_URI_META_KEY] as string | undefined;
  if (ui?.resourceUri && !legacyUri) return { ...meta, [RESOURCE_URI_META_KEY]: ui.resourceUri };
  if (legacyUri && !ui?.resourceUri) return { ...meta, ui: { ...ui, resourceUri: legacyUri } };
  return meta;
}
