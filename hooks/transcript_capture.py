#!/usr/bin/env python3
"""Save the conversation text of an agent session to a memory bank, as it happens.

A Claude Code `Stop` hook. Each time the agent stops, it reads the session file
from where it last left off, keeps only conversation text (the user's typed
messages and the assistant's prose; never tool calls, tool output, thinking, or
subagent lines), and every `interval_turns` complete turns sends one `retain` to
the memory service through an MCP door on a gateway. All of a session's text
lands in one document, `session:<session_id>`, by appending.

Modes:
  (no argument)    Stop hook: read the event JSON on stdin.
  --catch-up       For a scheduler: send what is unsent for every session file
                   changed since the last catch-up and idle for
                   `catch_up_idle_min` minutes, ignoring the interval. Replays
                   owed retains first.
  --replay-owed    Resend the retains that could not be sent earlier.
  --dry-run        With --catch-up: print what would be sent (counts only, never
                   text), change nothing, contact nothing.
  --backfill       With --catch-up: also send sessions the hook never saw that
                   predate the first run (by default those are left alone).

Files (under ~/.claude, or $CLAUDE_CONFIG_DIR when set):
  transcript-capture.json                     config; missing or enabled=false -> do nothing
  transcript-capture/cursors/<session>.json   per-session cursor
  transcript-capture/owed-<date>.jsonl        retains that failed, verbatim
  transcript-capture/installed-at             time of the first run (backfill gate)
  transcript-capture/capture.log              one line per error; never text or keys

Never raises into the harness: every failure is logged and the script exits 0
with no output. Standard library only; Python 3.9 or newer; runs as
`python -S -I transcript_capture.py`.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time

VERSION = "1.0.0"
HARNESS = "claude-code"
PROTOCOL_VERSION = "2025-06-18"
CONTEXT = "verbatim transcript of an agent session, conversation text only"
REDACTED = "[redacted]"
REDACTED_LINE = "[redacted line]"
MAX_BATCHES_PER_STOP = 3
LOCK_STALE_S = 120
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_SECRET_FILE_BYTES = 256 * 1024
MIN_SECRET_LEN = 16
LOG_MAX_BYTES = 512 * 1024
KEEP_OPS = 20

DEFAULTS = {
    "enabled": False,
    "gateway_url": "",
    "mount": "",
    "mount_header": "x-mcp-servers",
    "key_file": "",
    "tool_name": "",
    "interval_turns": 10,
    "projects_root": "",
    "tags": [],
    "device": "",
    "secret_files": [],
    "scrub_patterns": None,
    "scrub_whole_line": False,
    "extra_metadata": {},
    "timeout_s": 15,
    "catch_up_idle_min": 30,
}

# Harness-injected blocks dropped from user text, and wrappers whose tags are
# removed but whose inner text is kept (a slash command stays as "/name args").
DROP_TAGS = (
    "system-reminder", "task-notification", "local-command-caveat",
    "local-command-stdout", "local-command-stderr", "command-message",
    "bash-stdout", "bash-stderr", "user-prompt-submit-hook",
    "environment_context", "user_instructions", "turn_aborted",
)
UNWRAP_TAGS = ("command-name", "command-args", "bash-input")
_DROP_RX = [re.compile(r"<%s(?:\s[^>]*)?>.*?</%s>" % (t, t), re.S) for t in DROP_TAGS]
_UNWRAP_RX = re.compile(r"</?(?:%s)(?:\s[^>]*)?>" % "|".join(UNWRAP_TAGS))
_INTERRUPTED = re.compile(r"^\[Request interrupted by user[^\]]*\]$")
_CMD_NAME = re.compile(r"<command-name>(.*?)</command-name>", re.S)
_CMD_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)

DEFAULT_SCRUB_PATTERNS = [
    r"sk-[A-Za-z0-9_-]{20,}",
    r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}=*",
    r"\bgh[pousr]_[A-Za-z0-9]{20,}",
    r"\bgithub_pat_[A-Za-z0-9_]{20,}",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\bhvs\.[A-Za-z0-9_-]{20,}",
    r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)",
    # A run of 32+ hex characters (this also catches commit hashes).
    r"(?<![A-Za-z0-9])[A-Fa-f0-9]{32,}(?![A-Za-z0-9])",
    # A run of 32+ base64 / url-safe characters with a digit, an upper- and a
    # lower-case letter (plain words, paths and lower-case ids do not match).
    r"(?<![A-Za-z0-9+/_-])(?=[A-Za-z0-9+/_-]*[0-9])(?=[A-Za-z0-9+/_-]*[A-Z])"
    r"(?=[A-Za-z0-9+/_-]*[a-z])[A-Za-z0-9+/_-]{32,}={0,2}",
]
_SECRET_TOKEN = re.compile(r"[A-Za-z0-9_\-+/.~]{%d,}={0,2}" % MIN_SECRET_LEN)
_USER_OR_ASSISTANT = re.compile(rb'"type"\s*:\s*"(?:user|assistant)"')


# ---------------------------------------------------------------- paths, log

def claude_home():
    return os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")


def config_path():
    return os.environ.get("TRANSCRIPT_CAPTURE_CONFIG") or os.path.join(
        claude_home(), "transcript-capture.json")


def state_dir():
    return os.environ.get("TRANSCRIPT_CAPTURE_HOME") or os.path.join(
        claude_home(), "transcript-capture")


def log(msg):
    try:
        os.makedirs(state_dir(), exist_ok=True)
        path = os.path.join(state_dir(), "capture.log")
        try:
            if os.path.getsize(path) > LOG_MAX_BYTES:
                os.replace(path, path + ".1")
        except OSError:
            pass
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"),
                                 str(msg).replace("\n", " ")[:500]))
    except Exception:
        pass


def load_config(require_enabled=True):
    """The merged config, or None when missing, unreadable, or disabled."""
    try:
        with open(config_path(), encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    if require_enabled and raw.get("enabled") is not True:
        return None
    cfg = dict(DEFAULTS)
    cfg.update(raw)
    if not isinstance(cfg.get("tags"), list):
        cfg["tags"] = []
    if not isinstance(cfg.get("secret_files"), list):
        cfg["secret_files"] = []
    if not isinstance(cfg.get("extra_metadata"), dict):
        cfg["extra_metadata"] = {}
    try:
        cfg["interval_turns"] = max(1, int(cfg["interval_turns"]))
    except (TypeError, ValueError):
        cfg["interval_turns"] = DEFAULTS["interval_turns"]
    return cfg


def safe_id(session_id):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id))[:120]


# ---------------------------------------------------------------- text

def strip_injected(text):
    """Remove harness-injected blocks and wrapper tags from user text."""
    if not text:
        return ""
    name = _CMD_NAME.search(text)
    if name:  # a slash command: keep it as "/name args"
        args = _CMD_ARGS.search(text)
        cmd = (name.group(1).strip() + " " + (args.group(1).strip() if args else "")).strip()
        text = _CMD_ARGS.sub("", _CMD_NAME.sub(lambda m: cmd, text, count=1))
    for rx in _DROP_RX:
        text = rx.sub("", text)
    text = _UNWRAP_RX.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _block_texts(content):
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [b.get("text") or "" for b in content
                if isinstance(b, dict) and b.get("type") == "text"]
    return []


def claude_user_text(obj):
    """The text the user typed, or None for any line that is not a human turn."""
    if (obj.get("isSidechain") or obj.get("isMeta") or obj.get("isCompactSummary")
            or obj.get("isVisibleInTranscriptOnly")):
        return None
    origin = obj.get("origin")
    if isinstance(origin, dict) and origin.get("kind") not in (None, "human"):
        return None  # task notifications, peer-agent messages, and the like
    content = (obj.get("message") or {}).get("content")
    if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return None
    text = strip_injected("\n\n".join(_block_texts(content)))
    if not text or _INTERRUPTED.match(text):
        return None
    return text


def claude_assistant_text(obj):
    if obj.get("isSidechain") or obj.get("isApiErrorMessage"):
        return None
    msg = obj.get("message") or {}
    if msg.get("model") == "<synthetic>":
        return None
    parts = [p.strip() for p in _block_texts(msg.get("content")) if p and p.strip()]
    return "\n\n".join(parts) or None


def claude_events(raw):
    """Events from one session-file line: ("user"|"assistant"|"cwd", value, ts)."""
    if not _USER_OR_ASSISTANT.search(raw):
        return []
    try:
        obj = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(obj, dict) or obj.get("isSidechain"):
        return []
    kind = obj.get("type")
    if kind not in ("user", "assistant"):
        return []
    ts = obj.get("timestamp") or ""
    out = []
    cwd = obj.get("cwd")
    if isinstance(cwd, str) and cwd:
        out.append(("cwd", cwd, ts))
    text = claude_user_text(obj) if kind == "user" else claude_assistant_text(obj)
    if text:
        out.append((kind, text, ts))
    return out


def render(turns):
    out = []
    for t in turns:
        if t.get("u"):
            out.append("user: " + t["u"])
        if t.get("a"):
            out.append("assistant: " + "\n\n".join(t["a"]))
    return "\n\n".join(out)


# ---------------------------------------------------------------- scrubbing

_secret_cache = {}


def secret_values(patterns):
    """Token-like strings found in the configured secret files. Never logged."""
    key = tuple(patterns or ())
    if key in _secret_cache:
        return _secret_cache[key]
    vals = set()
    for pat in key:
        try:
            paths = glob.glob(os.path.expanduser(str(pat)))
        except Exception:
            continue
        for path in paths:
            try:
                if not os.path.isfile(path) or os.path.getsize(path) > MAX_SECRET_FILE_BYTES:
                    continue
                with open(path, encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue
            for tok in _SECRET_TOKEN.findall(text):
                if tok[0] in "/~." or "://" in tok:
                    continue
                if re.search(r"[0-9]", tok) and re.search(r"[A-Za-z]", tok):
                    vals.add(tok)
    result = sorted(vals, key=len, reverse=True)
    _secret_cache[key] = result
    return result


def compiled_patterns(cfg):
    pats = cfg.get("scrub_patterns")
    if not isinstance(pats, list):
        pats = DEFAULT_SCRUB_PATTERNS
    out = []
    for p in pats:
        try:
            out.append(re.compile(str(p)))
        except re.error:
            log("scrub pattern skipped: does not compile")
    return out


def scrub(text, cfg):
    for v in secret_values(cfg.get("secret_files") or []):
        if v in text:
            text = text.replace(v, REDACTED)
    pats = compiled_patterns(cfg)
    if cfg.get("scrub_whole_line"):
        lines = text.split("\n")
        text = "\n".join(REDACTED_LINE if any(p.search(line) for p in pats) else line
                         for line in lines)
    else:
        for p in pats:
            text = p.sub(REDACTED, text)
    return text


# ---------------------------------------------------------------- tags, retain

def _split_path(path):
    parts = []
    path = os.path.normpath(os.path.abspath(os.path.expanduser(path)))
    while True:
        head, tail = os.path.split(path)
        if tail:
            parts.append(tail)
        if not head or head == path:
            parts.append(head)
            break
        path = head
    return list(reversed([p for p in parts if p]))


def project_name(cwd, projects_root):
    """The folder directly under projects_root that holds cwd, lower-cased."""
    if not cwd or not projects_root:
        return None
    try:
        c, r = _split_path(cwd), _split_path(projects_root)
    except Exception:
        return None
    if len(c) <= len(r):
        return None
    if [os.path.normcase(x) for x in c[:len(r)]] != [os.path.normcase(x) for x in r]:
        return None
    return c[len(r)].lower()


def build_retain(cfg, cur, turns, first_turn, harness):
    text = scrub(render(turns), cfg)
    if not text.strip():
        return None
    tags = [str(t) for t in cfg.get("tags") or []]
    proj = project_name(cur.get("cwd"), cfg.get("projects_root"))
    if proj:
        tags.append("project:" + proj)
    tags = list(dict.fromkeys(tags))
    meta = {str(k): str(v) for k, v in (cfg.get("extra_metadata") or {}).items()}
    if cfg.get("device"):
        meta["device"] = str(cfg["device"])
    meta.update({
        "harness": harness,
        "session": cur["session_id"],
        "kind": "transcript",
        "turns": "%d-%d" % (first_turn, first_turn + len(turns) - 1),
    })
    args = {
        "content": text,
        "document_id": "session:" + cur["session_id"],
        "update_mode": "append",
        "tags": tags,
        "metadata": meta,
        "context": CONTEXT,
    }
    if turns[0].get("ts"):
        args["timestamp"] = turns[0]["ts"]
    return args


# ---------------------------------------------------------------- MCP client

class McpError(Exception):
    pass


def read_key(path):
    try:
        with open(os.path.expanduser(str(path)), encoding="utf-8") as f:
            key = f.read().strip()
    except OSError:
        raise McpError("key file unreadable")
    if not key or "\n" in key:
        raise McpError("key file is empty or not a single line")
    return key


def _pick(msg, want_id):
    if isinstance(msg, list):
        for m in msg:
            if isinstance(m, dict) and m.get("id") == want_id:
                return m
        return None
    if isinstance(msg, dict) and msg.get("id") == want_id:
        return msg
    return None


def _read_sse(resp, want_id, deadline):
    data = []

    def done():
        if not data:
            return None
        payload = "\n".join(data)
        del data[:]
        try:
            return _pick(json.loads(payload), want_id)
        except ValueError:
            return None

    total = 0
    while True:
        if time.monotonic() > deadline:
            raise McpError("timed out reading the event stream")
        line = resp.readline(MAX_RESPONSE_BYTES)
        if not line:
            break
        total += len(line)
        if total > MAX_RESPONSE_BYTES:
            raise McpError("event stream too large")
        line = line.decode("utf-8", "replace").rstrip("\r\n")
        if line == "":
            m = done()
            if m is not None:
                return m
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            data.append(value)
    m = done()
    if m is not None:
        return m
    raise McpError("no response in the event stream")


def _request(url, method, payload, headers, deadline, want_id):
    import urllib.error
    import urllib.request
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise McpError("timed out")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=remaining)
    except urllib.error.HTTPError as e:
        raise McpError("HTTP %s on %s" % (e.code, (payload or {}).get("method", method)))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise McpError("connection failed: %s" % (getattr(e, "reason", None) or type(e).__name__))
    with resp:
        session = resp.headers.get("Mcp-Session-Id")
        if want_id is None:
            resp.read(65536)
            return session, None
        ctype = (resp.headers.get("Content-Type") or "").lower()
        try:
            if "text/event-stream" in ctype:
                msg = _read_sse(resp, want_id, deadline)
            else:
                msg = _pick(json.loads(resp.read(MAX_RESPONSE_BYTES).decode("utf-8", "replace")),
                            want_id)
        except (OSError, ValueError) as e:
            raise McpError("bad response: %s" % type(e).__name__)
    if msg is None:
        raise McpError("no JSON-RPC response with id %s" % want_id)
    if msg.get("error"):
        err = msg["error"] if isinstance(msg["error"], dict) else {}
        raise McpError("JSON-RPC error %s: %s" % (err.get("code"), str(err.get("message"))[:200]))
    return session, msg.get("result") or {}


def _result_text(result):
    return " ".join(c.get("text") or "" for c in result.get("content") or []
                    if isinstance(c, dict))


def _choose_tool(tools, mount):
    names = [t.get("name") for t in tools if isinstance(t, dict) and t.get("name")]
    if "retain" in names:
        return "retain"
    cands = [n for n in names if re.search(r"(?:^|[-_.])retain$", n) and "sync" not in n]
    if mount:
        pref = [n for n in cands if n.startswith(mount)]
        cands = pref or cands
    if not cands:
        raise McpError("no retain tool offered by the gateway")
    return cands[0]


def mcp_call_tool(cfg, arguments, tool=None):
    """initialize -> notifications/initialized -> [tools/list] -> tools/call."""
    url = cfg.get("gateway_url") or ""
    if not url:
        raise McpError("gateway_url not set")
    key = read_key(cfg.get("key_file") or "")
    deadline = time.monotonic() + float(cfg.get("timeout_s") or 15)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer " + key,
        "User-Agent": "transcript-capture/" + VERSION,
    }
    if cfg.get("mount"):
        headers[cfg.get("mount_header") or "x-mcp-servers"] = str(cfg["mount"])
    session, result = _request(url, "POST", {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                   "clientInfo": {"name": "transcript-capture", "version": VERSION}},
    }, headers, deadline, 1)
    if session:
        headers["Mcp-Session-Id"] = session
    headers["MCP-Protocol-Version"] = str(result.get("protocolVersion") or PROTOCOL_VERSION)
    _request(url, "POST", {"jsonrpc": "2.0", "method": "notifications/initialized"},
             headers, deadline, None)
    name = tool or cfg.get("tool_name")
    if not name:
        _, listed = _request(url, "POST", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                             headers, deadline, 2)
        name = _choose_tool(listed.get("tools") or [], cfg.get("mount"))
    _, result = _request(url, "POST", {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }, headers, deadline, 3)
    if result.get("isError"):
        raise McpError("tool error: %s" % _result_text(result)[:300])
    if session:
        try:
            _request(url, "DELETE", None, headers,
                     min(deadline, time.monotonic() + 2), None)
        except McpError:
            pass
    return result


def _find_key(obj, keys):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and isinstance(v, (str, int)):
                return str(v)
            found = _find_key(v, keys)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_key(v, keys)
            if found:
                return found
    return None


def operation_id(result):
    keys = ("operation_id", "operationId")
    found = _find_key(result.get("structuredContent"), keys)
    if found:
        return found
    for c in result.get("content") or []:
        text = c.get("text") if isinstance(c, dict) else None
        if not text:
            continue
        try:
            found = _find_key(json.loads(text), keys)
        except ValueError:
            m = re.search(r"operation[_ ]?id[\"':=\s]+([A-Za-z0-9_-]+)", text, re.I)
            found = m.group(1) if m else None
        if found:
            return found
    return None


def send(cfg, arguments):
    """(True, operation_id or "") on success, (False, reason) on any failure."""
    try:
        return True, operation_id(mcp_call_tool(cfg, arguments)) or ""
    except McpError as e:
        return False, str(e)
    except Exception as e:  # never raise into the harness
        return False, "unexpected %s" % type(e).__name__


def write_owed(arguments, reason, harness):
    try:
        os.makedirs(state_dir(), exist_ok=True)
        path = os.path.join(state_dir(), "owed-%s.jsonl" % time.strftime("%Y-%m-%d"))
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "harness": harness,
               "error": reason, "arguments": arguments}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        log("owed write failed: %s" % type(e).__name__)


def replay_owed(cfg, sender=None):
    """Resend owed retains; whatever still fails goes back to an owed file."""
    sender = sender or send
    sent = failed = 0
    for path in sorted(glob.glob(os.path.join(state_dir(), "owed-*.jsonl"))):
        work = "%s.replay-%d" % (path, os.getpid())
        try:
            os.replace(path, work)
        except OSError:
            continue
        down = False
        try:
            with open(work, encoding="utf-8") as f:
                lines = [ln for ln in f if ln.strip()]
            for ln in lines:
                try:
                    rec = json.loads(ln)
                except ValueError:
                    log("owed replay: unreadable line dropped from %s" % os.path.basename(path))
                    continue
                if not down:
                    ok, info = sender(cfg, rec.get("arguments") or {})
                    if ok:
                        sent += 1
                        continue
                    down = True
                    rec["error"] = info
                failed += 1
                with open(path, "a", encoding="utf-8") as out:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            os.remove(work)
        except OSError as e:
            log("owed replay %s: %s" % (os.path.basename(path), type(e).__name__))
    return sent, failed


# ---------------------------------------------------------------- cursor

def cursor_path(session_id):
    return os.path.join(state_dir(), "cursors", safe_id(session_id) + ".json")


def load_cursor(session_id, transcript_path, harness):
    try:
        with open(cursor_path(session_id), encoding="utf-8") as f:
            cur = json.load(f)
        if isinstance(cur, dict) and cur.get("session_id") == session_id:
            return cur
    except (OSError, ValueError):
        pass
    return {"version": 1, "session_id": session_id, "harness": harness,
            "transcript_path": transcript_path, "offset": 0, "turns_sent": 0,
            "pending": [], "cwd": None, "last_operation_id": None, "ops": [],
            "owed_batches": 0}


def save_cursor(cur):
    path = cursor_path(cur["session_id"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cur["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False)
    os.replace(tmp, path)


def advance(cur, path, events_fn):
    """Read complete lines from the cursor's offset and add their turns to pending."""
    offset = int(cur.get("offset") or 0)
    size = os.path.getsize(path)
    if size < offset:
        log("session file shorter than its cursor; skipping ahead: %s" % cur["session_id"])
        cur["offset"] = size
        return
    pending = cur.setdefault("pending", [])
    with open(path, "rb") as f:
        f.seek(offset)
        for raw in f:
            if not raw.endswith(b"\n"):
                break  # a line still being written; read it next time
            offset += len(raw)
            for kind, value, ts in events_fn(raw):
                if kind == "cwd":
                    cur["cwd"] = value
                elif kind == "user":
                    pending.append({"u": value, "a": [], "ts": ts})
                elif pending:
                    pending[-1]["a"].append(value)
                else:
                    pending.append({"u": "", "a": [value], "ts": ts})
    cur["offset"] = offset


