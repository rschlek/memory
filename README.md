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

## Data rule

Never store credentials or secrets, and never store sensitive or restricted
data (customer, personal, or financial detail) verbatim; store the conclusion
and where the source lives.

## License

MIT; see [LICENSE](LICENSE).
