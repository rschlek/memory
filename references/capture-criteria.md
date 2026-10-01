# Capture criteria

The `remember` and `learn` skills read this file. It defines what you hand to
memory and how. The call shapes are in `hindsight-binding.md`.

The memory service does its own chunking, fact extraction, and consolidation
on whatever text it receives. Your job is to produce one clean, complete
document and pass it in a single `retain` call. Do not decompose it into
hand-written summaries.

## 1. One source, one call

A meeting transcript goes in as the transcript; a research synthesis goes in
as the synthesis. Splitting a source into many small summaries costs more calls
and adds no coverage. Split only when one file genuinely holds unrelated
documents; each then gets its own call and its own `document_id`. Length alone
is not a reason to split.

A short fact the user dictates ("remember that ...") is the same call with a
self-contained statement as the content.

## 2. Preparing the text

1. **Apply the data rule first** (`memory-conventions.md` section 6). Remove
   credentials and secrets. If the source carries customer data, personal
   data, or financial detail, do not hand it over verbatim: write the
   conclusions and a pointer to where the source lives, and tell the user you
   did so.
2. **Complete.** Keep every durable fact. Strip only scaffolding that carries
   none: cue numbers and timestamps in a transcript, page furniture in a PDF.
3. **Faithful.** Do not round or paraphrase specifics. Numbers, dates,
   versions, identifiers, and proper names survive exactly.
4. **Structure-preserving.** Keep `Speaker: text` attribution and headings;
   they help extraction.
5. **Known distortions noted once.** If an auto-transcript mangles names, say
   so in a short lead-in line instead of silently correcting every instance.
6. **Nothing invented.** Never add claims the source does not support.
7. **Plain text.** For a tabular record, write `Field: value` lines, not raw
   JSON.

## 3. Which date

Stamp the capture with the date the information is about, not the date you
ingest it.

- **Event-anchored** (a meeting, an email, any dated record): infer the date
  from the content or header, make sure it appears in the text, and pass it as
  `timestamp`. If it is genuinely absent, ask one question: "What date was
  this?"
- **Atemporal reference** (a spec, documentation, a research briefing): omit
  `timestamp` and never ask for a date.

## 4. Provenance

- `context` (required, never "general"): a short label naming what the content
  is and who is speaking, for example `"project meeting transcript,
  2025-03-11"` or `"product spec sheet (user-supplied document)"`.
- `metadata`: `{"source": "<same label>"}`, plus `"stated_by": "<name>"` when
  the content is a named person's own words, and `"kind": "correction"` when
  it replaces something captured earlier.
- In the text: attribute claims whose weight depends on it ("According to the
  planning meeting, ..."), and say whether something was read in a document or
  done and verified. For a verbatim source the lead-in line carries the
  attribution; do not rewrite the body to add it.

## 5. The `retain` call

| arg | value |
|---|---|
| `content` | the prepared text. Required. |
| `context` | the provenance label (section 4). |
| `timestamp` | ISO-8601 date the information is about. Omit for atemporal sources. |
| `document_id` | a stable key such as `<source-slug>-<date>`. The same id replaces the earlier document, so keep ids distinct across sources. |
| `tags` | 1-3 scope tags, reused from `list_tags`. |
| `metadata` | string-to-string map with the provenance (section 4). |

Leave `strategy` and `update_mode` unset.

## 6. Confirm before reporting

`retain` returns `accepted` with an `operation_id`; extraction runs afterwards
and can take minutes on a long document. Confirm with `get_operation` (status
`completed`) or `list_documents` (the document appears with a memory unit
count; the listing can lag the operation). Report what you confirmed, not what
you sent. Re-submit only after the operation reports `failed`.

## 7. Example

The user hands over an auto-transcript of a meeting held on 2025-03-11.
Normalize it (strip cue numbers and timestamps, keep every `Speaker: text`
line), then make one call:

- `content`: a lead-in naming the meeting and its date and flagging any name
  mangling, then the full transcript
- `context`: `"project meeting transcript, 2025-03-11"`
- `metadata`: `{"source": "project meeting transcript, 2025-03-11"}`
- `timestamp`: `"2025-03-11T12:00:00Z"`
- `document_id`: `"planning-meeting-2025-03-11"`
- `tags`: `["project:example"]`
