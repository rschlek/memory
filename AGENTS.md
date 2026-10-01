# Agent guidance

<!-- project-guide:base start (0.4.0) -->
## Working in this repo

This repo follows the project-guide standard, version 0.4.0
(https://github.com/rschlek/project-guide). This block is replaced when the
standard updates; put project-specific guidance in the section below it.

- Read `README.md` and `project.yaml` first: what this is, who it is for,
  and where related things live.
- Before changing `project.yaml`, `README.md`, `AGENTS.md`, `CLAUDE.md`, or
  the repo's layout, read `docs/project-conventions.md` and keep to it.
- Make one change for one purpose, and run the checks this repo documents
  before proposing it.
- Commit only the files you changed, by path. Never commit credentials,
  tokens, or data extracts.
- In a repo other people use, changes go in through its review process,
  not straight to the main branch.
- Keep work in progress in a worktree under `.claude/worktrees/`, one
  session per worktree, and push its branch before leaving it.
- Do not move or rename the repo, and keep `project.yaml` true when the
  project changes.
<!-- project-guide:base end -->

## This project

This repository is the single source of the memory skills. Every catalog that
offers them references this repository on the `stable` ref; no catalog keeps a
copy. Fix a skill here, never in a consumer.

### Public repository

Everything here is public and generic. Write for "the user" and "the memory
bank". No person, username, host name, bank name, employer, team, or internal
product; no absolute paths from any machine; no real tokens or memory content.
The one exception is this repository's own URL. Anything specific to one
environment (where the service runs, the MCP server's name, the bank, how to
repair the service) belongs to that environment's own plugin or instructions,
which tell the agent what to pass to these skills.

### Layout

- `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`: the manifests.
  Skills are auto-discovered from `skills/`.
- `.claude-plugin/marketplace.json`, `.agents/plugins/marketplace.json`:
  single-plugin catalogs for direct install.
- `skills/<name>/`: `SKILL.md`, `README.md` (maintainer and date),
  `agents/openai.yaml`, and any `scripts/`.
- `references/`: `memory-conventions.md` (backend-neutral rules),
  `capture-criteria.md` (how a source is written), `hindsight-binding.md` (the
  Hindsight tools, which the skills call by name).

### Two harnesses, no hooks

Every skill must work in Claude Code and Codex from the same `SKILL.md`. Refer
to bundled files by paths relative to the skill's directory, add no hooks, and
keep skill bodies short and harness-neutral.

### Scripts

Standard library only, Python 3.9 or newer. Test both 3.9 and a current
Python. Test writes only against a throwaway bank that you delete afterwards,
with `MEMORY_LEDGER_PATH` (or `MEMORY_HOME`) pointing at a scratch folder.
Never point a test at someone's real bank or ledger.

### Releases

Consumers track `stable`. A release bumps `version` in both manifests, tags
`vX.Y.Z`, and advances `stable` to the tag after validation. When to release
is the owner's decision.
