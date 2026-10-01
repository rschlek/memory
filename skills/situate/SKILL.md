---
name: situate
description: >-
  Load what memory already holds about a project, problem, or person before
  resuming work on it, and hand back one situation brief so a fresh session
  picks up where the last one left off. Use when a session starts on an
  ongoing project, service, or person (self-invoke, unprompted), or when the
  user says "situate yourself", "get up to speed on X", "where did we leave X",
  "what do we already know about X", or "catch me up on X". Not for a quick
  lookup of one fact (use the recall tool), for saving something (remember),
  or for researching a new topic (learn).
---

# Situate

Paths below are relative to this skill's directory. Read
`../../references/memory-conventions.md` and
`../../references/hindsight-binding.md` first.

Reconstruct what is already known so work resumes mid-stream instead of from
scratch. This skill reads; it never writes to memory.

## Procedure

1. **Frame the situation.** From the conversation, write a short spec: the
   problem in a line or two, and the questions memory must answer (what was
   decided and why, current state, what is open, what must not be done). The
   spec keeps every later read on target.

2. **State model, if there is one.** If the bank has a state model for the
   subject (`list_mental_models`), read it first (`get_mental_model`) and note
   its "as of" date. It is a snapshot; a dated specific fact beats it. If the
   bank has none, go on.

3. **Find the real tags.** Run `list_tags` (filter with `q`) and note the tags
   that exist for this subject. A guessed tag returns an empty recall that
   looks exactly like "nothing is known".

4. **Recall, as many times as the spec needs.** Scope recalls with the real
   tags. Cover each question in the spec, what moved since the state model's
   date, the user's own decisions and corrections (found by text, for example
   "the user decided" or "CORRECTION"), and anything recent. If a phrasing
   misses, re-query with concrete names, identifiers, or dates. When the
   subject is wide and the harness supports subagents, readers can run recalls
   in parallel and return quoted evidence with dates, not verdicts. Have them
   lean inclusive, say what they could not find, and keep raw recall payloads
   to themselves so only cited findings reach the main context.

5. **Other sources, only if the spec needs them.** The repository, working
   files, or a tracker for open items.

6. **Write the brief.**
   - **Goal**: what we are doing and why.
   - **Guardrails**: what must not be done, first.
   - **Decisions so far**: each with its reason and date.
   - **Current state**: where things stand, with the date of the newest fact.
   - **Open questions and next steps.**
   - **Gaps and conflicts**: thin spots, and facts that disagree (the newer
     dated fact usually wins; flag it, do not silently pick).

   For anything that will drive a decision, open the source with
   `get_document` rather than trusting a recalled summary.

7. **Confirm, then resume.** Present the brief briefly, raise conflicts and
   gaps for the user, and continue the work.

When the session ends, `sweep` writes back what landed.
