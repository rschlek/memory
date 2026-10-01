# Runtime binding: Hindsight

The concrete backend behind `memory-conventions.md`:
[Hindsight](https://hindsight.vectorize.io). The skills call these tools by
name, so another backend would mean revising the skills as well as this file.

## Service

- The agent reaches the bank through a Hindsight MCP server that the
  environment registers. Where that server runs, what it is called, and how it
  authenticates are the environment's business (its own setup or global
  instructions say so), not this plugin's.
- The bank is bound by the server (a single-bank endpoint or a server-side
  binding), so no call below takes a bank argument.
- Tool names below are the plain names. A harness or a gateway may show them
  with a prefix (for example `mcp__<server>__recall`, or `hindsight-recall`);
  use whatever form the session lists.

## Tools the skills use

| purpose | tool | parameters used |
|---|---|---|
| read | `recall` | `query` (required), `tags`, `tags_match`, `types`, `max_tokens` |
| check tag spelling | `list_tags` | `q`, `limit` |
| open a source | `get_document` | `document_id` |
| find a document | `list_documents` | `q`, `limit` |
| find a state model | `list_mental_models` | `tags`, `limit` (it returns metadata only) |
| read a state model | `get_mental_model` | `mental_model_id`, `detail` (`"content"`) |
| write | `retain` | `content` (required), `context`, `timestamp`, `tags`, `metadata`, `document_id` |
| confirm a write | `get_operation` | `operation_id` |
| look at queued writes | `list_operations` | `status`, `limit` |

Notes on these calls:

- `recall`: `tags_match` `"any"` (the default) also returns untagged
  memories; `"any_strict"` hides them. `types` narrows to `world`,
  `experience`, or `observation` facts. `observation` facts are syntheses the
  service derives from several facts; `world` and `experience` facts sit
  closer to the source. On conflict, prefer the dated specific fact.
- State models are Hindsight mental models: a saved answer to one standing
  question, re-synthesized by the service. A bank may have none; then skip
  them. Read the "as of" date in the model's text; the model is a snapshot.
- `retain` is queued: it returns `accepted` with an `operation_id`, and the
  content is not recallable until extraction finishes. `metadata` is a
  string-to-string map and is not filterable on recall, so anything you need
  to search by goes in the text or the tags. The same `document_id` replaces
  the earlier document.
- `get_operation` reports `pending`, `completed`, or `failed`.
  `list_documents` shows a document with its memory unit count once it has
  committed, and can lag behind the operation status.

## Tools the skills do not use

The server may expose more tools than the skills need. Do not call these from
a skill or in ordinary work:

- `reflect`, and creating, updating, refreshing, or deleting mental models,
  directives, or knowledge pages. Synthesis is the session's own reasoning.
- Destructive or administrative tools: `delete_document`, `delete_bank`,
  `clear_memories`, `update_memory`, `invalidate_memory`, `update_bank`,
  `cancel_operation`. Call one only when the user explicitly asks for that
  exact action on named items.
- `sync_retain` blocks until extraction finishes; prefer `retain` and confirm
  with `get_operation`.

## When memory is down

Memory is down when the memory tools are missing from the session, or when a
call fails with a connection error, an authentication error, or a timeout.
Tell the user, follow the environment's own instructions for checking or
repairing the service, and note that a new session may be needed before the
tools reappear. Then work without memory reads for the session.

Slow is not down. Extraction can take minutes; an operation that stays
`pending` is still queued, and a slow bank still accepts writes. If a `retain`
call itself errors, do not drop the content: append it verbatim (tags,
context, timestamp, metadata, and content) to
`retains-owed-<YYYY-MM-DD>.md` in the memory folder (the `MEMORY_HOME`
environment variable, default `~/.agent-memory`), tell the user, and retain it
once memory is back.
