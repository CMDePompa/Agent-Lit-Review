---
name: literature-intake
description: Inspect the literature Inbox; summarize journal papers, reports and prefixed review articles, textbook chapters, or theses into Obsidian notes; or attach an exact-matched supplementary PDF to an existing article note.
---

# Literature intake

Work from this project root. Process at most one source package per invocation unless the user explicitly requests more. For an inspection request, run `python scripts/literature_intake_io.py inspect` and report `eligible`, `needs_attention`, and `already_processed` filenames. Inspection may clear failure flags for PDFs that were edited, replaced, or removed; it does not create notes or move PDFs. For “next paper,” choose the first name in the sorted `eligible` list. If that list is empty, report any flagged packages and stop without changing a source PDF. Never select an `SI - ` file or a successfully processed PDF left in Inbox as a new primary source.

For new processing, read [note-schema.md](note-schema.md) and [research-context.md](research-context.md). Resolve the requested path inside `PDFs/Inbox`. Name the note from the PDF's source stem, so its destination is known before PDF reading. Pair only an exact `SI - <primary filename>` supplement. Run `python scripts/literature_intake_io.py check "PDFs/Inbox/<file>.pdf" "<source stem>"` before reading, adding `--supplementary-pdf "PDFs/Inbox/SI - <file>.pdf"` when the exact pair exists. For a new note, stop on any existing note, record, or same-name PDF in `PDFs/Ingested`. Never overwrite an existing note or human-owned section. If the user asks to add a separated SI to a previously processed paper, follow [si-attachment.md](si-attachment.md).

Use Codex’s PDF-reading capability and the model selected for this Codex task to examine the source itself. For research articles, read methods, results, discussion, conclusions, figure captions, and stated limitations when available; the abstract alone is insufficient. For textbook chapters, read the exposition, definitions, equations, derivations, examples, applications, and exercises. Do not search the web, consult outside knowledge, or infer findings from the filename. If enough of the PDF cannot be read, stop with the original PDF untouched. Do not extract or save figure images. During new-source summarization, do not read any other PDF, previously generated literature note, or prior processing record. For the separated-SI attachment workflow only, read the selected existing note solely to preserve it and make the targeted update; derive all new scientific claims from the SI itself.

Before drafting, read [source-types.md](source-types.md). Inspect the PDF-visible title, full section-heading list, and relevant chapter features. Write a classification JSON in `data/tmp/` containing `title` and `section_headings`. Set `is_thesis_chapter: true` only when the PDF identifies itself as part of a thesis or dissertation; include its `chapter_number` and short `chapter_text_signals` observed in the chapter when useful. Set `has_end_of_chapter_exercises` or `pedagogical_structure` only when established by the PDF. Run `python scripts/literature_intake_io.py classify-document "data/tmp/<classification.json>"`. Copy its `document_type`, `source_type`, and, for thesis chapters, required `thesis_subtype` into the draft. Thesis subtype selection considers chapter title, aims, methods/theory, results, cumulative contributions, and future directions; if unclear, inspect further before drafting. For other documents, pedagogical structure selects `textbook_chapter`, review phrases or a complete article without a methods section select `review`, and uncertainty defaults to `primary`. An incomplete heading list does not establish that methods are absent. Classify from the PDF, not its filename. A complete thesis remains a separate `source_type: thesis` workflow.

For a complete thesis, prefer chapter-level processing followed by a separate thesis-synthesis task. A `synthesis_conclusion` chapter note must come from that selected chapter itself, not memory accumulated across chapter-processing tasks.

For `document_type: primary`, use [note-schema.md](note-schema.md) and `Literature Notes/Templates/Literature Note Template.md`. For `review`, use [review-extraction.md](review-extraction.md) and `Literature Notes/Templates/Review Note Template.md`. For `textbook_chapter`, use [textbook-extraction.md](textbook-extraction.md) and `Literature Notes/Templates/Textbook Chapter Note Template.md`, writing mathematics with `$...$` or `$$...$$` LaTeX notation. For `thesis_chapter`, follow [thesis-chapter-extraction.md](thesis-chapter-extraction.md): `intro_literature_review` extends the review template with Thesis Scope & Specific Aims, `methodology_theory` extends the textbook template with Custom Setups & Key Protocols, `research_body` extends the primary template with Mapped Thesis Aim, and `synthesis_conclusion` uses `Literature Notes/Templates/Thesis Synthesis Note Template.md`. Pass the classification JSON to commit with `--classification-file "data/tmp/<classification.json>"` so the helper checks the selected route and deletes the temporary file after success.

