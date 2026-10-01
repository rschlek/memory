# sweep

- Maintainer: the memory plugin maintainers
- Submitted: 2026-10-01

Seals a session before its context is lost, at the end of a session or before
a compaction. It retains the decisions, verified findings, corrections, and
open questions that landed in the conversation and are not yet in memory, each
with its reason, date, provenance, and scope tags; writes unfinished working
state to files; names any state models the session left behind; and reports
what went where. Invoking it is the approval to retain. It applies the data
rule to everything it writes.

## Prerequisites

A Hindsight memory bank reachable through an MCP server in the agent. It
follows `references/memory-conventions.md` and
`references/hindsight-binding.md` in this plugin.
