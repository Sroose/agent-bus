# Changelog

## 0.1.0 — 2026-05-19

Initial release.

- `/agent register|unregister|whoami|list|ask|send|inbox|read|archive` subcommands
- Container-hostname-based session identity (stable across `/resume`)
- `cwd-memo` so the watcher auto-rebinds the prior name on `/resume` (no user action needed)
- Pre-filtered watcher: notifications only arrive for messages addressed to the registered name
- Pre-formatted notifications (full body, no JSON parsing required by the receiver)
- Send-time warning when target name has no live listener
- Backlog replay: messages that arrived before registration are surfaced on `/agent register`
- Auto-unregister on clean session exit; preserves `cwd-memo` for next session
- SessionStart hook maintains `~/.claude/bus/bus.py` symlink for stable invocation path
- File watcher selects best available backend: `inotifywait` → `fswatch` → shell-poll
- Optional statusline integration via `statusline_fragment.py`
- Diagnostic log at `~/.claude/bus/log/watcher.log`
