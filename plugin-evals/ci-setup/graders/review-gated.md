---
type: regex
target: { source: file, path: .github/workflows/mcp-conformance.yml }
pattern: "lint_server\\.py[\\s\\S]*exit \\$code"
---

The review step's exit code reaches the job: `set +e`, capture, `exit $code`.
