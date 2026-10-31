#!/usr/bin/env python3
"""Tests for transcript_capture.py and transcript_capture_codex.py.

Run: python -S -I test_transcript_capture.py   (or pytest test_transcript_capture.py)

Everything runs against temporary folders and an in-process HTTP stub on
127.0.0.1; nothing reads the real ~/.claude or contacts a real service.
Fake tokens are assembled at run time so none appears literally in this file.
"""
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "testdata", "claude-session.jsonl")
CODEX_FIXTURE = os.path.join(HERE, "testdata", "codex-rollout.jsonl")
CLAUDE_SID = "11111111-2222-4333-8444-555555555555"
CODEX_SID = "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0000"
ENV_KEYS = ("CLAUDE_CONFIG_DIR", "TRANSCRIPT_CAPTURE_HOME", "TRANSCRIPT_CAPTURE_CONFIG",
            "CODEX_HOME", "TRANSCRIPT_CAPTURE_CORE", "NO_PROXY", "no_proxy")


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tc = load("transcript_capture", "transcript_capture.py")
os.environ["TRANSCRIPT_CAPTURE_CORE"] = os.path.join(HERE, "transcript_capture.py")
tcx = load("transcript_capture_codex", "transcript_capture_codex.py")

FAKE_KEY = "gw" + "Key" + "0123456789abcdefXYZ"  # the gateway key in the key file
FAKE_SK = "sk-" + "Ab1" * 9
FAKE_GH = "gh" + "p_" + "Zz9" * 9
FAKE_AWS = "AK" + "IA" + "ABCDEFGH12345678"
FAKE_FILE_SECRET = "Vault" + "Value" + "9876543210qwerty"
FAKE_BEARER_TOKEN = "abcdefghijklmnop" + "1234567890"


class _Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class Stub(object):
    """A minimal MCP streamable-HTTP server that records what it receives."""

    def __init__(self, sse=False):
        self.sse = sse
        self.call_result = None  # JSON text the retain tool returns; default: accepted
        self.requests = []
        self.calls = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n).decode("utf-8"))
                stub.requests.append({"headers": {k.lower(): v for k, v in self.headers.items()},
                                      "body": body})
                method = body.get("method")
                if method == "initialize":
                    self.reply(body, {"protocolVersion": "2025-06-18",
                                      "capabilities": {"tools": {}},
                                      "serverInfo": {"name": "stub", "version": "0"}},
                               session="stub-session-1")
                elif method == "notifications/initialized":
                    self.send_response(202)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                elif method == "tools/list":
                    self.reply(body, {"tools": [{"name": "door-recall"},
                                                {"name": "door-sync_retain"},
                                                {"name": "door-retain"}]})
                elif method == "tools/call":
                    stub.calls.append(body["params"])
                    op = "op-%d" % len(stub.calls)
                    text = stub.call_result or json.dumps({"success": True, "operation_id": op})
                    self.reply(body, {"content": [{"type": "text", "text": text}],
                                      "isError": False})
                else:
                    self.reply(body, None, error={"code": -32601, "message": "no such method"})

            def do_DELETE(self):
                stub.requests.append({"headers": {k.lower(): v for k, v in self.headers.items()},
                                      "body": "DELETE"})
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def reply(self, req, result, session=None, error=None):
                msg = {"jsonrpc": "2.0", "id": req.get("id")}
                if error:
                    msg["error"] = error
                else:
                    msg["result"] = result
                text = json.dumps(msg)
                if stub.sse:
                    note = json.dumps({"jsonrpc": "2.0", "method": "notifications/message",
                                       "params": {"level": "info", "data": "working"}})
                    data = (": keep-alive\n\nevent: message\ndata: %s\n\n"
                            "event: message\nid: 2\ndata: %s\n\n" % (note, text)).encode()
                    ctype = "text/event-stream"
                else:
                    data, ctype = text.encode(), "application/json"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                if session:
                    self.send_header("Mcp-Session-Id", session)
                self.end_headers()
                self.wfile.write(data)

        self.httpd = _Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:%d/mcp/" % self.httpd.server_address[1]

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def dead_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return "http://127.0.0.1:%d/mcp/" % port


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in ENV_KEYS}
        self.tmp = tempfile.mkdtemp(prefix="tc-test-")
        self.claude = os.path.join(self.tmp, "claude")
        os.makedirs(self.claude)
        os.environ["CLAUDE_CONFIG_DIR"] = self.claude
        os.environ["CODEX_HOME"] = os.path.join(self.tmp, "codex")
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
        os.environ.pop("TRANSCRIPT_CAPTURE_HOME", None)
        os.environ.pop("TRANSCRIPT_CAPTURE_CONFIG", None)
        os.environ["TRANSCRIPT_CAPTURE_CORE"] = os.path.join(HERE, "transcript_capture.py")
        tc._secret_cache.clear()
        tcx.core._secret_cache.clear()
        self.key_file = os.path.join(self.tmp, "device.key")
        with open(self.key_file, "w") as f:
            f.write(FAKE_KEY + "\n")
        self.stubs = []

    def tearDown(self):
        for s in self.stubs:
            s.close()
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stub(self, sse=False):
        s = Stub(sse=sse)
        self.stubs.append(s)
        return s

    def write_config(self, url, **over):
        cfg = {"enabled": True, "gateway_url": url, "mount": "door", "key_file": self.key_file,
               "interval_turns": 10, "projects_root": "/home/user/projects",
               "tags": ["group:example"], "device": "test-device", "secret_files": [],
               "extra_metadata": {"site": "lab"}}
        cfg.update(over)
        with open(os.path.join(self.claude, "transcript-capture.json"), "w") as f:
            json.dump(cfg, f)
        return tc.load_config()

    def copy_session(self, src=FIXTURE, name=CLAUDE_SID + ".jsonl", project="-home-user-proj"):
        d = os.path.join(self.claude, "projects", project)
        os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, name)
        shutil.copyfile(src, dst)
        return dst

    def state(self, *parts):
        return os.path.join(self.claude, "transcript-capture", *parts)

    def run_script(self, script, stdin="", args=()):
        env = dict(os.environ)
        return subprocess.run([sys.executable, "-S", "-I", os.path.join(HERE, script)] + list(args),
                              input=stdin, capture_output=True, text=True, env=env, timeout=60)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_json(path):
    return json.loads(read_text(path))


