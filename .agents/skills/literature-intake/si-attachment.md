# Attach a separated supplementary PDF

Use this workflow when the user asks to add or retry supplementary information after its primary paper has already been processed, or when the exact primary and SI files were separated between intake runs.

## Eligibility and checks

- Pair only when the SI filename is exactly `SI - <complete primary PDF filename>`.
- The primary PDF may be directly inside `PDFs/Inbox` or `PDFs/Ingested`. Its corresponding existing note and processing record must both exist. Do not create a separate SI note.
- The existing note must be for a journal paper, point to that exact primary PDF, have `source_file_count: 1`, and have no supplementary PDF or `Supplementary Information Used` section already attached.
- Before reading the SI, run `python scripts/literature_intake_io.py check-supplementary "<primary path>" "PDFs/Inbox/SI - <primary filename>"`. Stop on any collision or mismatch.
- Read the selected SI itself. Do not use a previous note or processing record as scientific evidence. Read the existing note only to preserve it and to replace any now-obsolete generated statement about that SI; keep `My Notes`, `Figure Screenshots`, and `Connections to Other Papers` byte-for-byte unchanged.

## Update

Draft one `## Supplementary Information Used` section with these exact fields:

- **File:** Exact SI filename
- **Material consulted:** Sections, figures, tables, equations, or pages read
- **Important contributions to this note:** SI-supported clarifications, methods, parameters, results, and qualifications; label SI-only claims as supplementary evidence

Prepare the section draft and update JSON inside `data/tmp/`. The helper deletes both after a successful attachment. The update JSON contains `summary_scope`, `page_scope`, and optional exact text replacements for obsolete generated wording, for example:

```json
{
  "summary_scope": "Entire primary paper and paired supplementary information",
  "page_scope": "Journal pagination 36–40; SI PDF pages 1–10",
  "resolved_provenance_warnings": [
    "Exact earlier warning text that this SI filename did not match the primary."
  ],
  "replacements": [
    {
      "old": "Exact outdated sentence from a generated section.",
      "new": "Updated sentence reflecting the SI review."
    }
  ]
}
```

Each replacement must match exactly once and must not touch a human-owned section. The helper updates `source_file_count`, `supplementary_pdf`, scope fields, the supplementary section, and provenance. It validates that human-owned sections remain unchanged. On success it moves the SI from Inbox to Ingested unless `--no-move` was requested. If any step fails, the helper rolls back note and record changes and leaves the SI in Inbox.

Run:

```text
python scripts/literature_intake_io.py attach-supplementary "<primary path>" "PDFs/Inbox/SI - <primary filename>" "data/tmp/<supplementary-section.md>" "data/tmp/<update.json>"
```

Add `--no-move` when requested. Do not attach an SI that was already incorporated, do not overwrite a prior SI, and do not infer a pairing from similar titles.
