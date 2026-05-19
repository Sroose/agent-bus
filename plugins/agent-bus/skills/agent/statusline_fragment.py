#!/usr/bin/env python3
"""Statusline fragment for agent-bus. Prints the registered agent name for
this container, or empty if unregistered.

Identity is by container hostname (stable across /resume), not session_id.
Stdin is read and ignored (CC pipes JSON to statusline scripts but we don't
need it).
"""
import json, sys, os, glob, socket

# Drain stdin so the parent doesn't block.
try:
    if not sys.stdin.isatty():
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
            print(d["name"])
            break
    except Exception:
        continue