def turns_of(args):
    """The turn range from a sent batch's header line."""
    m = re.match(r"## turns (\d+-\d+), \d{4}-\d\d-\d\dT\d\d:\d\dZ, session \S+\n\n", args["content"])
    assert m, args["content"][:80]
    return m.group(1)


def body_of(args):
    return args["content"].split("\n\n", 1)[1]


def parse_all(path, events_fn):
    cur = {"session_id": "s", "offset": 0, "pending": []}
    tc.advance(cur, path, events_fn)
    return cur


class ParseTests(Base):
    def test_keeps_conversation_text_only(self):
        cur = parse_all(FIXTURE, tc.claude_events)
        turns = cur["pending"]
        self.assertEqual([t["u"] for t in turns], [
            "Please list the files in this repo.",
            "Thanks. Now explain the src folder.",
            "/sweep now",
            "A question from an older harness version without an origin field?",
        ])
        self.assertEqual(turns[0]["a"], ["I'll look at the tree first.",
                                         "There are two entries: README.md and src.",
                                         "The background task finished too."])
        self.assertEqual(turns[1]["a"], ["src holds the code."])
        self.assertEqual(turns[2]["a"], [])
        self.assertEqual(turns[3]["a"], ["An answer to it."])
        text = tc.render(turns)
        for absent in ("must not appear", "Injected context", "private reasoning",
                       "toolu_", "task-notification", "Base directory", "interrupted",
                       "No response requested", "system-reminder"):
            self.assertNotIn(absent, text)
        self.assertTrue(text.startswith("user: Please list the files in this repo.\n\nassistant: "))
        self.assertEqual(cur["cwd"], "/home/user/projects/sample-repo/.claude/worktrees/feature")
        self.assertEqual(turns[0]["ts"], "2026-01-02T10:01:00.000Z")

    def test_strip_injected(self):
        self.assertEqual(tc.strip_injected("a\n<system-reminder>x\ny</system-reminder>\nb"), "a\n\nb")
        self.assertEqual(tc.strip_injected("<system-reminder>only</system-reminder>"), "")
        self.assertEqual(tc.strip_injected("<command-name>/x</command-name>"), "/x")

    def test_codex_events(self):
        cur = parse_all(CODEX_FIXTURE, tcx.codex_events)
        self.assertEqual([(t["u"], t["a"]) for t in cur["pending"]], [
            ("Run the tests please.", ["All 12 tests pass."]),
            ("Thanks, commit it.", ["Committed."]),
        ])
        self.assertEqual(cur["cwd"], "/home/user/projects/sample-repo")
        self.assertNotIn("must not appear", tc.render(cur["pending"]))
        self.assertEqual(tcx.codex_session_id(CODEX_FIXTURE), CODEX_SID)

    def test_project_name(self):
        root = "/home/user/projects"
        self.assertEqual(tc.project_name("/home/user/projects/Repo/.claude/worktrees/x", root), "repo")
        self.assertEqual(tc.project_name("/home/user/projects/repo", root), "repo")
        self.assertIsNone(tc.project_name("/home/user/projects", root))
        self.assertIsNone(tc.project_name("/home/user/other/repo", root))
        self.assertIsNone(tc.project_name("/home/user/projects-old/repo", root))
        self.assertIsNone(tc.project_name("/x", ""))


