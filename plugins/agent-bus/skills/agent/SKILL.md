---
name: agent
description: Register, unregister, send, receive, list, or check the inbox for messages between Claude Code sessions on this machine. Triggers on user prompts like "register me as X", "ask Y about...", "/agent ...", or on incoming `📨 from ...` inbox notifications.
---

# agent-bus

A thin Bash shim over the bundled `bus.py`. Do not extend-think, do not delegate to a sub-agent — you have Bash and these calls are one-liners.

## Resolving the helper script

The helper lives inside the installed plugin under a version directory. Resolve the newest installed copy at call time — don't cache the path:

```bash
BUS=$(find ~/.claude/plugins/cache -path '*agent-bus*/skills/agent/bus.py' 2>/dev/null | sort -V | tail -1)
```

`~/.claude/plugins/cache` is scoped deliberately — a blanket `~/.claude` search also matches the marketplace repo clone under `plugins/marketplaces/…`, which has no version dir and would sort last. `sort -V | tail -1` picks the highest installed version.

Set `BUS` at the start of each Bash call below (each tool call is a fresh shell, so re-resolve every time). In this doc, `$BUS` means exactly that expression.

> If `$BUS` comes back empty (no marketplace install — e.g. you're testing via `--plugin-dir`), invoke the script by its explicit plugin path instead.

## User-issued commands → one Bash call

Each row: set `BUS` (above), then run. Echo the helper's stdout to the user.

| User says | Command (after `BUS=…`) |
|---|---|
| `register [me as] <NAME>` or `/agent register <NAME>` | `python3 "$BUS" register <NAME>` **then** start the inbox watcher (see below) |
| `unregister` or `/agent unregister` | `python3 "$BUS" unregister` |
| `whoami`, `who am I` or `/agent whoami` | `python3 "$BUS" whoami` |
| `list [agents]` or `/agent list` | `python3 "$BUS" list` |
| `ask <NAME> "<msg>"`, `send <NAME>...`, or `/agent ask <NAME> "<msg>"` | `python3 "$BUS" send <NAME> "<msg>"` |
| `inbox [NAME]` or `/agent inbox` | `python3 "$BUS" inbox [NAME]` |
| `/agent read <id>.json` | `python3 "$BUS" read <id>.json` |
| `/agent archive <id>.json` | `python3 "$BUS" archive <id>.json` |

So a register is, in full, a single self-contained Bash call:

```bash
BUS=$(find ~/.claude/plugins/cache -path '*agent-bus*/skills/agent/bus.py' 2>/dev/null | sort -V | tail -1)
python3 "$BUS" register OBSIDIAN
```

The helper does all the work — atomic writes, conflict detection, send-warning, backlog replay. You're just calling it.

## After a successful `register` — start the inbox watcher

The `register` row says "**then** start the inbox watcher." Required for this session to receive any incoming messages. `register`'s stdout prints a `📡 NEXT STEP` block with an exact `command:`/`description:`/`persistent:` triple — **call the `Monitor` tool with those exact values** (the `command` is an absolute path to this version's `watch.py`, so use it verbatim — don't re-resolve it).

The watcher runs `inotifywait` (or `fswatch` or shell-poll) on the inbox, pre-filters by your registered name, and emits a `📨 from …` notification per addressed message. Without this `Monitor` call, no notifications arrive and the user silently misses messages.

If `whoami` already returns a name when the user invokes `register` (e.g. SessionStart auto-rebound), still start the Monitor — the SessionStart hook writes the registry but cannot itself call Claude tools, so the watcher is your responsibility.

## Three rules that override everything else

1. **On any name-conflict error from `register` (exit 4)** — surface the helper's stderr verbatim and STOP. Never delete `~/.claude/bus/registry/<NAME>.json` yourself unless the user has explicitly confirmed the holder is dead and asked you to reclaim.
2. **Never trust conversation memory for "what's my registered name"** — always re-run `whoami` before sending or replying as a named agent.
3. **Never delegate this skill to a sub-agent (Task tool).** The operations are direct Bash calls. There's nothing to research, plan, or parallelize.

## Incoming message notifications

When a notification arrives with a `📨 from <FROM> (id=<msg-id>):` line in its payload, follow the response protocol in [PROTOCOL.md](./PROTOCOL.md) (next to this file in the plugin). Skip reading PROTOCOL.md when you're handling a user-issued command from the table above — those are one-shot Bash calls, no protocol needed.
