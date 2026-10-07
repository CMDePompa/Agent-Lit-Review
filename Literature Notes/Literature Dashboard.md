[[Literature Database.base|Open Literature Database]] · [[Templates/Literature Note Template|Open note template]] · [[README|Customize this workflow]]

# Database views

These links all open the same [[Literature Database.base|Literature Database]] file. In the database, use the **view menu at the top left** to select the named view. The text after `|` in each link is its label; it does not select a view by itself.

- [[Literature Database.base|Rapid Review]] — citation details, review status, DOI, and linked PDFs.
- [[Literature Database.base|All Literature]] — every note and its research tags, provenance fields, and PDF links.
- [[Literature Database.base|Unread]] — notes with `review_status: unread`.
- [[Literature Database.base|Needs Review]] — AI drafts and notes whose metadata needs checking.
- [[Literature Database.base|Morphologies]] — notes with morphology-related columns; this view currently has no morphology filter.

Quick database links are just a suggested start for the Dashboard; feel free to customize and tailor them to your research domain.

Quick reference material is included below for help getting started with the overall workflow. For the full guide to customization, see [[README|the README file]].

# Quick Reference

## Needs attention

<!-- literature-intake:needs-attention:start -->
No source packages are currently flagged.
<!-- literature-intake:needs-attention:end -->

The intake skill updates the list between the markers above when it cannot process a source package. Later “next paper” runs skip flagged PDFs and continue with the next eligible package. Fix the stated issue, then ask the skill to retry that filename. Replacing or editing the PDF also clears its flag on the next Inbox inspection. Original PDFs stay in `PDFs/Inbox` while flagged.

PDFs successfully processed with “leave the PDF in Inbox” are also excluded from later “next paper” runs.

## Add literature

1. Put a PDF in `PDFs/Inbox` and open the parent `Literature` folder as a Codex project.
2. Ask Codex to use `$literature-intake` with one of the requests below. Each run handles at most one primary source package unless you explicitly ask for more.
3. A successful run creates a note in `Literature Notes/Papers`, stores a processing record in `data/processing_records`, and moves the PDF to `PDFs/Ingested` unless you ask it to leave the PDF in Inbox. The note's `pdf` property links to the primary PDF and any paired supplement. If processing fails, the skill flags that PDF above and future “next paper” runs skip it.
4. Open the new note through the database and review it against its linked PDF.

Copy a request into a Codex task:

```text
Use $literature-intake to inspect the Inbox and report what is waiting.
```

```text
Use $literature-intake to process the next eligible source package. As soon as you select its PDF, rename this chat to “LitNote — <PDF filename without .pdf>”. Keep that title even if processing fails. If no source is eligible, leave the chat title unchanged. 

```

```text
Use $literature-intake to process this paper: PDFs/Inbox/example.pdf. As soon as you select its PDF, rename this chat to “LitNote — <PDF filename without .pdf>”. Keep that title even if processing fails. If no source is eligible, leave the chat title unchanged. 
```

```text
Use $literature-intake to process the next paper but leave the PDF in Inbox. As soon as you select its PDF, rename this chat to “LitNote — <PDF filename without .pdf>”. Keep that title even if processing fails. If no source is eligible, leave the chat title unchanged. 
```

After fixing a flagged source, ask:

```text
Use $literature-intake to retry this paper: PDFs/Inbox/example.pdf. 
```

An Inbox with no eligible primary PDF produces no new note. Existing note names or same-name PDFs in `Ingested` stop that package rather than being overwritten; the skill flags it and continues with another package on the next run. If a supplementary PDF arrives after its parent article was processed, ask Codex to use `$literature-intake` to attach that exact-matched SI to the existing note.

For journal articles, the skill checks a local CSL-JSON Zotero export at `data/zotero-export.json`. If it is missing or unreadable, article intake stops before writing or moving files. If it is readable but has no confident match, intake can continue using metadata visible in the PDF and flags the note for review. Exports older than 30 days produce a stale warning. SI, textbooks, and theses skip Zotero lookup. The workflow does not use an external API or separate API billing.

### File names and source packages

- Articles: `<Year> <Author(s)> - <Article Title>.pdf`
	- Ex: `1993 Amundson et al. - Alignment of lamellar block copolymer microstructure.pdf`.
- Review articles: `REVIEW - <Year> <Author(s)> - <Article Title>.pdf`. These are journal reviews with `source_type: review`; they use article-style notes and Zotero article matching.
- Supplementary information: prefix the **entire matching article filename** with `SI - `
	- Ex: `SI - 1993 Amundson et al. - Alignment of lamellar block copolymer microstructure.pdf`.
	- An exact pair can be processed together. SI is not a separate literature note.
