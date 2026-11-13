# Memory

Long-term memory skills for Claude Code and Codex, on a
[Hindsight](https://hindsight.vectorize.io) memory bank. The plugin does not
install or run Hindsight; it assumes the environment already connects the
agent to a bank through an MCP server, and teaches the agent how to use it
well.

## Skills

| Skill | What it does |
| --- | --- |
| `situate` | Catches up on a project, problem, or person before work resumes. |
| `remember` | Saves a stated fact, decision, or handed-over document with its source. |
| `learn` | Researches a topic and saves the synthesis, marked as agent research. |
| `sweep` | Saves what landed in a session before it closes or compacts. |

The rules the skills share are in `references/`: `memory-conventions.md`
(backend-neutral: read before acting, what to write, the data rule,
provenance, tags, dates), `capture-criteria.md` (how a source is written), and
`hindsight-binding.md` (the Hindsight tools and what to do when memory is
down).

## Prerequisites

Every skill in this plugin talks to a Hindsight memory bank through the
Hindsight MCP server, so that server must be installed and configured for the
agent before the skills will work. How the skills bind to it is described in
`references/hindsight-binding.md`.

## Install

From a catalog that lists this plugin, install `memory` from it. To install
this repository directly:

```bash
# Claude Code
claude plugin marketplace add https://github.com/rschlek/memory.git
claude plugin install memory@memory

# Codex
codex plugin marketplace add https://github.com/rschlek/memory.git
codex plugin add memory@memory
```

A local checkout works the same way: pass its folder to `marketplace add`.
Start a new session afterwards.

## Local files

- `~/.agent-memory/memory-ledger.jsonl`: content hashes of what `remember`
  saved, so the same source is not saved twice. `MEMORY_HOME` moves
  the folder; `MEMORY_LEDGER_PATH` moves the ledger file alone. Ledgers an
  earlier version left in another hidden folder directly under the home
  folder are still read, never changed.
- `~/.agent-memory/retains-owed-<date>.md`: saves that could not be written
  while memory was down, to be retained once it is back.

## Transcript capture

`hooks/` holds an optional hook. As a session goes on, the hook saves the
conversation text from that session (the user's messages and the assistant's
prose, never tool calls or tool output) to a memory bank kept for transcripts.
It sends `interval_turns` turns at a time (10 by default), from a detached
process so the session never waits on it, all into one document per session,
`session:<session_id>`. It reaches the memory service through an MCP door on an
OpenAI-compatible gateway, using a key kept in a file. Installing the plugin
does not turn it on. The plugin registers no hook, and the scripts do nothing
until the user wires them in and writes a config with `enabled: true`. How it
works, every config key, and its failure handling are in
[hooks/README.md](hooks/README.md).

Before wiring it in, the user needs:

- a memory bank for transcripts, separate from the curated bank;
- a door to that bank on the gateway that accepts a key and allows `retain`;
- the key, alone in a file only the user can read.

1. Copy `hooks/transcript_capture.py`, and for Codex also
   `hooks/transcript_capture_codex.py`, to `~/.claude/hooks/`. Wire in the
   copies, not the plugin folder: the plugin folder changes with every update.
2. Write `~/.claude/transcript-capture.json`:

   ```json
   {
     "enabled": true,
     "gateway_url": "https://gateway.example.com/mcp/",
     "mount": "transcripts",
     "key_file": "~/.config/memory/transcripts.key",
     "interval_turns": 10,
     "projects_root": "~/projects",
     "tags": [],
     "device": "laptop",
     "secret_files": ["~/.config/memory/*.key"],
     "extra_metadata": {}
   }
   ```

3. Preview what would be sent. This prints counts only, contacts nothing,
   writes nothing, and works while `enabled` is still false:

   ```bash
   python -S -I ~/.claude/hooks/transcript_capture.py --catch-up --dry-run
   ```

4. Wire the Claude Code `Stop` hook in `~/.claude/settings.json`. Add it next to
   any `Stop` hooks already there. `<python>` is the full path of a Python 3.9+
   interpreter and `<home>` is the home folder, both written with forward
   slashes:

   ```json
   "hooks": {
     "Stop": [{"hooks": [{"type": "command", "command": "<python> -S -I <home>/.claude/hooks/transcript_capture.py", "timeout": 60, "async": true}]}],
     "SessionEnd": [{"hooks": [{"type": "command", "command": "<python> -S -I <home>/.claude/hooks/transcript_capture.py --session-end", "timeout": 10}]}]
   }
   ```

   The hook only reads the session file; when a batch is due it starts a
   detached worker that does the sending, with its own 15-second deadline on
   each exchange. `async` is a second guard against the agent ever waiting.
   The `SessionEnd` entry sends the rest of the session when it ends; its
   hook only starts a worker, well inside the harness's short SessionEnd
   budget.

5. For Codex, add a `Stop` and a `SessionEnd` hook to `~/.codex/config.toml`,
   then trust them once in `/hooks`:

   ```toml
   [[hooks.Stop]]

   [[hooks.Stop.hooks]]
   type = "command"
   command = "<python> -S -I <home>/.claude/hooks/transcript_capture_codex.py"
   timeout = 10

   [[hooks.SessionEnd]]

   [[hooks.SessionEnd.hooks]]
   type = "command"
   command = "<python> -S -I <home>/.claude/hooks/transcript_capture_codex.py --session-end"
   timeout = 3
   ```

   Codex waits for a hook to finish, so the short timeout is only a bound:
   the hook reads and returns, and the sending happens in the worker.
   The same entry can also go in `~/.codex/hooks.json` as
   `{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "...", "timeout": 10}]}]}}`.
   Check the hooks page of the installed Codex version for the exact form.

6. Nothing needs scheduling. The Stop hook sends full batches, the
   SessionEnd hook sends the rest, and about once an hour a Stop sweeps up
   the rest of any session that ended without a SessionEnd. `--catch-up` is
   a tool to run by hand. A session the hook never saw is sent only if its
   file changed after capture first ran on the device. To send older history
   on purpose, run the catch-up once with `--backfill`, after a
   `--dry-run --backfill` preview.

Retains that fail go to `~/.claude/transcript-capture/owed-<date>.jsonl`.
The next worker that reaches the door sends them, and so do a catch-up and
`transcript_capture.py --replay-owed`. To turn capture off, set
`enabled` to false. To remove it, also delete the hook entries (and any
catch-up task an earlier version had you schedule).

## Data rule

Never store credentials or secrets, and never store sensitive or restricted
data (customer, personal, or financial detail) verbatim; store the conclusion
and where the source lives.

## License

MIT; see [LICENSE](LICENSE).
