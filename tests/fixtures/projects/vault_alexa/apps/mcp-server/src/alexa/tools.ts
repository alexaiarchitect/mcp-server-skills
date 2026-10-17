/**
 * The Alexa+ tool surface (`ALEXA_PROFILE=1`).
 *
 * Voice changes the shape of every tool, not just its wording (Alexa+
 * functional requirements and design guide):
 *
 * - every answer carries **at most five options**, with a page token for more;
 * - names say what the user wants (`find_categories`, `log_entry`), not which
 *   HTTP-ish operation runs (`get_*`, `list_*`) — ALX042;
 * - nothing depends on an MCP Apps widget: a headless device must be able to
 *   finish every task by voice — ALX043. The write path keeps the vault's
 *   explicit-confirmation invariant as two calls (`log_entry` previews and
 *   asks, `confirm_entry` commits), which maps onto a spoken yes/no;
 * - every tool is invocable with a valid `inputSchema` and answers with one
 *   short speakable sentence (`content[0].text`) in en-US or es-ES, plus the
 *   same facts as `structuredContent` for the model;
 * - no identifiers are ever spoken; ids travel only in structured fields.
 *
 * The ChatGPT surface in `../server.ts` is untouched; both share the domain
 * services, scopes, rate limits and quotas.
 */
import { createHash, randomUUID } from "node:crypto";
import { requireScopes, type AuthContext, type VaultScope } from "@bookshelf-vault/auth";
import {
  asVaultError,
  derivePersonalSpaceId,
  VaultError,
  type EntitlementService,
  type JsonObject,
  type VaultService
} from "@bookshelf-vault/domain";
import type { McpServer } from "@modelcontextprotocol/server";
import { z } from "zod";
import type { ToolCallEvent } from "../telemetry.js";
import {
  locales,
  selectLocale,
  speech,
  spokenDate,
  spokenValues,
  type Locale,
  type LocaleSignals
} from "./speech.js";

/** Voice answers present at most this many options (Alexa+ functional requirements). */
export const MAX_VOICE_OPTIONS = 5;

export interface AlexaToolContext {
  service: VaultService;
  entitlements: EntitlementService;
  auth?: AuthContext;
  /**
   * Request-level language signals (`_meta.locale`, Accept-Language,
   * `ALEXA_DEFAULT_LOCALE`), used when a tool gets no `locale` argument.
   * See `selectLocale` for the order.
   */
  requestLocale?: Omit<LocaleSignals, "argument">;
  onToolCall?: (event: ToolCallEvent) => void;
}

const localeInput = z
  .enum(locales)
  .optional()
  .describe(
    "The language the user is speaking: en-US or es-ES. Defaults to the language of the request."
  );

const voiceOutput = z
  .object({
    ok: z.boolean(),
    speech: z.string(),
    data: z.unknown().optional(),
    next_page_token: z.string().optional(),
    error: z.object({ code: z.string(), retryable: z.boolean() }).strict().optional(),
    correlation_id: z.string()
  })
  .strict();

type VoiceResult = {
  speech: string;
  data?: unknown;
  nextPageToken?: string;
};

const readOnly = {
  readOnlyHint: true,
  destructiveHint: false,
  idempotentHint: true,
  openWorldHint: false
};

function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function stableKey(prefix: string, value: unknown): string {
  return `${prefix}-${createHash("sha256").update(JSON.stringify(value)).digest("hex").slice(0, 40)}`;
}

/** Coerce spoken values ("7.5", "yes") to the types the category schema declares. */
export function coerceValues(schema: JsonObject, values: Record<string, unknown>): JsonObject {
  const properties = (schema.properties ?? {}) as Record<string, { type?: unknown }>;
  const lookup = new Map(Object.keys(properties).map((key) => [fold(key), key]));
  const result: JsonObject = {};
  for (const [spokenKey, raw] of Object.entries(values)) {
    const key = lookup.get(fold(spokenKey)) ?? spokenKey;
    const type = properties[key]?.type;
    let value: unknown = raw;
    if ((type === "number" || type === "integer") && typeof raw === "string") {
      const parsed = Number(raw.replace(",", "."));
      if (Number.isFinite(parsed)) value = type === "integer" ? Math.round(parsed) : parsed;
    } else if (type === "boolean" && typeof raw === "string") {
      const folded = fold(raw);
      if (["yes", "true", "si"].includes(folded)) value = true;
      if (["no", "false"].includes(folded)) value = false;
    }
    result[key] = value as JsonObject[string];
  }
  return result;
}

