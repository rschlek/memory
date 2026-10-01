# learn

- Maintainer: the memory plugin maintainers
- Submitted: 2026-10-01

Researches a topic the user names and saves one synthesis to the memory bank,
marked as research the agent gathered rather than the user's own knowledge.
It checks that memory is reachable and what is already known, gathers from the
sources that fit (the web, local files, a codebase, library documentation),
shows the synthesis to the user, then writes it in one call and confirms it
landed.

## Prerequisites

A Hindsight memory bank reachable through an MCP server in the agent. It
follows `references/capture-criteria.md` in this plugin.
