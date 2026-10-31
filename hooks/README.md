# Transcript capture

An opt-in hook that saves each agent session's conversation, verbatim and as it
happens, into a memory bank kept for transcripts. The plugin does not install
or register it. The user copies the scripts and wires them into the harness
(see the plugin [README](../README.md#transcript-capture)).

| File | What it is |
| --- | --- |
| `transcript_capture.py` | The Claude Code `Stop` hook, plus `--catch-up`, `--replay-owed` and `--dry-run` modes. Holds the cursor, the scrubber and the MCP client. |
| `transcript_capture_codex.py` | The Codex adapter. It reads Codex session files and reuses everything else from `transcript_capture.py`, which it loads from its own folder, then from `~/.claude/hooks/`. |
| `test_transcript_capture.py` | Tests: `python -S -I test_transcript_capture.py`. |
| `testdata/` | Sample Claude Code and Codex session files the tests read. |

## Why a bank of its own

A curated memory bank holds facts that an agent wrote down at a moment when it
knew what was verified, what was ruled and what was only a passing idea. A
transcript holds all three, so it goes to a separate bank: ideally one that
stores text as verbatim chunks without fact extraction, and that the user can
read next to the curated one. Both sides share the session id: the transcript
document is `session:<session_id>`, and an agent's own retains can carry the
same id in `metadata.session`.

## What is kept

Only conversation text: what the user typed and the assistant's prose.

- **Claude Code** (`~/.claude/projects/<project>/<session_id>.jsonl`). A user
  line counts when it is a typed message: its `origin.kind` is `human`, or the
  line has no `origin` field (older versions). These are dropped: tool
  results, `isMeta` lines (injected skill bodies, peer-agent messages), task
  notifications, compaction summaries, interrupt markers and `isSidechain`
  lines (subagents). From the text that is kept, it strips
  `<system-reminder>`, `<task-notification>`, `<local-command-stdout>`,
  `<local-command-caveat>`, `<command-message>` and similar injected blocks.
  A slash command is kept as `/name args`. From assistant lines it keeps
  `text` blocks only, never `thinking` or `tool_use`. Synthetic assistant
  messages are dropped, and so are lines of other types, such as
  `api-request-blob`, `attachment` and `system`.
- **Codex** (`$CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl`, where
  `$CODEX_HOME` defaults to `~/.codex`). The text comes from the `event_msg`
  lines of type `user_message` and `agent_message`. These hold what the user
  typed and what the agent said, without the AGENTS.md and environment
  context that Codex injects into its `response_item` user messages.
  Reasoning, tool calls and tool output are dropped.

A **turn** is one user message and all the assistant text after it, up to the
next user message. Assistant text with no user message before it (a reply to a
background notification after the previous turn was sent) becomes a turn of its
own, holding only that text.

Each retain is rendered as plain text. It starts with a header line that gives
the batch's turn range, the first turn's time (UTC, to the minute) and the
session id:

```
## turns 11-20, 2026-01-02T20:58Z, session <session_id>

user: <message>

assistant: <reply>

user: ...
```

The turn range is in the text, not in the metadata, because the memory service
applies a retain's metadata to the whole document and to every unit in it. A
per-batch value there would be overwritten on every earlier unit by each
append. The header keeps the range in the verbatim text, and in the context
of every chunk near it.

## When it sends

- **Stop hook.** Every time the agent stops, the hook reads the session file
  from the cursor's byte offset (whole lines only), adds the new turns to the
  cursor's pending list, and sends once there are `interval_turns` complete
  turns. The newest turn always waits for the next user message, because the
  session file can lag the Stop event. That way a turn is never sent without
  its last reply. One Stop sends at most three batches; a longer backlog
  waits for the next Stop or the catch-up.
- **Catch-up** (`--catch-up`, from a scheduler). It first replays owed
  retains. Then, for every session file changed since the last catch-up and
  idle for `catch_up_idle_min` minutes, it sends everything the cursor has
  not sent, the newest turn included, in batches of `interval_turns`. The
  stamp file records "now minus the idle time", so a file skipped because it
  was still active is picked up next time. A session the hook never saw is
  sent only if its file changed after capture first ran on this device
  (`installed-at`). `--backfill` lifts that limit, to send older history on
  purpose.
- **Dry run** (`--catch-up --dry-run`, optionally with `--backfill`). It
  prints one JSON line per session that would be sent: turns ready, characters
  after scrubbing, the number of redactions and the project tag. It never
  prints text, contacts no service and writes no file. It runs even while
  `enabled` is false, so the user can preview before turning capture on.

## The retain

One MCP `tools/call` per batch of turns, with these arguments:

| Argument | Value |
| --- | --- |
| `content` | the header line, then the rendered turns, scrubbed |
| `document_id` | `session:<session_id>` |
| `update_mode` | `append` |
| `tags` | the configured `tags`, plus `project:<name>` when the session's working folder is under `projects_root` (`<name>` is the first folder below the root, lower-cased, so a worktree counts as its repository) |
| `metadata` | `extra_metadata`, then `device`, `harness` (`claude-code` or `codex`), `session` and `kind: transcript`; all values are strings, and all are constant for a session, since metadata applies to the whole document |
| `context` | `verbatim transcript of an agent session, conversation text only` |
| `timestamp` | the first turn's timestamp, when the session file has one |

The session id is the session file's name for Claude Code, and the
`session_meta` id for Codex. The hook and the catch-up therefore always use the
same cursor for a file.

## The MCP exchange

It is a minimal streamable-HTTP client written with `urllib`:

1. `POST initialize`, saving the `Mcp-Session-Id` response header.
2. `POST notifications/initialized`.
3. `POST tools/list`, only when `tool_name` is not set. It picks `retain`, or
   a name ending in `-retain`, `_retain` or `.retain` that is not
   `sync_retain`, and prefers names that start with the mount.
4. `POST tools/call`.
5. `DELETE`, to end the MCP session (best effort).

Every request carries `Authorization: Bearer <key>` and, when `mount` is set,
`<mount_header>: <mount>`. Every request after `initialize` also carries
`Mcp-Session-Id` and `MCP-Protocol-Version`. A response can be JSON or a
`text/event-stream`; in a stream, the hook reads events until it finds the
one with the request's id. The whole exchange has one deadline,
`timeout_s`.

The key is read from `key_file` at call time. It is never logged and never
written into the cursor, the owed file or the log.

## When something fails

Nothing raises into the harness. The script always exits 0 and prints nothing
(except in dry-run mode).

- **Failed retain** (connection, HTTP status, JSON-RPC error, a tool error, a
  result that reports an error status or `success: false`, a timeout, an
  unreadable key). The full arguments of the retain go to
  `owed-<date>.jsonl` with the reason. The turns count as handled, so they are
  never sent twice, and that run stops sending. `--replay-owed`, and the start
  of every catch-up, resend the owed retains. Whatever still fails goes back
  into an owed file. Replayed batches can land out of order in the document;
  each batch's header line gives its place.
- **What counts as success.** An accepted retain counts, and so does a
  pending or completed status. A missing or small unit count does not mean
  failure. The service can merge queued appends into one batch: then the
  operation for the second append reports no unit count, and the first
  reports a misleading one. Only an error status or a transport failure sends
  a batch to the owed file. To check a batch by hand, look up its operation
  id (kept in the cursor's `ops`) and expect `completed`.
- **Appends re-chunk the tail.** The service re-chunks the end of the
  document on each append, so a few units at each batch boundary are embedded
  again. That costs embedding time only; no text is lost or duplicated.
- **Any other error** adds one line to `capture.log`, which never holds text
  or keys and rolls over at 512 KB.
- **Overlap.** A per-session lock file keeps a Stop and a catch-up from
  working on one session at the same time. A lock older than two minutes is
  treated as stale.

## Scrubbing

The scrubber runs on the rendered text before every send. The text a session
file holds is otherwise unchanged.

1. It replaces every value read from `secret_files` with `[redacted]`. Each
   glob is expanded and each file of up to 256 KB is read. Every run of 16 or
   more token characters that holds both a letter and a digit is taken as a
   value, except paths and URLs. That covers a bare key file, `KEY=value`
   lines and JSON.
2. It replaces every match of the token patterns with `[redacted]`. The
   default patterns are:
   - `sk-...`
   - `Bearer ...`
   - GitHub tokens (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`, `github_pat_`)
   - `AKIA...`
   - `hvs....`
   - Slack `xox?-` tokens
   - PEM private-key blocks
   - runs of 32 or more hex characters (this catches commit hashes too)
   - runs of 32 or more base64 characters that mix digits with upper- and
     lower-case letters

   `scrub_patterns` replaces this list. With `scrub_whole_line`, the whole
   line that matches becomes `[redacted line]`.

## Config

The config file is `~/.claude/transcript-capture.json`. If `CLAUDE_CONFIG_DIR`
is set, the file is in that folder. `TRANSCRIPT_CAPTURE_CONFIG` names the file
directly. Both scripts read the same file. When the file is missing or
`enabled` is not `true`, they do nothing.

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `false` | Must be `true` before anything is read or sent. |
| `gateway_url` | (required) | The MCP endpoint of the gateway door, for example `https://gateway.example.com/mcp/`. |
| `mount` | `""` | The door's server name on the gateway. Sent in `mount_header`; leave it empty for a gateway that serves only one server. |
| `mount_header` | `x-mcp-servers` | The header the gateway uses to pick a server. |
| `key_file` | (required) | A file that holds only the gateway key, on one line. It is read at call time. |
| `tool_name` | `""` | The retain tool's name as the gateway lists it. When empty, it is found with `tools/list`. |
| `interval_turns` | `10` | Complete turns per retain. At most this many turns are lost if a session dies without a catch-up. |
| `projects_root` | `""` | The folder that holds the repositories. A session that runs below it gets `project:<repository folder>`. |
| `tags` | `[]` | Tags put on every retain, for example a group tag. |
| `device` | `""` | `metadata.device`. Left out when empty. |
| `secret_files` | `[]` | Globs of files whose values are redacted (`~` is expanded). |
| `scrub_patterns` | built in | A list of regular expressions that replaces the default token patterns. An expression that does not compile is skipped and logged. |
| `scrub_whole_line` | `false` | Redact the whole line that matches, instead of only the match. |
| `extra_metadata` | `{}` | More metadata, as strings. It cannot override `device`, `harness`, `session` or `kind`. Metadata applies to the whole document, so keep these values constant. |
| `timeout_s` | `15` | Deadline for one whole MCP exchange, in seconds. |
| `catch_up_idle_min` | `30` | Minutes a session file must be untouched before the catch-up sends its newest turn. |

## State

The state folder is `~/.claude/transcript-capture/`, or
`$TRANSCRIPT_CAPTURE_HOME` when that is set. It holds these files:

- `cursors/<session_id>.json` holds:
  - `offset`, the byte offset read up to
  - `turns_sent`
  - `pending`, the turns read but not sent yet
  - `cwd`
  - `last_operation_id`
  - `ops`, the last 20 operation ids with their turn ranges
  - `owed_batches`

  Deleting a cursor makes the next run read that session again from the
  start, and those turns are sent again.
- `owed-<date>.jsonl` holds the retains that failed, verbatim.
- `last-catch-up-<harness>` is the catch-up stamp. `installed-at` records when
  capture first ran on this device.
- `capture.log` is the error log.
- `locks/` holds the per-session locks.

The cursor and the owed file hold conversation text, as the session files do.
Keep the state folder as private as the harness's own folder.

## Testing

```
python -S -I test_transcript_capture.py
```

The tests use temporary folders and an HTTP stub on `127.0.0.1` that serves
both JSON and event-stream responses and records each `tools/call`. They cover:

- parsing both session formats
- cursor advance and half-written lines
- the interval and the newest turn held back
- the retain arguments
- scrubbing
- the MCP exchange
- the owed file when the gateway is down, and its replay
- silent exits on a missing config or bad input
- catch-up, backfill and dry run

They never read the real `~/.claude`. Any fake token the tests need is put
together at run time.

## Known limits

- The Codex line format was checked against session files written by Codex
  CLI 0.100 and 0.107, and against the rollout recorder's source. There is no
  published format spec. See the TODO in `transcript_capture_codex.py`.
- Codex documents `session_id` in its Stop input, but the docs do not say
  whether it equals the rollout's `session_meta` id. The adapter uses the
  `session_meta` id, so it does not depend on the answer.
- A typed Claude Code message is recognized by `origin.kind`. If a later
  version changes that field, injected lines will show up as user turns. The
  parse tests on `testdata/` are where to catch that.