class CursorTests(Base):
    def test_advance_is_incremental_and_skips_partial_lines(self):
        with open(FIXTURE, "rb") as f:
            data = f.read()
        lines = data.split(b"\n")
        path = os.path.join(self.tmp, "s.jsonl")
        head = b"\n".join(lines[:7]) + b"\n" + lines[7][:30]  # line 8 half written
        with open(path, "wb") as f:
            f.write(head)
        cur = {"session_id": "s", "offset": 0, "pending": []}
        tc.advance(cur, path, tc.claude_events)
        self.assertEqual(cur["offset"], len(b"\n".join(lines[:7])) + 1)
        self.assertEqual(len(cur["pending"]), 1)
        self.assertEqual(len(cur["pending"][0]["a"]), 2)
        with open(path, "wb") as f:
            f.write(data)
        tc.advance(cur, path, tc.claude_events)
        self.assertEqual(cur["offset"], len(data))
        self.assertEqual(len(cur["pending"]), 4)
        self.assertEqual(len(cur["pending"][0]["a"]), 3)
        tc.advance(cur, path, tc.claude_events)  # nothing new
        self.assertEqual(len(cur["pending"]), 4)


class IntervalTests(Base):
    def fake_sender(self):
        sent = []

        def sender(cfg, args):
            sent.append(args)
            return True, "op-%d" % len(sent)
        return sent, sender

    def test_stop_waits_for_interval_and_holds_back_newest_turn(self):
        cfg = self.write_config("http://unused", interval_turns=3)
        path = self.copy_session()
        sent, sender = self.fake_sender()
        tc.process_session(cfg, CLAUDE_SID, path, tc.claude_events, "claude-code", sender=sender)
        self.assertEqual(len(sent), 1)  # 4 turns read, 3 complete, interval 3
        self.assertEqual(turns_of(sent[0]), "1-3")
        cur = tc.load_cursor(CLAUDE_SID, path, "claude-code")
        self.assertEqual(cur["turns_sent"], 3)
        self.assertEqual(len(cur["pending"]), 1)
        self.assertEqual(cur["last_operation_id"], "op-1")
        # Stop again with nothing new: nothing resent.
        tc.process_session(cfg, CLAUDE_SID, path, tc.claude_events, "claude-code", sender=sender)
        self.assertEqual(len(sent), 1)
        # Forced (catch-up): the held-back turn goes, numbered 4.
        tc.process_session(cfg, CLAUDE_SID, path, tc.claude_events, "claude-code", force=True,
                           sender=sender)
        self.assertEqual(len(sent), 2)
        self.assertEqual(turns_of(sent[1]), "4-4")
        self.assertTrue(body_of(sent[1]).startswith("user: A question from an older"))

    def test_below_interval_sends_nothing(self):
        cfg = self.write_config("http://unused", interval_turns=10)
        path = self.copy_session()
        sent, sender = self.fake_sender()
        tc.process_session(cfg, CLAUDE_SID, path, tc.claude_events, "claude-code", sender=sender)
        self.assertEqual(sent, [])
        cur = tc.load_cursor(CLAUDE_SID, path, "claude-code")
        self.assertEqual(len(cur["pending"]), 4)
        self.assertGreater(cur["offset"], 0)

    def test_forced_send_batches_by_interval(self):
        cfg = self.write_config("http://unused", interval_turns=3)
        path = self.copy_session()
        sent, sender = self.fake_sender()
        tc.process_session(cfg, CLAUDE_SID, path, tc.claude_events, "claude-code", force=True,
                           sender=sender)
        self.assertEqual([turns_of(a) for a in sent], ["1-3", "4-4"])

    def test_retain_arguments(self):
        cfg = self.write_config("http://unused", interval_turns=1)
        path = self.copy_session()
        sent, sender = self.fake_sender()
        tc.process_session(cfg, CLAUDE_SID, path, tc.claude_events, "claude-code", sender=sender)
        a = sent[0]
        self.assertEqual(a["document_id"], "session:" + CLAUDE_SID)
        self.assertEqual(a["update_mode"], "append")
        self.assertEqual(a["tags"], ["group:example", "project:sample-repo"])
        self.assertEqual(a["metadata"], {"site": "lab", "device": "test-device",
                                         "harness": "claude-code", "session": CLAUDE_SID,
                                         "kind": "transcript"})
        self.assertTrue(a["content"].startswith(
            "## turns 1-1, 2026-01-02T10:01Z, session %s\n\nuser: Please list" % CLAUDE_SID))
        self.assertEqual(a["context"], tc.CONTEXT)
        self.assertEqual(a["timestamp"], "2026-01-02T10:01:00.000Z")


