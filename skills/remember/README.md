# remember

- Maintainer: the memory plugin maintainers
- Submitted: 2026-10-01

Saves one thing to the memory bank with its source: a fact or decision the
user states, or a document they hand over (a transcript, PDF, image, or pasted
report). Documents are normalized to text, checked against the data rule,
checked for an exact repeat with `scripts/hash_guard.py`, dated by when they
are about, and written in a single call. The skill confirms the write
completed before it reports, then records the content hash so the same source
is not saved twice.

## Prerequisites

A Hindsight memory bank reachable through an MCP server in the agent. Python
3.9 or newer for `scripts/hash_guard.py`, which keeps a small local ledger of
content hashes (location in `SKILL.md`). It follows
`references/capture-criteria.md` in this plugin.
