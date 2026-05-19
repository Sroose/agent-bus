#!/usr/bin/env python3
"""SessionEnd hook for agent-bus: auto-unregister this container's session.

Skip on `exit_reason=resume` — that means the user is /resume-ing within the
same container; the container is alive and may still want to receive messages
under its registered name. Only unregister on actual session terminations
(clear, prompt_input_exit, logout, etc.).

Identity is by container hostname, NOT session_id. session_id changes on
/resume but hostname is stable for the container's lifetime.
"""
import json, sys, os, glob, socket

try:
    inp = json.load(sys.stdin)
except Exception:
    sys.exit(0)

if inp.get("exit_reason") == "resume":
    sys.exit(0)

host = socket.gethostname()
if not host:
    sys.exit(0)

for f in glob.glob(os.path.expanduser("~/.claude/bus/registry/*.json")):
    try:
        with open(f) as fh:
            d = json.load(fh)
        if d.get("container") == host:
            os.unlink(f)
            break
    except Exception:
        continue

sys.exit(0)
