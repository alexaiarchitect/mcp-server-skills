/**
 * Speakable text for the Alexa+ tool surface, in en-US and es-ES.
 *
 * Alexa+ voices whatever the model makes of a tool result, so the `text`
 * content of every Alexa tool is a short, complete sentence a person can hear
 * once and act on: no identifiers, no JSON, no markdown, at most five options.
 * The structured content carries the same facts for the model.
 */
export const locales = ["en-US", "es-ES"] as const;
export type Locale = (typeof locales)[number];

/** The locale spoken when nothing in the request or the environment names one. */
export const FALLBACK_LOCALE: Locale = "en-US";

/**
 * Match a BCP-47 tag or an Accept-Language value to a supported locale, or
 * `undefined` when none of its languages is supported. Accept-Language
 * entries are tried in descending `q` order (ties keep header order), `q=0`
 * entries are ignored, and any `en-*` / `es-*` tag maps to en-US / es-ES.
 */
export function matchLocale(value: string | undefined): Locale | undefined {
  if (!value) return undefined;
  const ranked = value
    .split(",")
    .map((part, index) => {
      const [tag = "", ...parameters] = part.split(";").map((item) => item.trim());
      const q = parameters.find((parameter) => /^q=/iu.test(parameter));
      const weight = q === undefined ? 1 : Number(q.slice(2));
      return { tag: tag.toLowerCase(), weight: Number.isFinite(weight) ? weight : 0, index };
    })
    .filter((entry) => entry.tag && entry.weight > 0)
    .sort((a, b) => b.weight - a.weight || a.index - b.index);
  for (const { tag } of ranked) {
    const language = tag.split(/[-_]/u)[0];
    if (language === "es") return "es-ES";
    if (language === "en") return "en-US";
  }
  return undefined;
}

/** Map a BCP-47 tag (or an Accept-Language value) to a supported locale, en-US if none. */
export function resolveLocale(value: string | undefined): Locale {
  return matchLocale(value) ?? FALLBACK_LOCALE;
}

/** Where a request's speech locale came from (logged with every Alexa tool call). */
export type LocaleSource = "argument" | "meta" | "accept-language" | "env-default" | "fallback";

/** Every per-request signal that can carry the user's language. */
export interface LocaleSignals {
  /** The tool's own `locale` argument, chosen by the model from what the user says. */
  argument?: string | undefined;
  /** `params._meta.locale` of the JSON-RPC request, if the client sends one. */
  meta?: string | undefined;
  /** The HTTP `Accept-Language` header of the MCP request. */
  acceptLanguage?: string | undefined;
  /** `ALEXA_DEFAULT_LOCALE` of the deployment. */
  envDefault?: string | undefined;
}

/**
 * Pick the speech locale for one request: the first supported value of the
 * tool argument, `_meta.locale`, Accept-Language, then `ALEXA_DEFAULT_LOCALE`,
 * then en-US. Unsupported values (for example `fr-FR`) fall through to the
 * next signal instead of forcing English. The Alexa+ MCP documentation does
 * not say how (or whether) the user's locale reaches the server; see
 * docs/ALEXA-FRICTION.md.
 */
export function selectLocale(signals: LocaleSignals): { locale: Locale; source: LocaleSource } {
  const ordered: [LocaleSource, string | undefined][] = [
    ["argument", signals.argument],
    ["meta", signals.meta],
    ["accept-language", signals.acceptLanguage],
    ["env-default", signals.envDefault]
  ];
  for (const [source, value] of ordered) {
    const locale = matchLocale(value);
    if (locale) return { locale, source };
  }
  return { locale: FALLBACK_LOCALE, source: "fallback" };
}

/** Join up to five items the way each language says a list out loud. */
export function spokenList(items: readonly string[], locale: Locale): string {
  const list = items.slice(0, 5);
  const and = locale === "es-ES" ? "y" : "and";
  if (list.length <= 1) return list[0] ?? "";
  if (list.length === 2) return `${list[0]} ${and} ${list[1]}`;
  return `${list.slice(0, -1).join(", ")}${locale === "es-ES" ? "" : ","} ${and} ${list.at(-1)}`;
}

function spokenDate(iso: string, locale: Locale): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(locale, {
    weekday: "long",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "UTC"
  }).format(date);
}

/** Render a record's values as "hours 7.5, quality good" (at most five fields). */
export function spokenValues(data: Record<string, unknown>, locale: Locale): string {
  const entries = Object.entries(data)
    .filter(([, value]) => ["string", "number", "boolean"].includes(typeof value))
    .slice(0, 5)
    .map(([key, value]) => {
      const label = key.replace(/[_-]+/gu, " ");
      const spoken =
        typeof value === "boolean"
          ? value
            ? locale === "es-ES"
              ? "sí"
              : "yes"
            : "no"
          : String(value);
      return `${label} ${spoken}`;
    });
  return entries.join(", ");
}