- Textbook chapters: `TEXTBOOK - <Year> <Author> - <Book Title> - Ch <NN> - <Chapter Title>.pdf`.
- Thesis chapters: `THESIS - <Year> <Author> - <Thesis Title> - Ch <NN> - <Chapter Title>.pdf`.

Use two-digit chapter numbers so chapters sort correctly. Split textbooks and theses into chapter PDFs for chapter-level notes. Filenames identify and pair files; the PDF itself supplies the scientific content and provisional metadata. Malformed reserved prefixes are reported and left untouched.

## Review a generated note

The note has three parts:

1. **Properties** hold bibliographic details, source and processing status, PDF links, and research tags. These populate the database.
2. **Generated sections** summarize the source, methods, findings, numerical results, limitations, relevance, and figures worth checking. Sections differ for articles, textbooks, and theses.
3. **Your sections** are **My Notes**, **Figure Screenshots**, and **Connections to Other Papers**. The skill leaves these for you and never overwrites an existing note.

Check the title, authors, year, venue, DOI, claims, numbers, figure suggestions, and tags against the PDF. Review any metadata warnings. After verifying the draft, update `summary_status` and `review_status` in its properties. **Needs Review** includes AI drafts and notes with uncertain metadata.


## Scheduled intake

A scheduled Codex task can check Inbox periodically. Give each run its own task context and ask it to process only the first eligible source package in filename order. Flagged packages are skipped until their issue is fixed and they are retried. Choose a frequency that leaves enough time so that runs don't overlap too much. Suggested task prompt:

```text
Use $literature-intake to process the next eligible source package. As soon as you select its PDF, rename this chat to “LitNote — <PDF filename without .pdf>”. Keep that title even if processing fails. If no source is eligible, leave the chat title unchanged.
```

I recommend asking it to rename the chat to share the title of the source processed because it will get very confusing very quickly once you start processing large amounts of literature.

A faster model with a low reasoning setting may be sufficient for summarizing one paper per chat and can conserve usage for harder tasks.

Use a custom recurrence rule that executes one task per source package. Configure each run to use a new chat in your `Literature` project, with the model and reasoning level you prefer. For example, this rule runs every five minutes:

```
RRULE:FREQ=MINUTELY;INTERVAL=5
```

Add `COUNT=#` to limit the number of runs. Start with a small count so you can measure processing time and usage before scheduling a larger library.

You can also create a monitor that watches the Inbox and starts intake only when a source is waiting.

If your field is math-heavy, I also recommend adding this to your processing prompts so equations are rendered properly in Markdown:

```
FORMATTING RULE FOR MATH & EQUATIONS:
- Format all mathematical variables, symbols, inline equations, and units using standard Markdown LaTeX math delimiters.
- INLINE MATH: Wrap all inline mathematical expressions, single variables, and greek letters in single dollar signs ($...$). 
  Example: Write `$\chi_{AB}$` or `$p \le 1/3$`, NEVER `(chi_{AB})` or `(p \leq 1/3)`.
- DISPLAY MATH: Wrap standalone, multi-line, or primary equations in double dollar signs ($$...$$) on their own lines.
- ALWAYS include proper backslashes for LaTeX commands (e.g., `\chi`, `\alpha`, `\le`, `\frac{}{}`).
- Never use standard parentheses `(...)` or square brackets `[...]` to delimit LaTeX code.
```

## Add a view and a Dashboard link

1. Open [[Literature Database.base|Literature Database]]. Click its view name at the top left and choose **Add view**. Give the view a unique name, such as **Simulation Methods**.
2. Set a **This view** filter if you want only matching notes, for example a particular value in `methodology`. A filter under **All views** would also change the other views. Use **Properties** to choose columns and **Sort** to set their order. The existing folder filter already limits this database to `Literature Notes/Papers`.
3. Return here and add a line like `- [[Literature Database.base|Simulation Methods]] — papers using the selected methods.` to the list above. Use the exact view name as the label so readers know which view to choose in the database menu. Renaming or deleting a view means updating this list too.

For the view to **appear on this Dashboard itself**, place `![[Literature Database.base#Simulation Methods]]` on its own line. The `!` embeds the named view; the name after `#` must exactly match the view in the database. A regular `[[Literature Database.base|...]]` link only opens the database. [Obsidian's view guide](https://obsidian.md/help/bases/views) explains the view menu, filters, columns, and embeds.