def ready_turns(cur, force):
    """Turns that are certainly complete. Without force the newest turn waits for
    the next user message, since the session file can lag the Stop event."""
    n = len(cur.get("pending") or [])
    return n if force else max(0, n - 1)


def flush(cfg, cur, force, harness, sender=None):
    """Send complete turns in batches of interval_turns (any remainder when forced)."""
    sender = sender or send
    interval = cfg["interval_turns"]
    batches = 0
    while True:
        ready = ready_turns(cur, force)
        if ready == 0 or (not force and ready < interval):
            return batches
        if not force and batches >= MAX_BATCHES_PER_STOP:
            return batches
        n = min(interval, ready)
        turns = cur["pending"][:n]
        first = int(cur.get("turns_sent") or 0) + 1
        args = build_retain(cfg, cur, turns, first, harness)
        failed = False
        if args is not None:
            ok, info = sender(cfg, args)
            if ok:
                cur["last_operation_id"] = info or None
                cur["ops"] = (cur.get("ops") or [])[-(KEEP_OPS - 1):] + [
                    {"op": info, "turns": args["metadata"]["turns"]}]
            else:
                write_owed(args, info, harness)
                cur["owed_batches"] = int(cur.get("owed_batches") or 0) + 1
                log("retain failed, written to owed file: %s" % info)
                failed = True
        cur["turns_sent"] = first + n - 1
        del cur["pending"][:n]
        save_cursor(cur)
        batches += 1
        if failed:
            return batches  # do not spend another timeout on a door that is down


