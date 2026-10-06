# Source types

## Shared requirements

Use only the selected source unit. Preserve qualifications and distinguish reported statements from uncertain inference. Record the source type and page scope in YAML frontmatter.

## Journal paper

Name the PDF `<Year> <Author(s)> - <Article Title>.pdf`. Classify from the PDF title and section headings. For primary research, set `source_type: paper` and `document_type: primary`; use the existing paper-note schema and journal-article reference lookup.

## Review article

A review PDF may be named `REVIEW - <Year> <Author(s)> - <Article Title>.pdf`, but classification comes from PDF-visible content, not the filename. Set `source_type: review` and `document_type: review`; use [review-extraction.md](review-extraction.md), the Review Note Template, and journal-article reference lookup. Summarize field taxonomy, design paradigms, landmark cited studies, secondary benchmarks, and future directions. Attribute claims and numbers from cited studies to the review's report of those studies, not to new experiments by the review authors. Leave unsupported quantitative or methodological details unstated.

## Textbook chapter

Name the PDF `TEXTBOOK - <Year> <Author> - <Book Title> - Ch <NN> - <Chapter Title>.pdf`, using a two-digit chapter number. Classify from PDF-visible chapter structure rather than the filename: chapter/numbered-section headings, learning objectives, worked examples, chapter summary, end-of-chapter exercises or review questions, or a clearly pedagogical presentation. Set `source_type: textbook-chapter` and `document_type: textbook_chapter`; use [textbook-extraction.md](textbook-extraction.md) and the Textbook Chapter Note Template. Use metadata visible in the PDF and skip reference-manager article lookup. Process one chapter per source package whenever practical.

Present definitions, governing equations, theorems, derivations, worked examples, applications, and self-assessment questions in instructional order. Write mathematical expressions and variables with `$...$` or `$$...$$` LaTeX delimiters. Do not describe textbook exposition as original research or force experimental methods, study limitations, and literature maps into the chapter note.

## Thesis or dissertation chapter

Name the PDF `THESIS - <Year> <Author> - <Thesis Title> - Ch <NN> - <Chapter Title>.pdf`, using a two-digit chapter number. The filename organizes the vault; establish thesis identity and chapter purpose from the PDF. Set `source_type: thesis-chapter`, `document_type: thesis_chapter`, and a required `thesis_subtype`. Use PDF-visible metadata and skip reference-manager article lookup. Process one chapter per source package whenever practical.

Use [thesis-chapter-extraction.md](thesis-chapter-extraction.md) for the four subtypes: an introduction or literature review with thesis objectives/specific aims; a methodology or theory chapter with custom apparatus, protocols, or derivations; a research-body chapter with results, figures, analysis, and discussion; or a synthesis/conclusion chapter with cumulative contributions and future directions. Each reuses the appropriate review, textbook, or primary template with a thesis-specific addition, except synthesis/conclusion, which has its own template. If the subtype cannot be established from the chapter, inspect further rather than guess. Identify dependencies on other chapters without attributing unexamined results to this one.

## Complete thesis

Name a complete thesis PDF `THESIS - <Year> <Author> - <Thesis Title>.pdf` and set `source_type: thesis`. Use only when explicitly requested and when the complete document can be read adequately; otherwise split it into chapter files following the thesis-chapter pattern. Do not run reference-manager article lookup. Summarize:

- Thesis-level research problem
- Chapter structure
- Methods by study or chapter
- Major findings by chapter
- Cross-chapter conclusions
- Contributions
- Stated limitations
- Future work
- Relevance to the user’s research

If coverage becomes incomplete because of document length, stop and recommend chapter-level processing instead.