class ScrubTests(Base):
    def test_patterns_and_secret_files(self):
        secret_file = os.path.join(self.tmp, "vault.env")
        with open(secret_file, "w") as f:
            f.write("SERVICE_TOKEN=%s\nURL=https://example.invalid/path\n" % FAKE_FILE_SECRET)
        cfg = self.write_config("http://unused", secret_files=[os.path.join(self.tmp, "*.env")])
        text = "\n".join([
            "plain words stay, and so does session 11111111-2222-4333-8444-555555555555",
            "key " + FAKE_SK,
            "header Authorization: " + "Bear" + "er " + FAKE_BEARER_TOKEN,
            "gh token " + FAKE_GH,
            "aws " + FAKE_AWS,
            "hash " + "a1b2c3d4" * 5,
            "blob " + "QmFzZTY0" * 5 + "Zz9",
            "from the vault file: " + FAKE_FILE_SECRET,
            "a/long/path/to/some_module_name/file.py stays",
        ])
        out = tc.scrub(text, cfg)
        for secret in (FAKE_SK, FAKE_GH, FAKE_AWS, "a1b2c3d4" * 5, "QmFzZTY0" * 5,
                       FAKE_FILE_SECRET, FAKE_BEARER_TOKEN):
            self.assertNotIn(secret, out)
        self.assertIn("plain words stay, and so does session 11111111-2222-4333-8444-555555555555", out)
        self.assertIn("a/long/path/to/some_module_name/file.py stays", out)
        self.assertEqual(out.count(tc.REDACTED), 7)
        self.assertNotIn("example.invalid", "".join(tc.secret_values([secret_file])))

    def test_whole_line_mode_and_custom_patterns(self):
        cfg = self.write_config("http://unused", scrub_whole_line=True,
                                scrub_patterns=[r"internal-\d+", "("])
        out = tc.scrub("keep this\nticket internal-42 here\nand this", cfg)
        self.assertEqual(out, "keep this\n%s\nand this" % tc.REDACTED_LINE)

    def test_scrub_applies_before_sending(self):
        cfg = self.write_config("http://unused", interval_turns=1)
        cur = {"session_id": "s", "cwd": None}
        args = tc.build_retain(cfg, cur, [{"u": "my key is " + FAKE_SK, "a": ["ok"]}], 1,
                               "claude-code")
        self.assertNotIn(FAKE_SK, args["content"])
        self.assertIn(tc.REDACTED, args["content"])