const en = {
  noCategories: "Your vault has no categories yet. Create one from ChatGPT or the web first.",
  categories: (names: string[], more: boolean) =>
    `You have ${names.length === 1 ? "one category" : `${names.length} categories`}${more ? " on this page" : ""}: ${spokenList(names, "en-US")}.${more ? " Say 'more' to hear the next ones." : ""}`,
  fields: (name: string, fields: string[], required: string[]) =>
    fields.length
      ? `${name} records ${spokenList(fields, "en-US")}.${required.length ? ` ${spokenList(required, "en-US")} ${required.length === 1 ? "is" : "are"} required.` : ""}`
      : `${name} has no fields.`,
  notFound: (name: string, options: string[]) =>
    options.length
      ? `I couldn't find a category called ${name}. Did you mean ${spokenList(options, "en-US")
          .replace(/, and /u, ", or ")
          .replace(/ and /u, " or ")}?`
      : `I couldn't find a category called ${name}.`,
  preview: (name: string, values: string, when: string) =>
    `I'll add to ${name}: ${values}, for ${when}. Should I save it?`,
  invalid: (name: string, message: string) => `That doesn't fit ${name}: ${message}`,
  saved: (name: string) => `Saved to ${name}.`,
  noRecords: (name: string, days: number) => `Nothing in ${name} in the last ${days} days.`,
  records: (name: string, items: string[], more: boolean) =>
    `In ${name}: ${items.join(". ")}.${more ? " Say 'more' for older ones." : ""}`,
  usage: (plan: string, categories: string, records: string) =>
    `You're on the ${plan} plan, using ${categories} categories and ${records} records.`,
  error: (code: string) =>
    ({
      AUTH_REQUIRED: "Please link your Bookshelf Vault account in the Alexa app first.",
      INSUFFICIENT_SCOPE:
        "Your linked account doesn't allow that. Relink it in the Alexa app and allow access.",
      RATE_LIMITED: "That's a lot of requests. Try again in a little while.",
      PLAN_LIMIT_EXCEEDED: "Your plan's limit is reached for that.",
      NOT_FOUND: "I couldn't find that. It may have expired; let's start again.",
      SCHEMA_CONFLICT: "That category changed in the meantime. Let's start again."
    })[code] ?? "Something went wrong with your vault. Please try again."
};

const es: typeof en = {
  noCategories: "Tu bóveda aún no tiene categorías. Crea una primero desde ChatGPT o la web.",
  categories: (names, more) =>
    `Tienes ${names.length === 1 ? "una categoría" : `${names.length} categorías`}${more ? " en esta página" : ""}: ${spokenList(names, "es-ES")}.${more ? " Di 'más' para oír las siguientes." : ""}`,
  fields: (name, fields, required) =>
    fields.length
      ? `${name} registra ${spokenList(fields, "es-ES")}.${required.length ? ` ${required.length === 1 ? "Es obligatorio" : "Son obligatorios"}: ${spokenList(required, "es-ES")}.` : ""}`
      : `${name} no tiene campos.`,
  notFound: (name, options) =>
    options.length
      ? `No encuentro una categoría llamada ${name}. ¿Quizá ${spokenList(options, "es-ES").replace(/ y /u, " o ")}?`
      : `No encuentro una categoría llamada ${name}.`,
  preview: (name, values, when) => `Añadiré a ${name}: ${values}, para el ${when}. ¿Lo guardo?`,
  invalid: (name, message) => `Eso no encaja en ${name}: ${message}`,
  saved: (name) => `Guardado en ${name}.`,
  noRecords: (name, days) => `No hay nada en ${name} en los últimos ${days} días.`,
  records: (name, items, more) =>
    `En ${name}: ${items.join(". ")}.${more ? " Di 'más' para oír los anteriores." : ""}`,
  usage: (plan, categories, records) =>
    `Tienes el plan ${plan} y usas ${categories} categorías y ${records} registros.`,
  error: (code) =>
    ({
      AUTH_REQUIRED: "Primero vincula tu cuenta de Bookshelf Vault en la app de Alexa.",
      INSUFFICIENT_SCOPE:
        "Tu cuenta vinculada no permite eso. Vuelve a vincularla en la app de Alexa.",
      RATE_LIMITED: "Son muchas peticiones. Inténtalo de nuevo dentro de un rato.",
      PLAN_LIMIT_EXCEEDED: "Has alcanzado el límite de tu plan para eso.",
      NOT_FOUND: "No lo encuentro. Puede que haya caducado; empecemos de nuevo.",
      SCHEMA_CONFLICT: "Esa categoría cambió mientras tanto. Empecemos de nuevo."
    })[code] ?? "Algo falló con tu bóveda. Inténtalo de nuevo."
};

export function speech(locale: Locale): typeof en {
  return locale === "es-ES" ? es : en;
}

export { spokenDate };