class SessionLock(object):
    def __init__(self, session_id):
        self.path = os.path.join(state_dir(), "locks", safe_id(session_id) + ".lock")
        self.held = False

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode("ascii"))
                os.close(fd)
                self.held = True
                return True
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > LOCK_STALE_S:
                        os.remove(self.path)
                        continue
                except OSError:
                    pass
                return False
            except OSError:
                return False
        return False

    def __exit__(self, *exc):
        if self.held:
            try:
                os.remove(self.path)
            except OSError:
                pass
        return False


def process_session(cfg, session_id, path, events_fn, harness, force=False, cwd=None,
                    sender=None, dry_run=False):
    """Advance one session's cursor and send what is due. Returns batches sent."""
    if dry_run:  # read only: no lock, no cursor write
        cur = load_cursor(session_id, path, harness)
        advance(cur, path, events_fn)
        ready = ready_turns(cur, force)
        turns = cur["pending"][:ready]
        text = scrub(render(turns), cfg) if turns else ""
        proj = project_name(cwd or cur.get("cwd"), cfg.get("projects_root"))
        print(json.dumps({"session": session_id, "harness": harness, "turns_ready": ready,
                          "chars": len(text), "redactions": text.count(REDACTED),
                          "project_tag": ("project:" + proj) if proj else None}))
        return 0
    with SessionLock(session_id) as held:
        if not held:
            return 0
        cur = load_cursor(session_id, path, harness)
        cur["transcript_path"] = path
        advance(cur, path, events_fn)
        if cwd:
            cur["cwd"] = cwd
        save_cursor(cur)
        return flush(cfg, cur, force, harness, sender)


