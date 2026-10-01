---
name: learn
description: >-
  Research a topic and save the synthesis to the user's memory bank, marked as
  research the agent gathered. Use when the user says "learn about X",
  "research X and remember it", or "find out about X and add it to memory", or
  when durable knowledge on a subject is needed and no document exists for it.
  Not when the user hands over a specific source (remember), and not for tasks.
---

# Learn

Paths below are relative to this skill's directory. Read
`../../references/capture-criteria.md` first. The user gives a topic, not a
document; you gather, synthesize, and write one document.

## Flow

1. **Probe memory first.** Make one cheap call (`list_tags`). If memory is
   down, say so before spending effort on research. If the user wants the
   research anyway, write it to a file they agree on and note that it still
   needs to be retained.

2. **Check what is known.** A `recall` on the topic; research the gap rather
   than re-deriving what memory already holds.

3. **Gather.** Use only the sources that fit: the web for external or current
   topics, local files for material the user already has, a codebase for "how
   does this project do X", and a connected documentation-lookup tool, when
   there is one, for a specific library or API. If the harness supports
   subagents, research independent sub-questions in parallel. Each research
   agent is costly and a wide fan-out burns a large budget fast: a few agents
   cover most topics, so say how many you will launch before starting, and go
   wider only when the user asks.

4. **Synthesize and show it.** One coherent synthesis: contradictions
   resolved, primary sources preferred, thin evidence called thin. Showing it
   to the user is the checkpoint. Write it to be read cold: canonical names,
   specifics exact, only dates the material states.

5. **Write it in one call** (criteria sections 4 and 5):
   - `context`: an external-research label, for example `"agent research
     synthesis (external web sources)"`.
   - `metadata`: `{"source": "agent-research", "source_detail": "<same
     label>"}`. This keeps researched claims distinguishable from the user's
     own.
   - `document_id`: `research-<topic-slug>`.
   - `tags`: one `topic:*` tag plus any `project:*` or `service:*` tag the
     subject serves, three at most, reused from `list_tags`.
   - no `timestamp`; research is usually atemporal.
   - In the text, signal outside provenance where it matters ("According to
     the official documentation, ...").
   Apply the data rule to anything the research turned up.

6. **Confirm and report.** `get_operation` until `completed` (or
   `list_documents`), then one line: the topic, the sources drawn on, and how
   many memory units it produced.
