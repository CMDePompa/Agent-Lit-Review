# Source types

## Shared requirements

Use only the selected source unit. Preserve qualifications and distinguish reported statements from uncertain inference. Record the source type and page scope in YAML frontmatter.

## Journal paper

Name the PDF `<Year> <Author(s)> - <Article Title>.pdf`. Set `source_type: paper`; use the paper-note schema and journal-article Zotero lookup.

## Review article

A review PDF is named `REVIEW - <Year> <Author(s)> - <Article Title>.pdf`. Set `source_type: review`; use the paper-note headings and journal-article Zotero lookup. Summarize its scope, how the authors selected or organized prior work when stated, areas of agreement and disagreement, and conclusions. Attribute findings from cited studies to the review's report of those studies, not to new experiments by the review authors. Leave unsupported quantitative or methodological details unstated.

## Textbook chapter

Name the PDF `TEXTBOOK - <Year> <Author> - <Book Title> - Ch <NN> - <Chapter Title>.pdf`, using a two-digit chapter number. Set `source_type: textbook-chapter` and use metadata visible in the PDF; do not run Zotero article lookup. Process one chapter per source package whenever practical.

Emphasize:

- Chapter purpose and scope
- Central concepts and definitions
- Governing theories, models, and equations
- Assumptions and applicability
- Important examples
- Connections to the user’s research
- Figures, tables, or diagrams worth reviewing
- Topics requiring further reading

Do not describe textbook exposition as original research. Replace paper-specific sections such as “Research Question,” “Key Findings,” and “Authors’ Stated Limitations” with:

- Chapter Scope
- Core Concepts
- Models and Equations
- Assumptions and Limitations
- Important Examples
- Relevance to My Research

## Thesis or dissertation chapter

Name the PDF `THESIS - <Year> <Author> - <Thesis Title> - Ch <NN> - <Chapter Title>.pdf`, using a two-digit chapter number. Set `source_type: thesis-chapter` and use metadata visible in the PDF; do not run Zotero article lookup. Process one chapter per source package whenever practical.

First identify the chapter type:

- Introduction or literature review
- Methods
- Results
- Discussion
- Conclusions

Emphasize the chapter’s role within the thesis, its specific methods or claims, dependencies on other chapters, and any statements that cannot be evaluated from the selected chapter alone.

Do not attribute thesis-wide conclusions to one chapter unless that chapter explicitly states them.

## Complete thesis

Name a complete thesis PDF `THESIS - <Year> <Author> - <Thesis Title>.pdf` and set `source_type: thesis`. Use only when explicitly requested and when the complete document can be read adequately; otherwise split it into chapter files following the thesis-chapter pattern. Do not run Zotero article lookup. Summarize:

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
