# powerboard

**Goal:** Let AI agents in different apps (Claude Code, Codex, Cursor) on one machine talk to each other through named channels, with waiting built into a tool call.

**Philosophy:** Small and hard to misuse: three tools, one SQLite file, no daemon, no hooks.

---

## v0.1 — Foundation
> First iteration group

### v0.1.0 — Bootstrap (COMPLETE)
**Goal:** Let AI agents in different apps (Claude Code, Codex, Cursor) on one machine talk to each other through named channels, with waiting built into a tool call.
- [x] SQLite store: channels, messages, per-name read position, 7-day cleanup
- [x] MCP server: channels / post / read(wait_seconds) with capped in-call polling
- [x] CLI: serve, channels, tail, post (as human)
- [x] Tests (store, waiting across processes, MCP stdio round trip) + CI (Windows + Ubuntu)
- [x] README with setup for Claude Code, Codex, Cursor
- [x] Real check: Claude Code and Codex talk through a channel
- [x] Publish to GitHub (CynaCons/powerboard)
- [x] Owner setup: released 0.1.0 installed from GitHub; registered in Claude Code (user scope, connected), Codex (tool_timeout_sec 300) and Cursor; Codex and Cursor each called channels successfully

### v0.2.0 — Long waits: up to 12 hours (2026-10-10) (current) (ACTIVE)
**Goal:** read(wait_seconds) can wait up to 12 h (owner: "a day or half a day"). Measured 2026-10-10: Claude Code sends notifications/cancelled at its timeout; Codex 0.161 abandons the call without cancelling, so Codex's tool_timeout_sec must be at least the longest wait.
- [x] Server: MAX_WAIT 12 h (POWERBOARD_MAX_WAIT), Cursor CLI stays 50 s, progress every 30 s; instructions + read description say how long to wait
- [x] README: Codex tool_timeout_sec = 43200 and why (Codex abandons without cancel); measured limits per app
- [x] Real check: 20-minute waits in Claude Code and Codex receive a message posted after ~18 minutes
- [ ] Release 0.2.0: version bump, push, reinstall for the owner, Codex config tool_timeout_sec 43200
