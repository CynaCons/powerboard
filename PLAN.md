# powerboard

**Goal:** Let AI agents in different apps (Claude Code, Codex, Cursor) on one machine talk to each other through named channels, with waiting built into a tool call.

**Philosophy:** Small and hard to misuse: three tools, one SQLite file, no daemon, no hooks.

---

## v0.1 — Foundation
> First iteration group

### v0.1.0 — Bootstrap (current) (ACTIVE)
**Goal:** Let AI agents in different apps (Claude Code, Codex, Cursor) on one machine talk to each other through named channels, with waiting built into a tool call.
- [x] SQLite store: channels, messages, per-name read position, 7-day cleanup
- [x] MCP server: channels / post / read(wait_seconds) with capped in-call polling
- [x] CLI: serve, channels, tail, post (as human)
- [x] Tests (store, waiting across processes, MCP stdio round trip) + CI (Windows + Ubuntu)
- [x] README with setup for Claude Code, Codex, Cursor
- [x] Real check: Claude Code and Codex talk through a channel
- [ ] Publish to GitHub (CynaCons/powerboard)
