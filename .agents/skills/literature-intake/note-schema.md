# Literature note schema

Use the existing template and database property names. Create one new Markdown note in `Literature Notes/Papers` named from the PDF source stem, which allows collision detection before reading. The filename is never evidence for claims or metadata.

Frontmatter: `title` (string), `parent_title` (string), `authors` (list), `year` (integer or null), `source_type` (string), `source_file_count` (integer), `journal` (string), `doi` (string), `chapter_number` (integer), `chapter_title` (string), `page_scope` (string), `summary_scope` (string), `pdf` (list of Obsidian links, one for the primary PDF and, when present, one for SI), `supplementary_pdf` (relative project path to the SI PDF or null), `research_topics` (list), `methodology` (list), `evidence_type` (list), `polymer_system` (list), `morphologies` (list), `paper_role` (list), `context_summary` (brief string), `metadata_source` (PDF or Zotero export), `zotero_item_key`, `zotero_match_method`, `zotero_export_modified_at`, `zotero_export_age_days`, `summary_status: ai-draft`, `review_status: unread`, `metadata_review_needed` (boolean). The `pdf` links use vault-root paths such as `[[PDFs/Ingested/paper.pdf]]`; the helper sets them after choosing Inbox or Ingested destinations. For articles, use Zotero fields only after a confident match as described in [zotero-metadata.md](zotero-metadata.md). For other source types, use only metadata clearly visible in the PDF and leave Zotero fields blank. Missing or conflicting values, a stale export, or uncertain PDF metadata set `metadata_review_needed: true`.

Populate the six tag lists with short, consistent lowercase kebab-case labels supported by the source. Write them as inline YAML lists of quoted strings, such as `research_topics: ["phase-behavior", "sequence-disorder"]`.

- `research_topics`: scientific questions or subject areas addressed.
- `methodology`: methods, models, or experimental and computational techniques used.
- `evidence_type`: broad evidence basis, such as `analytical`, `computational`, `experimental`, or `review`.
- `polymer_system`: polymer architectures, chemistries, and blends actually studied; leave empty for non-polymer work.
- `morphologies`: named morphologies explicitly studied, predicted, or reviewed.
- `paper_role`: the paper's role in the literature, such as `foundational`, `theory`, `methods`, `experimental`, or `review`.

Use empty lists when a category does not apply or cannot be established; do not force domain-specific tags. `context_summary` is one concise, source-grounded sentence about the work's role or context. For the current polymer research vocabulary and examples, consult [research-context.md](research-context.md).

Start with an AI draft warning. The intake helper places Obsidian wikilinks to the primary PDF and, when present, its SI in the `pdf` property so the Literature Database can display them. Do not add duplicate PDF links to the note body. For a `paper` or `review`, include these exact level-two headings once each; for a review, follow the attribution guidance in [source-types.md](source-types.md):

1. Rapid Summary — brief prose covering question, approach, and central outcome.
2. Research Question — prose or `Not stated.`
3. Methods and System — distinguish method and studied material/system.
4. Key Findings — bullets labeled `Reported result`, `Authors’ interpretation`, or `Uncertain inference` as appropriate. Do not present inference as a finding without a visible warning.
5. Quantitative Results — Markdown table with result, conditions/context, and attribution when meaningful numbers are present; otherwise `Not stated.` Never invent units or precision.
6. Authors’ Stated Limitations — bullets; if none are stated in inspected portions, say so rather than inventing limitations.
7. Relevance to My Research — specific, proportionate assessment; low or indirect relevance is valid.
8. Figures Worth Reviewing — bullets naming figure identifier, relevance, supported finding, and uncertainty. Use `Not stated.` if no recommendation is defensible. Do not extract images.
9. Supplementary Information Used — Include this section only when a paired supplementary-information PDF was actually consulted.
    - **File:** Exact supplementary PDF filename
    - **Material consulted:** Relevant sections, methods, figures, tables, or appendices examined
    - **Important contributions to this note:** Findings, methodological details, parameter values, controls, or qualifications obtained from the supplementary information

If no supplementary PDF was paired with the primary source, omit this section entirely.
10. Suggested Topics — short descriptive bullets grounded in the paper.
11. My Notes — leave blank for the human.
12. Figure Screenshots — leave blank for the human.
13. Connections to Other Papers — leave blank for the human.

For a `textbook-chapter`, use the type-specific headings in [source-types.md](source-types.md) in place of the article-specific headings. For `thesis` and `thesis-chapter`, use the thesis-level or chapter-level outline there. Keep the three human-owned headings in every note.

Optional `Claims to Verify Manually` and `Supporting Evidence` sections may be placed before Suggested Topics. Do not invent page numbers. Use `not stated`, `null`, empty lists, and explicit warnings for unavailable or uncertain information. Do not write hidden reasoning or extracted full paper text into the note or provenance. The helper validates the required headings and performs exclusive file creation; inspect the draft for scientific fidelity before committing it. If supplementary_pdf is populated: require "## Supplementary Information Used". If supplementary_pdf is null: permit the section to be absent.
