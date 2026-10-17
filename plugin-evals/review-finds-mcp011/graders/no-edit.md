---
type: regex
target: trace
pattern: "\"(?:Edit|Write)\"[^\\n]*(?:handler|server)\\.ts"
match: not_contains
---

`Write` and `Edit` are granted on purpose, so not editing is a choice the model
made. Fails if any `Edit` or `Write` names the server sources. A write through
`Bash` would not show here, which is why `Bash` is limited to `python3`.