# ---------------------------------------------------------------- modes

def claude_session_files():
    return glob.glob(os.path.join(claude_home(), "projects", "*", "*.jsonl"))


def claude_session_id(path):
    return os.path.splitext(os.path.basename(path))[0]


def installed_at(record=True):
    """When capture first ran on this device; written on the first run."""
    path = os.path.join(state_dir(), "installed-at")
    try:
        with open(path, encoding="utf-8") as f:
            return float(f.read().strip())
    except (OSError, ValueError):
        pass
    now = time.time()
    if not record:
        return now
    try:
        os.makedirs(state_dir(), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(repr(now))
    except OSError:
        pass
    return now


def catch_up(cfg, harness, files, session_id_fn, events_fn, dry_run=False, sender=None,
             backfill=False):
    """Send what is unsent for every session file changed since the last run and
    idle long enough. The stamp records now - idle, so a file skipped as too
    recent is picked up by the next run. A session with no cursor (the hook
    never saw it) is sent only if its file changed after the first run, or with
    backfill."""
    if not dry_run:
        replay_owed(cfg, sender)
    first_run = installed_at(record=not dry_run)
    stamp = os.path.join(state_dir(), "last-catch-up-%s" % harness)
    since = 0.0
    try:
        with open(stamp, encoding="utf-8") as f:
            since = float(f.read().strip() or 0)
    except (OSError, ValueError):
        pass
    idle_s = float(cfg.get("catch_up_idle_min") or 30) * 60
    horizon = time.time() - idle_s
    done = 0
    for path in sorted(files):
        try:
            mtime = os.path.getmtime(path)
            if mtime <= since or mtime > horizon:
                continue
            sid = session_id_fn(path)
            if not sid:
                continue
            if (not backfill and mtime < first_run
                    and not os.path.isfile(cursor_path(sid))):
                continue
            if sid:
                done += process_session(cfg, sid, path, events_fn, harness, force=True,
                                        sender=sender, dry_run=dry_run)
        except Exception as e:
            log("catch-up %s: %s" % (os.path.basename(path), type(e).__name__))
    if not dry_run:
        os.makedirs(state_dir(), exist_ok=True)
        with open(stamp, "w", encoding="utf-8") as f:
            f.write(repr(horizon))
    return done


def hook(stdin_text, harness, events_fn, session_id_fn=None):
    """Stop hook body: never raises, never prints."""
    try:
        cfg = load_config()
        if not cfg:
            return 0
        installed_at()
        data = json.loads(stdin_text or "{}")
        path = data.get("transcript_path") or ""
        if not path or not os.path.isfile(path):
            return 0
        sid = (session_id_fn(path) if session_id_fn else None) or data.get("session_id")
        if not sid:
            return 0
        process_session(cfg, str(sid), path, events_fn, harness, cwd=data.get("cwd"))
    except Exception as e:
        log("hook error %s: %s" % (type(e).__name__, str(e)[:200]))
    return 0


def main(argv, harness=HARNESS, events_fn=claude_events, files_fn=claude_session_files,
         session_id_fn=claude_session_id, hook_session_id_fn=claude_session_id):
    try:
        if "--catch-up" in argv or "--replay-owed" in argv:
            dry = "--dry-run" in argv
            cfg = load_config(require_enabled=not dry)
            if not cfg:
                return 0
            if "--catch-up" in argv:
                catch_up(cfg, harness, files_fn(), session_id_fn, events_fn, dry_run=dry,
                         backfill="--backfill" in argv)
            else:
                replay_owed(cfg)
            return 0
        return hook(sys.stdin.read(), harness, events_fn, hook_session_id_fn)
    except Exception as e:
        log("error %s: %s" % (type(e).__name__, str(e)[:200]))
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
