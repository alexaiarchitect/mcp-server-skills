# `addon.json`, field by field

The shape below is the one the MCP toolkit quickstart documents (read
2026-10-05). `alexa-ai new mcp` scaffolds it; `validate_addon.py` checks it
before `alexa-ai deploy` does.

```json
{
  "manifestVersion": "1.0",
  "storeListing": {
    "distributionCountries": ["US"],
    "locales": {
      "en-US": {
        "default": "DEFAULT",
        "name": { "value": "Bookshelf", "spokenForm": {} },
        "shortDescription": "...",
        "fullDescription": "...",
        "examplePhrases": ["...", "...", "..."],
        "privacyAndCompliance": {
          "privacyPolicyUrl": "https://...",
          "termsOfUseUrl": "https://..."
        },
        "mediaAssets": {
          "icons": { "light": [{ "size": "72x72", "uri": "https://..." }], "dark": [] },
          "carouselImages": [{ "uri": "https://...", "altText": "...", "size": "600x900" }],
          "bannerImages": []
        }
      }
    }
  },
  "integrations": [
    { "type": "MCP", "config": { "endpoints": { "default": { "type": "HTTPS", "uri": "https://mcp.example.com/mcp" } } } }
  ]
}
```

## Rules and the id that checks each

| Field | Rule | Id |
|---|---|---|
| `manifestVersion` | `"1.0"` | ALX003 |
| `storeListing.distributionCountries` | non-empty list | ALX010 |
| ... each country | the toolkit is documented as available in the US (warning, not error) | ALX011 |
| `storeListing.locales` | non-empty; keys like `en-US` | ALX012 |
| `name.value` | required, at most 30 characters | ALX013 |
| `shortDescription` | required, at most 123 characters | ALX014 |
| `fullDescription` | required, at most 4000 characters | ALX015 |
| `examplePhrases` | 3-4 items, at least 3 distinct, each at most 200 characters; they must work when spoken | ALX016 |
| `privacyPolicyUrl`, `termsOfUseUrl` | required, valid HTTPS | ALX017 |
| `mediaAssets.icons.light` | all six sizes: 72x72, 64x64, 88x88, 126x126, 180x180, 241x241 | ALX018 |
| `mediaAssets.carouselImages` | at least one, 600x900, alt text at most 250 characters | ALX019 |
| any media `uri` | HTTPS; PNG, JPG, JPEG or WEBP | ALX019 |
| `integrations[type=MCP].config.endpoints.default.uri` | HTTPS | ALX020 |
| ... vs the server | same URI as the PRM `resource` / OAuth `resource` (`--endpoint`) | ALX021 |
| customer-facing text | no API names, tool names, JSON references or developer jargon | ALX022 |

The jargon check flags words such as JSON, API, endpoint, MCP, schema, token,
OAuth, and any `snake_case` word or tool name of the server. It is a prompt
for a human to reread the listing, not a grammar checker.

## Not enforced (not documented as required)

`dark` icons, `bannerImages`, the contents of `spokenForm`, and additional
locales. A second locale (for example `es-ES`) is accepted by the validator;
whether it is offered in a country outside the US is a question for the
toolkit's availability, which `ALX011` raises.

## After editing

1. `validate_addon.py addon.json --endpoint https://.../mcp`
2. `alexa-ai deploy` (the user confirms)
3. Test the example phrases in the web simulator — they must work as written.

---

Sources: https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html,
https://developer.amazon.com/docs/alexaplus/add-ons/functional-requirements.html,
https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-overview.html (read 2026-10-05).
