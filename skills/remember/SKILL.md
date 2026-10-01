---
name: remember
description: >-
  Save something to the user's long-term memory bank with its source: a fact
  the user states, a decision, or a document they hand over (meeting
  transcript, PDF, image, pasted report). Invoking it is the decision to
  remember; no per-item approval. Use when the user says "remember that ...",
  "remember this", "save this to memory", "add this to my memory", "log this",
  or "capture this transcript". Not for researching a topic (learn), for
  sealing a whole session (sweep), or for tasks and to-dos.
---

# Remember

Paths below are relative to this skill's directory. Read
`../../references/capture-criteria.md` first; it defines the text, the date,
the provenance, the `retain` call, and how to confirm it. If the memory tools
are not available, stop and say so before doing any work.

## A stated fact or decision

When the user says "remember that ...", write one self-contained statement:
the fact, its reason, who stated it, and its date. Make one `retain` call with
`context` naming the speaker (for example `"the user's decision in a working
session"`), `metadata` `{"source": "...", "stated_by": "..."}`, a timestamp,
and 1-3 scope tags reused from `list_tags`. Apply the data rule. Confirm in one
line.

## A document

1. **Normalize to text.** Text, Markdown, and transcripts (a `.vtt` file
   included) are used directly (strip only cue numbers and timestamps, keep
   every word). Read a PDF's text. For an image,
   write a faithful text description; that is the source text. Save the
   normalized text to a working file.

2. **Apply the data rule** (criteria section 2). If the document carries
   credentials, or customer, personal, or financial detail, retain the
   conclusions and a pointer to where the document lives instead of the
   verbatim text, and tell the user.

3. **Check for a repeat.** Run
   `python scripts/hash_guard.py check --text-file <normalized.txt>`
   (use `--file <path>` for an image or other binary; on Windows, `py -3` if
   `python` is not found). Exit code 3 means this exact source was already
   remembered: tell the user when and under what name, and continue only if
   they say so. The guard only catches identical content; for a source that
   may overlap existing knowledge, a quick `recall` first is cheap insurance.

4. **Resolve the date** (criteria section 3). Event-anchored sources get a
   timestamp, asking once if it is missing; atemporal references get none.

5. **Write it in one call** (criteria sections 4 and 5): the full text opened
   by a one-line lead-in naming the source, its date, and any known
   distortion; a source-attributed `context`; `metadata` with `source`; a
   stable `document_id`; 1-3 scope tags reused from `list_tags`.

6. **Confirm** with `get_operation` on the returned `operation_id` until it
   reports `completed`, or `list_documents`. Do not re-submit unless it
   reports `failed`.

7. **Record the hash, then report.** Only after the write is confirmed:
   `python scripts/hash_guard.py record --text-file <normalized.txt> --name "<short label>"`.
   Recording earlier would block a legitimate retry. Report in one line what
   was captured, its date and source, and how many memory units it produced.

The hash ledger is per computer, at `~/.agent-memory/memory-ledger.jsonl`
(override the folder with `MEMORY_HOME` or the file with
`MEMORY_LEDGER_PATH`). The guard also reads, without changing them, any
`memory-ledger.jsonl` left in a hidden folder directly under the home folder
by an earlier version, so nothing recorded there is forgotten.
