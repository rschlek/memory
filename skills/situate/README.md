# situate

- Maintainer: the memory plugin maintainers
- Submitted: 2026-10-01

Catches the agent up on a project, problem, or person before work resumes. It
frames what the session needs to know, reads the bank's state model for the
subject when there is one, finds the tags that really exist in the memory
bank, runs as many scoped recalls as that takes, and returns one brief: goal,
guardrails, decisions with reasons and dates, current state, open questions,
and gaps or conflicts. It only reads memory; it never writes.

## Prerequisites

A Hindsight memory bank reachable through an MCP server in the agent. It
follows `references/memory-conventions.md` and
`references/hindsight-binding.md` in this plugin.
