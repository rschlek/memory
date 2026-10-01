---
name: sweep
description: >-
  Seal the current session before its context is lost, at close or before a
  compaction: retain durable knowledge not yet in memory, write in-flight state
  to files, and give the all-clear. Use when the user says "sweep",
  "checkpoint", "let's wrap", "save what we did", "am I safe to compact?", or
  "anything to save before I go?". Not for handing work to another agent or
  session, and not for saving one specific item (remember).
---

# Sweep

Paths below are relative to this skill's directory. Read
`../../references/memory-conventions.md` and
`../../references/hindsight-binding.md` first.

A closed or compacted session keeps nothing. Before that moment, durable
knowledge that exists only in the conversation goes to memory, and anything
future work needs goes to a file. Invoking this skill is the approval to
retain; do not ask item by item.

## Procedure

1. **Retain what landed.** Walk the conversation for settled decisions with
   their reasons, verified findings, corrections, the user's answers, and open
   questions worth tracking. Retain each one whole, with its reason and
   evidence, not a one-line summary:
   - dated by when it is about, with the date in the text too;
   - `context` naming the content and who is speaking;
   - provenance in the text and `metadata`: who decided it, and whether it was
     read in a document or done and verified; a correction says what it
     replaces;
   - 1-3 scope tags checked against `list_tags`;
   - the right bank, if more than one is connected (conventions section 11).

   Apply the data rule: no credentials or secrets, and no customer data,
   personal data, or financial detail verbatim. Retain only what was
   explicitly settled as a decision; record leanings as open questions or not
   at all. Skip what is already retained this session or already recorded in
   files or version control. A slow bank still accepts writes; if a `retain`
   call itself errors, follow the binding's "When memory is down" section.

2. **Write in-flight state to files.** An unsaved plan, a half-built design, a
   working list: write it to a suitable file and say where.

3. **Name what is now behind.** If the bank keeps state models, list the ones
   whose subject this session materially changed. Do not refresh them.

4. **Give the all-clear.** One short summary: what was retained (with
   operation ids), what was written where, which state models are behind, and
   the verdict, "safe to compact" or "clean to close". `accepted` means
   queued; confirm with `get_operation` only for a write that something
   depends on. "Nothing to save" is a fine outcome.