class McpClientTests(Base):
    def check_exchange(self, stub, tool_name):
        methods = [r["body"]["method"] if isinstance(r["body"], dict) else r["body"]
                   for r in stub.requests]
        expected = ["initialize", "notifications/initialized"]
        if not tool_name:
            expected.append("tools/list")
        expected += ["tools/call", "DELETE"]
        self.assertEqual(methods, expected)
        first = stub.requests[0]["headers"]
        self.assertEqual(first["authorization"], "Bearer " + FAKE_KEY)
        self.assertEqual(first["x-mcp-servers"], "door")
        self.assertNotIn("mcp-session-id", first)
        for r in stub.requests[1:]:
            self.assertEqual(r["headers"]["mcp-session-id"], "stub-session-1")
            self.assertEqual(r["headers"]["mcp-protocol-version"], "2025-06-18")
        self.assertEqual(len(stub.calls), 1)
        self.assertEqual(stub.calls[0]["name"], tool_name or "door-retain")
        return stub.calls[0]["arguments"]

    def test_json_responses_and_tool_discovery(self):
        stub = self.stub(sse=False)
        cfg = self.write_config(stub.url)
        ok, op = tc.send(cfg, {"content": "hello", "document_id": "session:x"})
        self.assertTrue(ok, op)
        self.assertEqual(op, "op-1")
        args = self.check_exchange(stub, None)
        self.assertEqual(args, {"content": "hello", "document_id": "session:x"})

    def test_sse_responses_and_configured_tool(self):
        stub = self.stub(sse=True)
        cfg = self.write_config(stub.url, tool_name="door-retain")
        ok, op = tc.send(cfg, {"content": "hi"})
        self.assertTrue(ok, op)
        self.assertEqual(op, "op-1")
        self.check_exchange(stub, "door-retain")

    def test_operation_id_shapes(self):
        self.assertEqual(tc.operation_id({"structuredContent": {"operation_id": "a"}}), "a")
        self.assertEqual(tc.operation_id({"content": [{"type": "text",
                                                       "text": "{\"result\": {\"operationId\": \"b\"}}"}]}), "b")
        self.assertEqual(tc.operation_id({"content": [{"type": "text",
                                                       "text": "accepted, operation_id: c-1"}]}), "c-1")
        self.assertIsNone(tc.operation_id({"content": []}))

    def test_unit_counts_do_not_decide_success(self):
        ok_shapes = [
            {"operation_id": "a", "status": "completed"},  # merged batch: no unit count
            {"operation_id": "b", "status": "completed", "units": 0},
            {"operation_id": "c", "status": "pending"},
            {"success": True, "operation_id": "d", "items_count": 1},
        ]
        for shape in ok_shapes:
            self.assertIsNone(tc.retain_failure(
                {"content": [{"type": "text", "text": json.dumps(shape)}]}), shape)
        for shape in ({"operation_id": "e", "status": "failed"},
                      {"result": {"status": "ERROR"}}, {"success": False}):
            self.assertIsNotNone(tc.retain_failure(
                {"content": [{"type": "text", "text": json.dumps(shape)}]}), shape)
        self.assertIsNotNone(tc.retain_failure({"structuredContent": {"status": "failed"}}))
        self.assertIsNone(tc.retain_failure({"content": [{"type": "text", "text": "accepted"}]}))

    def test_error_status_goes_to_owed_file(self):
        stub = self.stub()
        stub.call_result = json.dumps({"operation_id": "op-x", "status": "failed"})
        cfg = self.write_config(stub.url, interval_turns=1)
        path = self.copy_session()
        tc.process_session(cfg, CLAUDE_SID, path, tc.claude_events, "claude-code")
        owed = [n for n in os.listdir(self.state()) if n.startswith("owed-")]
        self.assertEqual(len(owed), 1)
        rec = json.loads(read_text(self.state(owed[0])).splitlines()[0])
        self.assertEqual(rec["error"], "service reported status failed")
        stub.call_result = json.dumps({"operation_id": "op-y", "status": "completed"})
        self.assertEqual(tc.replay_owed(cfg), (1, 0))

    def test_missing_key_file_fails_cleanly(self):
        cfg = self.write_config("http://unused", key_file=os.path.join(self.tmp, "nope"))
        ok, why = tc.send(cfg, {"content": "x"})
        self.assertFalse(ok)
        self.assertIn("key file", why)


