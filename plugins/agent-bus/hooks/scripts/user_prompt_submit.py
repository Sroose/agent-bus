#!/usr/bin/env python3
"""UserPromptSubmit hook for agent-bus: sync the session's display name
(sessionTitle) to whatever this container is registered as in the bus registry.

Keyed on hostname, not session_id (see watch.py for rationale)."""
import json, sys, os, glob, socket

# Drain stdin (we don't use it but Claude Code may write to it)
try:
    sys.stdin.read()
except Exception:
    pass

host = socket.gethostname()
if not host:
    sys.exit(0)

for f in glob.glob(os.path.expanduser("~/.claude/bus/registry/*.json")):
    try:
        with open(f) as fh:
            d = json.load(fh)
        if d.get("container") == host:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "sessionTitle": d["name"],
                }
            }))
            break
    except Exception:
        continue

sys.exit(0)