export function registerAlexaTools(server: McpServer, context: AlexaToolContext): void {
  const { service, entitlements } = context;

  const run =
    (
      tool: string,
      scope: VaultScope,
      locale: Locale | undefined,
      operation: (auth: AuthContext, locale: Locale) => Promise<VoiceResult>
    ) =>
    async () => {
      const correlationId = randomUUID();
      const startedAt = Date.now();
      const selected = selectLocale({ ...context.requestLocale, argument: locale });
      const spokenLocale = selected.locale;
      const localeFields = { locale: spokenLocale, localeSource: selected.source };
      try {
        const auth = requireScopes(context.auth, [scope]);
        const entitlement = await entitlements.resolve(auth.owner);
        await entitlements.enforceRate(
          auth.owner,
          "tool",
          entitlement.limits.toolCallsPerHour,
          3600
        );
        const outcome = await operation(auth, spokenLocale);
        context.onToolCall?.({
          tool,
          outcome: "success",
          correlationId,
          durationMs: Date.now() - startedAt,
          ...localeFields
        });
        const structuredContent = {
          ok: true,
          speech: outcome.speech,
          ...(outcome.data === undefined ? {} : { data: outcome.data }),
          ...(outcome.nextPageToken ? { next_page_token: outcome.nextPageToken } : {}),
          correlation_id: correlationId
        };
        return { content: [{ type: "text" as const, text: outcome.speech }], structuredContent };
      } catch (error) {
        const vaultError = asVaultError(error);
        context.onToolCall?.({
          tool,
          outcome: "error",
          correlationId,
          durationMs: Date.now() - startedAt,
          ...localeFields,
          errorCode: vaultError.code,
          ...(error instanceof Error && !(error instanceof VaultError)
            ? { errorName: `${error.name}: ${error.message.slice(0, 300)}` }
            : {})
        });
        const said =
          vaultError.code === "VALIDATION_FAILED" || vaultError.code === "LIMIT_EXCEEDED"
            ? vaultError.message
            : speech(spokenLocale).error(vaultError.code);
        return {
          isError: true,
          content: [{ type: "text" as const, text: said }],
          structuredContent: {
            ok: false,
            speech: said,
            error: { code: vaultError.code, retryable: vaultError.retryable },
            correlation_id: correlationId
          }
        };
      }
    };

  async function findCategory(owner: string, name: string) {
    const page = await service.listCategories(owner, { limit: 100 });
    const wanted = fold(name);
    const exact = page.categories.find((category) => fold(category.name) === wanted);
    const partial = page.categories.filter(
      (category) => fold(category.name).includes(wanted) || wanted.includes(fold(category.name))
    );
    return {
      match: exact ?? (partial.length === 1 ? partial[0] : undefined),
      options: partial.length ? partial : page.categories
    };
  }

  server.registerTool(
    "find_categories",
    {
      title: "Find my categories",
      description:
        "Say which categories the user keeps in their vault, five at a time. Use it when the user asks what they track, or before logging when the category is unclear. Pass page_token from the previous answer when the user says 'more'.",
      inputSchema: z
        .object({
          page_token: z
            .string()
            .max(4096)
            .optional()
            .describe("Opaque token from the previous answer, for the next five."),
          locale: localeInput
        })
        .strict(),
      outputSchema: voiceOutput,
      annotations: readOnly
    },
    async ({ page_token, locale }) =>
      run("find_categories", "categories.read", locale, async (auth, spoken) => {
        const page = await service.listCategories(auth.owner, {
          limit: MAX_VOICE_OPTIONS,
          ...(page_token ? { cursor: page_token } : {})
        });
        const names = page.categories.map((category) => category.name);
        const say = speech(spoken);
        return {
          speech: names.length ? say.categories(names, Boolean(page.cursor)) : say.noCategories,
          data: {
            categories: page.categories.map((c) => ({ category_id: c.categoryId, name: c.name }))
          },
          ...(page.cursor ? { nextPageToken: page.cursor } : {})
        };
      })()
  );

  server.registerTool(
    "describe_category",
    {
      title: "What a category records",
      description:
        "Say which fields a category records and which are required, so the user knows what to say when logging. Use the category's name as the user said it.",
      inputSchema: z
        .object({
          category: z.string().min(1).max(120).describe("Category name as spoken, e.g. 'sleep'."),
          locale: localeInput
        })
        .strict(),
      outputSchema: voiceOutput,
      annotations: readOnly
    },
    async ({ category, locale }) =>
      run("describe_category", "categories.read", locale, async (auth, spoken) => {
        const say = speech(spoken);
        const found = await findCategory(auth.owner, category);
        if (!found.match) {
          return {
            speech: say.notFound(
              category,
              found.options.slice(0, 3).map((c) => c.name)
            )
          };
        }
        const version = await service.getCategorySchema(auth.owner, found.match.categoryId);
        const properties = Object.keys((version.schema.properties ?? {}) as JsonObject);
        const required = Array.isArray(version.schema.required)
          ? (version.schema.required as string[])
          : [];
        return {
          speech: say.fields(
            version.name,
            properties.slice(0, MAX_VOICE_OPTIONS),
            required.slice(0, MAX_VOICE_OPTIONS)
          ),
          data: {
            category_id: version.categoryId,
            name: version.name,
            fields: properties,
            required
          }
        };
      })()
  );

  server.registerTool(
    "log_entry",
    {
      title: "Log an entry",
      description:
        "Prepare one entry for a category from what the user said, then read the preview back and ask the user to confirm. Nothing is saved until confirm_entry is called with the returned entry_id after the user says yes.",
      inputSchema: z
        .object({
          category: z.string().min(1).max(120).describe("Category name as spoken, e.g. 'sleep'."),
          values: z
            .record(z.string().max(64), z.union([z.string().max(500), z.number(), z.boolean()]))
            .describe('Field values the user said, keyed by field name, e.g. {"hours": 7.5}.'),
          when: z.iso
            .datetime()
            .optional()
            .describe("When it happened (ISO 8601, UTC). Defaults to now."),
          locale: localeInput
        })
        .strict(),
      outputSchema: voiceOutput,
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false
      }
    },
    async ({ category, values, when, locale }) =>
      run("log_entry", "records.write", locale, async (auth, spoken) => {
        const say = speech(spoken);
        const found = await findCategory(auth.owner, category);
        if (!found.match)
          return {
            speech: say.notFound(
              category,
              found.options.slice(0, 3).map((c) => c.name)
            )
          };
        const version = await service.getCategorySchema(auth.owner, found.match.categoryId);
        const data = coerceValues(version.schema, values);
        const occurredAt = when ?? new Date().toISOString();
        const batch = await service.prepareRecords(auth.owner, {
          categoryId: version.categoryId,
          records: [{ occurredAt, data, source: "alexa" }],
          idempotencyKey: stableKey("alexa-log", { c: version.categoryId, data, occurredAt })
        });
        if (!batch.records.length) {
          throw new VaultError(
            "VALIDATION_FAILED",
            say.invalid(version.name, batch.errors[0]?.message ?? "")
          );
        }
        return {
          speech: say.preview(
            version.name,
            spokenValues(data, spoken),
            spokenDate(occurredAt, spoken)
          ),
          data: {
            entry_id: batch.batchId,
            category: version.name,
            values: data,
            occurred_at: occurredAt
          }
        };
      })()
  );

  server.registerTool(
    "confirm_entry",
    {
      title: "Save a confirmed entry",
      description:
        "Save the entry that log_entry prepared, only after the user clearly said yes to the preview. Prepared entries expire after 15 minutes.",
      inputSchema: z
        .object({
          entry_id: z.uuid().describe("entry_id returned by log_entry."),
          category: z
            .string()
            .max(120)
            .optional()
            .describe("Category name, only to say where it was saved."),
          locale: localeInput
        })
        .strict(),
      outputSchema: voiceOutput,
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false
      }
    },
    async ({ entry_id, category, locale }) =>
      run("confirm_entry", "records.write", locale, async (auth, spoken) => {
        const { limits } = await entitlements.resolve(auth.owner);
        await entitlements.enforceQuota(derivePersonalSpaceId(auth.owner), limits, "records", 1);
        const committed = await service.commitRecords(auth.owner, {
          batchId: entry_id,
          confirm: true,
          idempotencyKey: `alexa-commit-${entry_id}`
        });
        return {
          speech: speech(spoken).saved(
            category ?? (spoken === "es-ES" ? "tu bóveda" : "your vault")
          ),
          data: { saved: committed.committed }
        };
      })()
  );

  server.registerTool(
    "recent_entries",
    {
      title: "Hear recent entries",
      description:
        "Read back up to five entries of one category from the last few days, oldest first. Pass page_token from the previous answer when the user says 'more'.",
      inputSchema: z
        .object({
          category: z.string().min(1).max(120).describe("Category name as spoken."),
          days: z
            .number()
            .int()
            .min(1)
            .max(90)
            .optional()
            .describe("How many days back to look. Defaults to 7."),
          page_token: z.string().max(4096).optional(),
          locale: localeInput
        })
        .strict(),
      outputSchema: voiceOutput,
      annotations: readOnly
    },
    async ({ category, days, page_token, locale }) =>
      run("recent_entries", "records.read", locale, async (auth, spoken) => {
        const say = speech(spoken);
        const found = await findCategory(auth.owner, category);
        if (!found.match)
          return {
            speech: say.notFound(
              category,
              found.options.slice(0, 3).map((c) => c.name)
            )
          };
        const window = days ?? 7;
        const from = new Date(Date.now() - window * 86_400_000).toISOString();
        const page = await service.queryRecords(auth.owner, {
          categoryId: found.match.categoryId,
          from,
          limit: MAX_VOICE_OPTIONS,
          ...(page_token ? { cursor: page_token } : {})
        });
        const items = page.records.map(
          (record) =>
            `${spokenDate(record.occurredAt, spoken)}, ${spokenValues(record.data, spoken)}`
        );
        return {
          speech: items.length
            ? say.records(found.match.name, items, Boolean(page.cursor))
            : say.noRecords(found.match.name, window),
          data: {
            entries: page.records.map((record) => ({
              occurred_at: record.occurredAt,
              values: record.data,
              tags: record.tags
            }))
          },
          ...(page.cursor ? { nextPageToken: page.cursor } : {})
        };
      })()
  );

  server.registerTool(
    "vault_usage",
    {
      title: "How much of my plan I use",
      description:
        "Say the user's plan and how many categories and records they use out of its limits.",
      inputSchema: z.object({ locale: localeInput }).strict(),
      outputSchema: voiceOutput,
      annotations: readOnly
    },
    async ({ locale }) =>
      run("vault_usage", "categories.read", locale, async (auth, spoken) => {
        const report = await entitlements.usageReport(
          auth.owner,
          derivePersonalSpaceId(auth.owner)
        );
        const of = spoken === "es-ES" ? "de" : "of";
        return {
          speech: speech(spoken).usage(
            report.plan,
            `${report.usage.categories} ${of} ${report.limits.maxCategories}`,
            `${report.usage.records} ${of} ${report.limits.maxRecords}`
          ),
          data: {
            plan: report.plan,
            usage: { categories: report.usage.categories, records: report.usage.records },
            limits: { categories: report.limits.maxCategories, records: report.limits.maxRecords }
          }
        };
      })()
  );
}