class HookEndToEndTests(Base):
    def stop_event(self, path, sid=CLAUDE_SID):
        return json.dumps({"session_id": sid, "transcript_path": path,
                           "cwd": "/home/user/projects/sample-repo", "hook_event_name": "Stop",
                           "stop_hook_active": False, "permission_mode": "default",
                           "last_assistant_message": "An answer to it."})

    def test_stop_hook_sends_once_and_records_operation(self):
        stub = self.stub()
        self.write_config(stub.url, interval_turns=2)
        path = self.copy_session()
        r = self.run_script("transcript_capture.py", self.stop_event(path))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertEqual(len(stub.calls), 1)
        args = stub.calls[0]["arguments"]
        self.assertEqual(turns_of(args), "1-2")
        self.assertIn("project:sample-repo", args["tags"])
        cur = read_json(self.state("cursors", CLAUDE_SID + ".json"))
        self.assertEqual(cur["last_operation_id"], "op-1")
        self.assertEqual(cur["turns_sent"], 2)
        r = self.run_script("transcript_capture.py", self.stop_event(path))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(stub.calls), 1)  # the third turn is complete but below interval
        for name in os.listdir(self.state()):
            p = self.state(name)
            if os.path.isfile(p):
                self.assertNotIn(FAKE_KEY, read_text(p))

    def test_owed_file_when_gateway_down_then_replay(self):
        self.write_config(dead_url(), interval_turns=1, timeout_s=3)
        path = self.copy_session()
        r = self.run_script("transcript_capture.py", self.stop_event(path))
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        owed = [n for n in os.listdir(self.state()) if n.startswith("owed-")]
        self.assertEqual(len(owed), 1)
        recs = [json.loads(l) for l in read_text(self.state(owed[0])).splitlines()]
        self.assertEqual(len(recs), 1)  # one failure stops the run
        self.assertEqual(recs[0]["arguments"]["document_id"], "session:" + CLAUDE_SID)
        self.assertEqual(recs[0]["arguments"]["update_mode"], "append")
        self.assertTrue(body_of(recs[0]["arguments"]).startswith("user: Please list"))
        self.assertIn("connection failed", recs[0]["error"])
        cur = read_json(self.state("cursors", CLAUDE_SID + ".json"))
        self.assertEqual((cur["turns_sent"], cur["owed_batches"]), (1, 1))
        log_text = read_text(self.state("capture.log"))
        self.assertNotIn(FAKE_KEY, log_text)
        self.assertNotIn("Please list", log_text)
        # The door comes back: replay sends the owed retain and empties the file.
        stub = self.stub()
        self.write_config(stub.url, interval_turns=1)
        r = self.run_script("transcript_capture.py", args=["--replay-owed"])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(stub.calls), 1)
        self.assertEqual(turns_of(stub.calls[0]["arguments"]), "1-1")
        self.assertEqual([n for n in os.listdir(self.state()) if n.startswith("owed-")], [])

    def test_missing_or_disabled_config_is_silent(self):
        path = self.copy_session()
        r = self.run_script("transcript_capture.py", self.stop_event(path))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertFalse(os.path.exists(self.state()))
        self.write_config("http://unused", enabled=False)
        r = self.run_script("transcript_capture.py", self.stop_event(path))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertFalse(os.path.exists(self.state()))

    def test_garbage_input_is_silent(self):
        self.write_config("http://unused")
        for payload in ("", "not json", "[]", json.dumps({"transcript_path": "/nope"})):
            r = self.run_script("transcript_capture.py", payload)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_codex_stop_hook(self):
        stub = self.stub()
        self.write_config(stub.url, interval_turns=1)
        d = os.path.join(self.tmp, "codex", "sessions", "2026", "01", "02")
        os.makedirs(d)
        path = os.path.join(d, "rollout-2026-01-02T11-00-00-%s.jsonl" % CODEX_SID)
        shutil.copyfile(CODEX_FIXTURE, path)
        event = json.dumps({"session_id": "event-id", "transcript_path": path,
                            "cwd": "/home/user/projects/sample-repo", "hook_event_name": "Stop",
                            "turn_id": "t2", "stop_hook_active": False, "model": "m",
                            "last_assistant_message": "Committed."})
        r = self.run_script("transcript_capture_codex.py", event)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertEqual(len(stub.calls), 1)
        args = stub.calls[0]["arguments"]
        self.assertEqual(args["document_id"], "session:" + CODEX_SID)
        self.assertEqual(args["metadata"]["harness"], "codex")
        self.assertEqual(args["content"], "## turns 1-1, 2026-01-02T11:04Z, session %s\n\n"
                         "user: Run the tests please.\n\nassistant: All 12 tests pass." % CODEX_SID)
        self.assertIn("project:sample-repo", args["tags"])


