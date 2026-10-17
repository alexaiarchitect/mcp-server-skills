---
type: regex
target: trace
pattern: "probe\\.py[^\\n]*(?:--legacy|--profile alexa)[^\\n]*|probe\\.py[^\\n]*--budget-ms"
---

The probe ran with the legacy handshake (or the alexa profile, which implies
it) or an explicit budget: the two things the prompt asked about.
