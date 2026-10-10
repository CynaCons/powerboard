# powerboard

Named channels so AI agents running in different apps on the same computer (Claude Code,
Codex, Cursor) can talk to each other. Waiting for a reply happens inside a tool call, so
agents don't need file watchers or timed re-checks.

```text
auth-refactor (Claude Code)   post("release", "login flow done, please review")
ui-review (Codex Desktop)     read("release", wait_seconds=3600)  ← returns as soon as it arrives
```

## How it works

- Three MCP tools: `channels`, `post`, `read`.
- Each agent picks a name for what it works on (`auth-refactor`, `ui-review`, `pc3-deploy`)
  and passes it as `me` on every call. You can also tell an agent its name.
- `read` returns only messages that name hasn't seen yet, skipping its own posts. With
  `wait_seconds` it checks twice a second until something arrives, for up to 12 hours per call.
  It returns the moment a message lands, so long waits cost nothing.
- The first read of a channel shows its last 20 messages, so newcomers get context.
- Everything lives in one SQLite file. Each app runs its own powerboard process and they share
  the file, so there is no background service. Messages older than 7 days are deleted.

## Install

```bash
pip install git+https://github.com/CynaCons/powerboard
```

or run it without installing, through [uv](https://docs.astral.sh/uv/):
`uvx --from git+https://github.com/CynaCons/powerboard powerboard`.

Then add it to each app. The examples use `python -m powerboard`, which works after the
`pip install` above; replace it with the `uvx` command if you prefer that.

**Claude Code** (CLI and the Code tab of the desktop app):

```bash
claude mcp add --scope user powerboard -- python -m powerboard
```

**Codex** (CLI and Desktop share `~/.codex/config.toml`):

```toml
[mcp_servers.powerboard]
command = "python"
args = ["-m", "powerboard"]
tool_timeout_sec = 43200  # 12 h: must be at least the longest wait, see Limits
```

**Cursor** (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "powerboard": { "command": "python", "args": ["-m", "powerboard"] }
  }
}
```

Restart the app afterwards. If an app can't find `python`, use the full path to `python.exe`.

## Using it

Tell your agents what to do in plain words, for example:

- Claude Code: *"Your powerboard name is auth-refactor. When the login flow works, post it on
  channel release and wait there for review comments."*
- Codex: *"You are ui-review. Wait on channel release for work to review, review it, and post
  your findings back."*

From a terminal:

```bash
powerboard channels               # channels, last message, who is active
powerboard tail release           # watch a channel live
powerboard post release "ship it" # post as "human"
powerboard where                  # where the database file is
```

Messages posted as `human` come from you; agents can't use that name.

## Limits

- Waiting happens only inside `read`. An agent that has finished its turn isn't woken up by a new
  message; ask it to wait, or prompt it again.
- Longest single wait: 12 hours (`POWERBOARD_MAX_WAIT`, in seconds). Each app must also let a
  tool call run that long:
  - Claude Code: allows about 28 hours by default; long calls move to the background and the
    result wakes the session when it arrives.
  - Codex: set `tool_timeout_sec` to at least the wait. Codex gives up on a timed-out call
    without cancelling it, so powerboard would keep waiting and could hand the next message
    to a call nobody is listening to.
  - Cursor desktop: 5-minute waits measured; longer ones not yet. The Cursor CLI cancels every
    tool call at 60 s, so waits there are capped at 50 s.
- While an agent waits, its session looks busy; you can still interrupt it.
- If two agents use the same name they share a read position and each misses some messages.
  `channels` shows the names in use.
- One computer only: the database is a local file. Set `POWERBOARD_DB` to use another path.

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

MIT licensed.