class CatchUpTests(Base):
    def age(self, path, seconds):
        t = time.time() - seconds
        os.utime(path, (t, t))

    def test_catch_up_sends_idle_sessions_once(self):
        stub = self.stub()
        self.write_config(stub.url, interval_turns=10)
        r = self.run_script("transcript_capture.py", args=["--catch-up"])  # first run
        self.assertEqual(r.returncode, 0)
        old = self.copy_session()
        self.age(old, 3600)
        recent = self.copy_session(name="22222222-2222-4333-8444-555555555555.jsonl")
        # Without --backfill, a session the hook never saw from before the first run waits.
        r = self.run_script("transcript_capture.py", args=["--catch-up"])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(stub.calls, [])
        os.remove(self.state("last-catch-up-claude-code"))
        r = self.run_script("transcript_capture.py", args=["--catch-up", "--backfill"])
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(len(stub.calls), 1)  # the recent file is not idle yet
        args = stub.calls[0]["arguments"]
        self.assertEqual(args["document_id"], "session:" + CLAUDE_SID)
        self.assertEqual(turns_of(args), "1-4")
        self.assertTrue(os.path.isfile(self.state("last-catch-up-claude-code")))
        # A later night: the recent file has gone idle and is newer than the stamp.
        with open(self.state("last-catch-up-claude-code"), "w") as f:
            f.write(repr(time.time() - 7200))
        self.age(recent, 3600)
        r = self.run_script("transcript_capture.py", args=["--catch-up", "--backfill"])
        self.assertEqual(len(stub.calls), 2)
        self.assertEqual(stub.calls[1]["arguments"]["document_id"],
                         "session:22222222-2222-4333-8444-555555555555")
        # And again: every cursor is current, nothing is resent.
        with open(self.state("last-catch-up-claude-code"), "w") as f:
            f.write("0")
        r = self.run_script("transcript_capture.py", args=["--catch-up", "--backfill"])
        self.assertEqual(len(stub.calls), 2)

    def test_catch_up_flushes_a_session_the_hook_saw(self):
        stub = self.stub()
        self.write_config(stub.url, interval_turns=10)
        path = self.copy_session()
        event = json.dumps({"session_id": CLAUDE_SID, "transcript_path": path,
                            "cwd": "/home/user/projects/sample-repo"})
        self.run_script("transcript_capture.py", event)  # below interval: nothing sent
        self.assertEqual(stub.calls, [])
        self.age(path, 3600)
        with open(self.state("installed-at"), "w") as f:
            f.write(repr(time.time()))  # the session file predates install, but has a cursor
        r = self.run_script("transcript_capture.py", args=["--catch-up"])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(stub.calls), 1)
        self.assertEqual(turns_of(stub.calls[0]["arguments"]), "1-4")

    def test_dry_run_reports_counts_only(self):
        self.write_config(dead_url(), enabled=False)
        old = self.copy_session()
        self.age(old, 3600)
        r = self.run_script("transcript_capture.py", args=["--catch-up", "--dry-run", "--backfill"])
        self.assertEqual(r.returncode, 0)
        rows = [json.loads(l) for l in r.stdout.splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["turns_ready"], 4)
        self.assertEqual(rows[0]["project_tag"], "project:sample-repo")
        self.assertNotIn("Please list", r.stdout)
        self.assertFalse(os.path.exists(self.state("cursors")))
        self.assertFalse(os.path.exists(self.state("last-catch-up-claude-code")))


if __name__ == "__main__":
    unittest.main(verbosity=1)
