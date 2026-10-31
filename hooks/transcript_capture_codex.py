#!/usr/bin/env python3
"""Codex adapter for transcript_capture.py: the same cursor, scrub, and sender,
reading Codex session files instead of Claude Code ones.

Wire it as a Codex `Stop` hook (silent exit 0 is a no-op for Codex), and run
`--catch-up` from a scheduler like the Claude Code script. It shares the config
file (~/.claude/transcript-capture.json, or $TRANSCRIPT_CAPTURE_CONFIG) and the
state folder with the Claude Code script; metadata says "harness": "codex".

Codex session files: $CODEX_HOME/sessions/YYYY/MM/DD/rollout-<time>-<id>.jsonl
($CODEX_HOME defaults to ~/.codex). Each line is {"timestamp", "type",
"payload"}. Conversation text is read from the `event_msg` lines whose payload
type is `user_message` (what the user typed, without the injected AGENTS.md and
environment context that the `response_item` user messages carry) and
`agent_message` (the assistant's prose). The session id is the `session_meta`
payload's `id`, so the hook and the catch-up key one cursor per file.

TODO(codex-format): this line format was checked against session files written
by Codex CLI 0.100 and 0.107 and against the rollout recorder source, not
against a published format spec. If a Codex release stops persisting
`user_message` / `agent_message` events, add a fallback to `response_item`
messages (role user minus injected context, role assistant `output_text`) in
codex_events() below. Whether the Stop event's `session_id` always equals the
`session_meta` id is also unverified; the adapter avoids depending on it.

Loads transcript_capture.py from its own folder, else from ~/.claude/hooks/, or
from $TRANSCRIPT_CAPTURE_CORE. Never raises into the harness; standard library
only; runs as `python -S -I transcript_capture_codex.py`.
"""
import glob
import importlib.util
import json
import os
import re
import sys

HARNESS = "codex"
_UUID = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)
_INTERESTING = (b'"event_msg"', b'"session_meta"', b'"turn_context"')


def load_core():
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.environ.get("TRANSCRIPT_CAPTURE_CORE"),
                 os.path.join(here, "transcript_capture.py"),
                 os.path.join(os.path.expanduser("~"), ".claude", "hooks",
                              "transcript_capture.py")):
        if path and os.path.isfile(path):
            spec = importlib.util.spec_from_file_location("transcript_capture_core", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


core = load_core()


def codex_home():
    return os.path.expanduser(os.environ.get("CODEX_HOME") or "~/.codex")


def codex_events(raw):
    """Events from one rollout line: ("user"|"assistant"|"cwd", value, ts)."""
    if not any(k in raw for k in _INTERESTING):
        return []
    try:
        obj = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(obj, dict) or not isinstance(obj.get("payload"), dict):
        return []
    kind, p, ts = obj.get("type"), obj["payload"], obj.get("timestamp") or ""
    if kind in ("session_meta", "turn_context"):
        cwd = p.get("cwd")
        return [("cwd", cwd, ts)] if isinstance(cwd, str) and cwd else []
    if kind != "event_msg":
        return []
    msg = p.get("message")
    if not isinstance(msg, str):
        return []
    if p.get("type") == "user_message":
        text = core.strip_injected(msg)
        return [("user", text, ts)] if text else []
    if p.get("type") == "agent_message":
        text = msg.strip()
        return [("assistant", text, ts)] if text else []
    return []


def codex_session_id(path):
    """The session_meta id from the file's first lines, else the uuid in its name."""
    try:
        with open(path, "rb") as f:
            for _ in range(5):
                raw = f.readline()
                if not raw:
                    break
                if b'"session_meta"' not in raw:
                    continue
                obj = json.loads(raw)
                p = obj.get("payload") or {}
                sid = p.get("id") or p.get("session_id")
                if sid:
                    return str(sid)
    except (OSError, ValueError):
        pass
    m = _UUID.search(os.path.basename(path))
    return m.group(1) if m else None


def codex_session_files():
    return glob.glob(os.path.join(codex_home(), "sessions", "*", "*", "*", "rollout-*.jsonl"))


def main(argv):
    if core is None:
        return 0
    return core.main(argv, harness=HARNESS, events_fn=codex_events,
                     files_fn=codex_session_files, session_id_fn=codex_session_id,
                     hook_session_id_fn=codex_session_id)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        sys.exit(0)
