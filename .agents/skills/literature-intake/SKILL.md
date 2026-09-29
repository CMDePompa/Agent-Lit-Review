---
name: literature-intake
description: Inspect the literature Inbox; summarize journal papers, reports and prefixed review articles, textbook chapters, or theses into Obsidian notes; or attach an exact-matched supplementary PDF to an existing article note.
---

# Literature intake

Work from this project root. Process at most one PDF per invocation unless the user explicitly requests more. For an inspection request, run `python scripts/literature_intake_io.py inspect`, report the waiting filenames, and make no changes. For “next paper,” choose the first name in that sorted output. An empty Inbox means no file changes.

For new processing, read [note-schema.md](references/note-schema.md) and [research-context.md](references/research-context.md). Resolve the requested path inside `PDFs/Inbox`. Name the note from the PDF's source stem, so its destination is known before PDF reading. Pair only an exact `SI - <primary filename>` supplement. Run `python scripts/literature_intake_io.py check "PDFs/Inbox/<file>.pdf" "<source stem>"` before reading, adding `--supplementary-pdf "PDFs/Inbox/SI - <file>.pdf"` when the exact pair exists. For a new note, stop on any existing note, record, or same-name PDF in `PDFs/Ingested`. Never overwrite an existing note or human-owned section. If the user asks to add a separated SI to a previously processed paper, follow [si-attachment.md](references/si-attachment.md).

Use Codex’s PDF-reading capability and the model selected for this Codex task to examine the paper itself. Read methods, results, discussion, conclusions, figure captions, and stated limitations when available; the abstract alone is insufficient. Do not search the web, consult outside knowledge, infer findings from the filename. If enough of the PDF cannot be read, stop with the original PDF untouched. Do not extract or save figure images. During new-paper summarization, do not read any other PDF, previously generated literature note, or prior processing record. For the separated-SI attachment workflow only, read the selected existing note solely to preserve it and make the targeted update; derive all new scientific claims from the SI itself.

Before reading, read [source-types.md](references/source-types.md), classify the source as `paper`, `review`, `textbook-chapter`, `thesis-chapter`, or `thesis`, and apply the corresponding guidance.

For a complete thesis, prefer chapter-level processing followed by a separate thesis-synthesis task. Do not create the thesis synthesis from memory accumulated across chapter-processing tasks.

Draft a note using the schema reference and the existing `Literature Notes/Templates/Literature Note Template.md`. Validate the claims against the PDF package, then save the draft to a temporary Markdown file. Run `python scripts/literature_intake_io.py commit "PDFs/Inbox/<file>.pdf" "<source stem>" "<draft file>"` to validate and write the note, put Obsidian links for the primary PDF and any paired SI in the `pdf` property, record provenance, and then move the package. Do not add separate PDF links in the note body. Add the same `--supplementary-pdf` path used by `check` when paired SI exists, and add `--no-move` when requested. For journal articles, including `review`, include `--metadata-lookup-file "<lookup.json>"` so Zotero match method, item key, export date/age, and metadata warnings are recorded. Pass the accumulated warning list with `--warnings-json`. If processing fails, report the reason and leave every original package PDF in Inbox.

Extract scientific content only from the selected PDF package. For journal articles, follow [zotero-metadata.md](references/zotero-metadata.md) to verify bibliographic metadata against `data/zotero-export.json`. If the export is missing or unreadable, stop article intake before note creation or file movement and report that metadata retrieval is unavailable. If the export is readable but has no confident match, continue intake using only metadata clearly visible in the PDF; leave uncertain fields empty, set `metadata_review_needed: true`, and record the lookup warnings. A matched stale export may be used with a visible warning and metadata review flag. Skip Zotero lookup for `SI - ` PDFs, textbooks, and theses. Never consult the web, Crossref, publisher pages, or external APIs.

## Source packages and supplementary information

One task processes one source package. A source package consists of:

- One primary scientific article PDF, including a `REVIEW - ` article
- Zero or one supplementary-information PDF associated with that article

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

If a filename begins with `SI - ` but its primary article is not present in Inbox, check for the exact primary filename in `PDFs/Ingested`. When that PDF and its existing note are present, use [si-attachment.md](references/si-attachment.md) if the user asks to add the separated SI. If the parent is in neither location, classify the SI as orphaned: do not summarize, move, or delete it. Report the orphan and continue only if another valid primary source can be selected without exceeding the one-source-package limit.

Use the primary article for bibliographic metadata. Use supplementary information to clarify methods, equations, parameter values, controls, additional results, uncertainty, and supporting figures or tables.

Clearly identify whether a statement is supported by:

- The primary article
- The supplementary information
- Both files

Preserve supplementary figure and table labels exactly, such as `Figure S3` or `Table S2`. Do not silently present an SI-only result as a main-text result.

If either file cannot be read sufficiently, report the problem. Do not create the note or move either file unless the source package can be processed defensibly.
