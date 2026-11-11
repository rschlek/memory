# Agent guidance

<!-- playbook:base start (1.0.1) -->
## Working in this repo

This repo follows the playbook standard, version 1.0.1
(https://github.com/rschlek/playbook). This block is replaced when the
standard updates; put project-specific guidance in the section below it.

- Read `README.md` and `project.yaml` first: what this is, who it is for,
  and where related things live.
- Before changing `project.yaml`, `README.md`, `AGENTS.md`, `CLAUDE.md`, or
  the repo's layout, read `docs/project-conventions.md` and keep to it.
- Make one change for one purpose, and run the checks this repo documents
  before proposing it.
- Commit only the files you changed, by path. Never commit credentials,
  tokens, or data extracts.
- If `project.yaml` says `visibility: public`, anyone can read this repo:
  write no person, employer, team, host, or machine names into it.
- If it says `visibility: internal`, everyone in the organization that
  hosts this repo can read it: the organization's own names are fine,
  other people's personal details are not.
- The repo holds the project's own context; the tracker holds its work.
  A plan lives in its parent ticket, never in a file. Each decision is
  one file in `docs/decisions/`; research is a dated file under `docs/`.
  Write records for a reader who opens the project cold, and in a shared
  project (`shared: true`, or `visibility` set) show the user the exact
  text before writing one.
- Read and write tickets the way the tracker doc says: `docs/tracker.md`
  when present, else the user's own doc for the tracker `project.yaml` or
  the profile names. A ticket's status lives only in its tracker; never
  copy tickets between trackers, and never track progress in a document.
  Read `docs/project-conventions.md` before writing or moving anything
  under `docs/`, and leave existing documents as they are.
- The flow, each step a playbook skill: sharpen the idea (`grill-me`); if
  it is foggy, map its open questions (`wayfinder`, answering them with
  `research`, `prototype`, `grill-me`); plan and file the work
  (`to-tickets`); do each ticket (`tackle`); close the parent. Skip steps
  already clear. Any time: `capture` a stray item, `untangle` when lost,
  `next` when unsure what comes next.
- In a repo other people use, changes go in through its review process,
  not straight to the main branch.
- Keep work in progress in a worktree under `.claude/worktrees/`, one
  session per worktree, and push its branch before leaving it.
- Do not move or rename the repo, and keep `project.yaml` true when the
  project changes.
<!-- playbook:base end -->

## This project

This repository is the single source of the memory skills. Every catalog that
offers them references this repository on the `stable` ref; no catalog keeps a
copy. Fix a skill here, never in a consumer.

### Public repository

Everything here is public and generic. Write for "the user" and "the memory
bank". No person, username, host name, bank name, employer, team, or internal
product; no absolute paths from any machine; no real tokens or memory content.
The exceptions are the `author` field in the plugin manifests (and the owner
of the single-plugin catalog) and this repository's own URL. Anything specific
to one environment (where the service runs, the MCP server's name, the bank,
how to repair the service) belongs to that environment's own plugin or
instructions, which tell the agent what to pass to these skills.

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
