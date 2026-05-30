#!/usr/bin/env python3
"""agent-bus watcher.

Watches ~/.claude/bus/inbox/ for new message files. Per event, looks up the
current session's registered agent name (via $CLAUDE_CODE_SESSION_ID and the
registry) and only emits a line if the message is addressed to this session.

Output per relevant message (one line per notification):
    📨 from <FROM>: <body-truncated> (id=<filename-without-ext>)

Picks the best available file-watch backend at startup:
  inotifywait (Linux) → fswatch (macOS) → shell-poll fallback (universal).

Pre-filtering at this layer means Claude only sees notifications meant for it,
which dramatically cuts UI noise and per-event tool-call cost on the receiver.
"""
import json, os, sys, time, shutil, subprocess, signal, socket, hashlib
from pathlib import Path
from datetime import datetime

BUS_ROOT = Path(os.environ.get("BUS_ROOT", os.path.expanduser("~/.claude/bus")))
INBOX = BUS_ROOT / "inbox"
REGISTRY = BUS_ROOT / "registry"
LOG_DIR = BUS_ROOT / "log"
INBOX.mkdir(parents=True, exist_ok=True)
REGISTRY.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "watcher.log"


def log(msg):
    try:
        with open(LOG_FILE, "a") as fh:
            fh.write(f"{datetime.utcnow().isoformat()}Z [{os.getpid()}] {msg}\n")
    except Exception:
        pass


def auto_rebind_from_memo():
    """If this session's host_cwd has a cwd-memo and no live registration
    exists for that name, claim it. Makes /resume transparent: the new session
    (often in a fresh Docker container) reclaims the name the prior session
    held in this host directory. Idempotent — safe to call multiple times.

    Skipped if:
      - no host_cwd resolvable / no hostname / no memo
      - the name is currently held by a DIFFERENT host (conflict)
    """
    host = socket.gethostname()
    # $HOST_CWD set by Docker wrappers, else the actual cwd of this process.
    host_cwd = os.environ.get("HOST_CWD", "") or os.getcwd()
    if not host or not host_cwd:
        return
    memo_hash = hashlib.sha256(host_cwd.encode()).hexdigest()[:16]
    memo_path = BUS_ROOT / "cwd-memo" / f"{memo_hash}.json"
    if not memo_path.exists():
        return
    try:
        memo = json.loads(memo_path.read_text())
    except Exception:
        return
    name = memo.get("name", "")
    if not name:
        return
    entry_path = REGISTRY / f"{name}.json"
    if entry_path.exists():
        try:
            existing = json.loads(entry_path.read_text())
        except Exception:
            existing = {}
        if existing.get("container") == host:
            log(f"AUTO-REBIND: already registered as {name}")
            return
        else:
            log(f"AUTO-REBIND skipped: '{name}' held by other container {existing.get('container', '?')}")
            return
    data = {
        "name": name,
        "container": host,
        "session_id": os.environ.get("CLAUDE_CODE_SESSION_ID", ""),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cwd": os.environ.get("PWD", ""),
        "host_cwd": host_cwd,
        "auto_rebind": True,
    }
    entry_path.write_text(json.dumps(data, indent=2))
    log(f"AUTO-REBIND: registered as {name} from cwd-memo {host_cwd}")


def my_name():
    """Return the name this session is registered as, or None.

    Keyed on hostname (stable across /resume within the same host/container,
    unique per fresh Docker container), not session_id (which changes on
    /resume and leaves pre-resume watcher subprocesses with stale env)."""
    host = socket.gethostname()
    if not host:
        return None
    for f in REGISTRY.glob("*.json"):
        try:
            with open(f) as fh:
                d = json.load(fh)
            if d.get("container") == host:
                return d.get("name")
        except Exception:
            continue
    return None


def emit_if_relevant(filename: str):
    filename = filename.strip()
    if not filename:
        return
    if filename.startswith(".tmp-"):
        log(f"skip tmp: {filename}")
        return
    name = my_name()
    if not name:
        log(f"event {filename}: unregistered, dropping")
        return
    if "--" not in filename:
        log(f"event {filename}: malformed, dropping")
        return
    to = filename.split("--", 1)[0]
    if to != name:
        log(f"event {filename}: not for me ({to} != {name}), dropping")
        return
    path = INBOX / filename
    if not path.exists():
        log(f"event {filename}: file vanished before read")
        return
    try:
        with open(path) as fh:
            d = json.load(fh)
    except Exception as e:
        log(f"event {filename}: json parse failed: {e}")
        return
    body = d.get("body", "") or ""
    msg_id = d.get("id", filename[:-5] if filename.endswith(".json") else filename)
    # Show the sender's send-time in LOCAL time (HH:MM:SS). The payload stores
    # epoch `ts` (and UTC ts_iso); datetime.fromtimestamp() converts to local.
    hhmmss = ""
    try:
        hhmmss = datetime.fromtimestamp(d["ts"]).strftime("%H:%M:%S")
    except Exception:
        sent = d.get("ts_iso", "") or ""
        hhmmss = sent[11:19] if len(sent) >= 19 else sent  # fallback: UTC slice
    stamp = f"  [{hhmmss}]" if hhmmss else ""
    log(f"EMIT {filename}: from={d.get('from','?')} bytes={len(body)}")
    # 📥 ← = inbound (distinct tray + arrow from the 📤 → outbound echo).
    print(f"📥 ← from {d.get('from', '?')}{stamp} (id={msg_id}):", flush=True)
    print(body, flush=True)
    print(f"📥 end", flush=True)


def watch_inotify():
    # inotifywait block-buffers stdout when piped, which can sit on events
    # indefinitely under low traffic. stdbuf -oL forces line-buffering.
    cmd = ["inotifywait", "-m", "-q", "-e", "create,moved_to", "--format", "%f", str(INBOX)]
    if shutil.which("stdbuf"):
        cmd = ["stdbuf", "-oL"] + cmd
    log(f"watch_inotify start: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    try:
        for line in proc.stdout:
            emit_if_relevant(line)
    finally:
        log(f"watch_inotify exit: returncode={proc.poll()}")
        proc.terminate()


def watch_fswatch():
    proc = subprocess.Popen(
        ["fswatch", "-0", "--event", "Created", "--event", "Renamed", str(INBOX)],
        stdout=subprocess.PIPE, bufsize=0,
    )
    try:
        buf = bytearray()
        while True:
            ch = proc.stdout.read(1)
            if not ch:
                break
            if ch == b"\0":
                full = buf.decode(errors="replace")
                emit_if_relevant(os.path.basename(full))
                buf.clear()
            else:
                buf.extend(ch)
    finally:
        proc.terminate()


def watch_poll():
    seen = {p.name for p in INBOX.iterdir() if p.is_file()}
    while True:
        time.sleep(0.5)
        try:
            cur = {p.name for p in INBOX.iterdir() if p.is_file()}
        except FileNotFoundError:
            INBOX.mkdir(parents=True, exist_ok=True)
            cur = set()
        for f in sorted(cur - seen):
            emit_if_relevant(f)
        seen = cur


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    host = socket.gethostname()
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "(no-sid)")
    if shutil.which("inotifywait"):
        backend = "inotifywait"
    elif shutil.which("fswatch"):
        backend = "fswatch"
    else:
        backend = "poll"
    log(f"START backend={backend} host={host} session_id={sid} inbox={INBOX}")
    auto_rebind_from_memo()
    try:
        if backend == "inotifywait":
            watch_inotify()
        elif backend == "fswatch":
            watch_fswatch()
        else:
            watch_poll()
    except Exception as e:
        log(f"FATAL: {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    main()