Draft a note using the selected schema and template. Put every scratch artifact—draft, classification JSON, reference request/result, warnings, extracted text, and SI update files—inside `data/tmp/`; never create temporary intake records elsewhere. Validate the claims against the PDF package, then run `python scripts/literature_intake_io.py commit "PDFs/Inbox/<file>.pdf" "<source stem>" "data/tmp/<draft file>" --classification-file "data/tmp/<classification.json>"` for a classified source; omit `--classification-file` for an explicitly requested complete thesis. Commit validates and writes the note, puts Obsidian links for the primary PDF and any paired SI in the `pdf` property, records provenance, moves the package, and deletes declared temporary files after success. Do not add separate PDF links in the note body. Add the same `--supplementary-pdf` path used by `check` when paired SI exists, and add `--no-move` when requested. For journal articles only, include `--metadata-lookup-file "data/tmp/<lookup.json>"` to record reference-manager match details. Pass warnings with `--warnings-json-file "data/tmp/<warnings.json>"` and pass other scratch files, such as the reference request, with a repeated `--temporary-file "data/tmp/<file>"`; successful commit deletes all of them. If the selected source cannot be processed at any stage, leave every original package PDF in Inbox and run `python scripts/literature_intake_io.py defer "PDFs/Inbox/<file>.pdf" "<specific reason and action needed>"`. Report the failure and stop this invocation; later “next paper” runs skip that package. Do not mark a user-cancelled request as a source failure. When the user asks to retry a flagged file after fixing its issue, run `python scripts/literature_intake_io.py retry "PDFs/Inbox/<file>.pdf"` before processing it. A changed PDF is requeued automatically on inspection; resolving the final flag deletes the temporary failure-state file.

Extract scientific content only from the selected PDF package. For journal articles, follow [reference-metadata.md](reference-metadata.md) to verify bibliographic metadata with Zotero or Mendeley. Configured reference-manager APIs may be used only for bibliographic lookup; do not consult the web, Crossref, publisher pages, or unrelated APIs. When an API is configured, run the actual lookup with network-enabled command execution. If a restricted command reports an API `URLError` and falls back to a local export, retry that lookup with escalated network permission before accepting the export result. Confirm an API match has `export_path: null`; `--check-source` alone never verifies API access. If no confident match is available, use only metadata clearly visible in the PDF, set metadata_source: "PDF" and metadata_review_needed: true, leave uncertain fields empty, and record the lookup warnings. A matched stale export may be used with a visible warning and metadata review flag. Skip reference lookup for SI PDFs, textbooks, and theses.

## Source packages and supplementary information

One task processes one source package. A source package consists of:

- One primary source PDF: a research article, review article, textbook chapter, or thesis unit
- Zero or one supplementary-information PDF when the source is a journal article

A supplementary-information filename begins with the exact prefix `SI - `. Its corresponding primary article has the identical filename after that prefix is removed.

Example:

- Primary: `Example Article.pdf`
- Supplement: `SI - Example Article.pdf`

Supplementary-information PDFs are not independent Inbox items. When choosing the next source in sorted order:

1. Exclude filenames beginning with `SI - ` from the primary-source queue.
2. Select the first eligible primary source.
3. Look for an exact supplementary match named `SI - <primary filename>`.
4. If found, treat both files as one source package and read both during the same task.
5. If not found, process the primary source alone.
6. Never attach supplementary information using fuzzy title matching.

If a filename begins with `SI - ` but its primary article is not present in Inbox, check for the exact primary filename in `PDFs/Ingested`. When that PDF and its existing note are present, use [si-attachment.md](si-attachment.md) if the user asks to add the separated SI. If the parent is in neither location, classify the SI as orphaned: do not summarize, move, or delete it. Report the orphan and continue only if another valid primary source can be selected without exceeding the one-source-package limit.

Use the primary article for bibliographic metadata. Use supplementary information to clarify methods, equations, parameter values, controls, additional results, uncertainty, and supporting figures or tables.

Clearly identify whether a statement is supported by:

- The primary article
- The supplementary information
- Both files

Preserve supplementary figure and table labels exactly, such as `Figure S3` or `Table S2`. Do not silently present an SI-only result as a main-text result.

If either file cannot be read sufficiently, report the problem. Do not create the note or move either file unless the source package can be processed defensibly.
