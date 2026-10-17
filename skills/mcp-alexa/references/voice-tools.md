# Shaping MCP tools for voice

A tool list written for a chat client with a screen often fails by voice in
predictable ways: it returns twenty rows, its description says "see the table
below", its name is an HTTP verb, and its only confirmation step is a widget.
The Alexa+ documents give concrete rules; this file turns them into edits.

## Descriptions: intent first

The design guide's pattern: *when* to call it, *what* it returns, *what it does
not do*.

```text
before: "Query records by date range with filters and pagination."
after:  "Use this when the customer asks what they logged on a day or in a
         date range, like 'what did I eat on Monday'. Returns at most five
         entries, newest first, and says how many more there are. Does not
         change or delete anything."
```

`ALX040` flags screen references (click, tap, scroll, see below, the table,
the chart, the widget, the card, displayed, button) and descriptions longer
than 400 characters.

## At most five options

"Present a maximum of 5 options with key differentiators and offer
pagination." For list-returning tools (`list_*`, `search_*`, `find_*`,
`query_*`, or a `limit` / `cursor` parameter) `ALX041` checks the declared
maximum of the page-size parameter:

```ts
// before
limit: z.number().int().min(1).max(100).optional()
// after: voice gets five; a screen client can still page with the cursor
limit: z.number().int().min(1).max(5).optional(),
cursor: z.string().optional()
```

When the same tool serves screen clients that want more, keep one tool and a
small default rather than two tools that do the same thing — the design guide
asks that "each tool should have a clear, distinct purpose".

## Names

`get_record`, `delete_record`, `post_entry` read as API calls (`ALX042`).
Prefer the customer's intent: `find_entry`, `forget_entry`, `log_meal`. Renaming
a tool on a deployed add-on changes its signature — record the lock again
after redeploying.

## Confirmations without a screen

MCP App tools (`registerAppTool`, `_meta.ui.resourceUri`) render a widget on
devices with a screen. On a headless device the same task must complete by
voice: "Read back all key details and require explicit 'yes' before any
commitment." `ALX043` lists every app tool so someone checks its voice path —
typically a `confirm: true` parameter the model sets only after a spoken yes.

## Errors the customer hears

"Surface no API codes, tool names, JSON, or internal IDs in any
customer-facing response" and "Provide actionable next step for every error".
Return an `isError` result whose text is a sentence the model can say, and
keep codes and correlation ids in `structuredContent` or logs.

## Slow tools

"Display interim messages for slow tool calls" and keep the round trip under
500 ms: return the first five quickly and let the customer ask for more.

---

Sources: https://developer.amazon.com/docs/alexaplus/add-ons/functional-requirements.html,
https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-design-guide.html,
https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html (read 2026-10-05).
