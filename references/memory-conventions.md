# Memory conventions

How every skill in this plugin, and any agent that reads or writes the memory
bank, behaves. This file names no tools; the concrete calls are in
`hindsight-binding.md` next to it. Read the binding after this file.

## 1. Memory is the source of truth for prior work

The memory bank is where facts about the user's work and world live: projects,
people, systems, decisions and their reasons, findings. Chat history and
assumptions are not substitutes. If memory is unreachable, say so and work
without it for the session; never fall back to another store.

## 2. Read before you act

Before non-trivial work that names a project, a person, a system, or a past
decision, read memory first, the way a file is read before it is edited. Skip
the read only when context cannot help: a self-contained question, a purely
mechanical edit, a request already fully specified in the conversation. When
unsure, read; a wasted query is cheap.

## 3. How to read

Reads go from broad to narrow. This is an ordering, not a cap.

1. **State model.** If the bank keeps a standing summary of the subject (a
   state model), read it first. It is a dated snapshot; note its "as of" date.
2. **Recall.** As many scoped queries as the task needs, to cover what moved
   since the snapshot and the specifics a summary compresses away. One query is
   a probe, not a verdict: if a phrasing misses, re-query at a different level
   of abstraction (concrete identifiers, dates, names) before concluding that
   nothing is known.
3. **Synthesis** is the reader's own reasoning over what came back.

## 4. Weigh what you read

Treat every recalled item as evidence of what was true when it was written.
When facts disagree, prefer the dated, specific one over a summary, a state
model, or an older statement. Never let a single uncorroborated hit drive an
irreversible or outward-facing action; corroborate or ask. When exact wording
matters (a quote, a config, a command), open the source document rather than
trusting the recalled summary.

## 5. What gets written

Durable knowledge, written when it lands: a decision and why, a verified
finding, a correction, the user's answer to a question, an open question worth
tracking. Routine one-offs (lookups, mechanical edits) warrant nothing. Never
write guesses or mid-task theories as facts, and never record an exploratory
remark as a decision; record it as an open question or not at all.

Write self-contained statements in your own words: entities named, the reason
included, phrased the way you would want to find them again.

## 6. Data rule

- Never store credentials or secrets: passwords, tokens, keys, connection
  strings, session cookies.
- Never store sensitive or restricted data verbatim: customer data, personal
  data, financial detail. Store the conclusion and a pointer to where the
  source lives (a file path, a system, a document name).

When a source mixes durable knowledge with restricted data, write the
knowledge and leave the restricted data out.

## 7. Provenance

Every fact says where it came from, in the text and in the metadata:

- Who said or decided it ("the user decided on <date> that ...").
- Whether it was **read** (in a document, a page, a message) or **done and
  verified** (a command run, a test passed, a result observed). A claim read
  in a document is weaker than one verified by doing.
- Research the agent gathered from outside sources is marked as such.

Every write sets a short `context` label naming the content and who is
speaking. A correction is a new dated fact that states the new state and what
it replaces (the text may open "CORRECTION (<date>): ..."), never an edit of
history.

## 8. Tags are scopes only

One to three namespaced tags per write (`project:*`, `service:*`, `topic:*`,
`person:*`) saying what the fact is about. Check the tags already in the bank
and reuse their spelling before coining a new one; a scattered tag silently
breaks later scoped reads. Never tag trust, source, kind, or correction;
provenance belongs in the text and metadata.

## 9. Dates

Date a fact by when the information is about, not when it was written. Put
the date in the structured timestamp and in the text. Atemporal reference
material (a spec, documentation) carries neither.

## 10. Confirm the write

Accepting a write is not proof it landed. Confirm load-bearing writes before
reporting success, and never re-submit on a hunch.

## 11. Route by subject

Where more than one bank is connected, a fact goes to the bank for its
subject: facts about the user's world go to the user's bank; facts about an
agent's own operation go to that agent's own bank, if it has one.

## 12. Close the loop

A session that materially changed a subject ends by writing what landed (the
`sweep` skill) before its context is lost. Sessions do not refresh state
models; they name the ones the session left behind.
