---
max_turns: 16
allowed_tools: [Read, Glob, Grep, Skill, AskUserQuestion, "Bash(python3 *)"]
tags: [verify, probe]
---

A test MCP server is in ./fixtures/fake_mcp.py. Start it in the background with `python3 fixtures/fake_mcp.py --mode dual --port 8765 &`, then check whether http://127.0.0.1:8765/mcp is fast enough for Alexa+ and still works for older clients. You have my approval to start it and to probe it; it is a local test server.
