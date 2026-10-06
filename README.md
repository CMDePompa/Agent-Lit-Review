# Agent Lit Review: an agentic coding workflow for turning research PDFs into structured Obsidian literature notes.

This project turns research PDFs into structured notes in an Obsidian vault. A project-local Codex skill, [`literature-intake`](./.agents/skills/literature-intake/SKILL.md), reads one source at a time, drafts a note, links the PDF, and records what it processed. You review the draft against the source before relying on it.

Codex reads the PDF using the model selected for your Codex task. The workflow does not call the OpenAI API, require an API key, or create separate API charges. Its current research vocabulary is for polymer science, but you can change the note fields and research context for another field.

Disclaimer: This project is provided as a research workflow template. Review generated notes against the original sources before relying on them for scholarly work.

## Project structure

```text
Agent-Lit-Review/
├── README.md                              # Setup, usage, and customization guide
├── LICENSE                                # MIT license
├── .gitignore                             # Excludes local app state and generated content
├── .agents/
│   └── skills/
│       └── literature-intake/
│           ├── SKILL.md                   # Main Codex workflow
│           ├── note-schema.md             # Note fields and required sections
│           ├── review-extraction.md       # Review extraction prompt and schema
│           ├── research-context.md        # Project-specific relevance context
│           ├── si-attachment.md           # Separated supplementary-PDF workflow
│           ├── source-types.md            # Paper, review, textbook, and thesis rules
│           ├── textbook-extraction.md     # Textbook chapter extraction prompt
│           ├── thesis-chapter-extraction.md # Thesis subtype extraction rules
│           └── reference-metadata.md      # Zotero/Mendeley metadata policy
├── scripts/
│   ├── literature_intake_io.py            # Safe file operations and provenance
│   ├── reference_metadata.py              # Local and API reference matching
│   ├── test_literature_intake_io.py       # Workflow regression tests
│   └── test_reference_metadata.py         # Provider regression tests
├── Literature Notes/
│   ├── Literature Dashboard.md            # Obsidian quick-start dashboard
│   ├── Literature Database.base           # Obsidian Bases views
│   ├── Templates/
│   │   ├── Literature Note Template.md    # Primary research note template
│   │   ├── Review Note Template.md        # Review article note template
│   │   ├── Textbook Chapter Note Template.md # Textbook chapter note template
│   │   └── Thesis Synthesis Note Template.md # Thesis conclusion template
│   └── Papers/                            # Generated literature notes
├── PDFs/
│   ├── Inbox/                             # PDFs waiting for intake
│   └── Ingested/                          # Processed PDFs
└── data/
    ├── zotero-export.json                 # Optional Zotero CSL-JSON export
    ├── mendeley-export.json               # Optional Mendeley CSL-JSON export
    ├── mendeley-export.bib                # Optional Mendeley BibTeX export
    ├── tmp/                               # Local scratch files and unresolved flags
    └── processing_records/                # Intake provenance records
```

The repository includes zero-byte `.gitkeep` placeholder files so a fresh clone contains the empty `PDFs/Inbox`, `PDFs/Ingested`, `Literature Notes/Papers`, `data/tmp`, and `data/processing_records` folders. Git does not track empty directories. The placeholders contain no data.

## What you need

- Codex (or another local agentic AI software, but reference material will continue to assume Codex) with access to a local project folder.
- [Obsidian](https://obsidian.md/) to browse the notes and database. The notes are Markdown files, so you can also read them in another editor.
- Python 3 to run the small, local file and metadata helpers. They use the Python standard library; there is no package installation step.
- For **journal articles**, either a local Zotero/Mendeley export or credentials for the chosen reference-manager API. No reference-manager setup is required for PDF-only fallback.

## Get started

### Step 1: Download the project

Download or clone this repository. Keep its folders together, including the hidden `.agents` folder that contains the skill.

### Step 2: Open the project

Open the repository folder as an Obsidian vault and as a local project in Codex. Start with the [Literature Dashboard](Literature%20Notes/Literature%20Dashboard.md) for the day-to-day instructions.

### Step 3: Configure reference metadata

Reference-manager metadata is optional for journal articles. Choose any of these sources:

- Zotero Web API v3: create a read-only key for your personal library, then set `ZOTERO_API_KEY` and your numeric `ZOTERO_USER_ID` in the environment used to run Codex or the helper. See the setup steps below.
- Mendeley Documents API: set an OAuth access token as `MENDELEY_ACCESS_TOKEN` in your local environment. The token must authorize your documents; this helper does not perform OAuth login or refresh.
- Local export: save Zotero CSL JSON as `data/zotero-export.json`, or Mendeley CSL JSON/BibTeX as `data/mendeley-export.json` / `data/mendeley-export.bib`.

#### Set up Zotero Web API access

1. Sign in at [Zotero's API Keys page](https://www.zotero.org/settings/keys). Copy your **numeric user ID** shown there; it is different from your Zotero username. Create a new private key for this workflow with **read access to your personal library**. This helper only reads item metadata, so it does not need write, file, or notes access. Copy the key when Zotero displays it.
2. On Windows, set `ZOTERO_USER_ID` and `ZOTERO_API_KEY` as **user environment variables** (search Windows for “Edit environment variables for your account”). Restart Codex after saving them so new tasks inherit the values. For a one-time manual check in PowerShell, set them in that same terminal instead:

   ```powershell
   $env:ZOTERO_USER_ID = '123456'     # replace with your numeric Zotero user ID
   $env:ZOTERO_API_KEY = 'your-key'    # replace with your new private key
   python scripts/reference_metadata.py --provider zotero --check-source
   ```

3. In the `--check-source` output, `api_status: "configured_unverified"` means both variables were found; it **does not verify the key**. To test access without displaying the key, run this in the same PowerShell session:

   ```powershell
   $headers = @{ 'Zotero-API-Key' = $env:ZOTERO_API_KEY; 'Zotero-API-Version' = '3' }
   $keyInfo = Invoke-RestMethod -Uri 'https://api.zotero.org/keys/current' -Headers $headers
   $keyInfo.userID
   $keyInfo.access.user.library
   ```

   The number should match `ZOTERO_USER_ID`, and the library-access value should be `True`. If Zotero denies access, check the key and its personal-library read permission. See [reference-metadata.md](./.agents/skills/literature-intake/reference-metadata.md) for a lookup example. Do not paste your key into chat or save it in the repository; this script does not load a `.env` file.

For a lookup, save PDF-visible bibliographic fields as JSON in `data/tmp/request.json`, then run `python scripts/reference_metadata.py data/tmp/request.json --provider auto --output data/tmp/lookup.json`. Use `--provider zotero` or `--provider mendeley` to select one manager. API access is preferred when configured; a local export is available as fallback. If no confident match is available, intake continues with PDF-visible metadata, sets `metadata_source: "PDF"` and `metadata_review_needed: true`, and records a warning. Textbook and thesis intake skips the lookup. Exports and scratch files are ignored by Git.

### Step 4: Customize the workflow

The included note fields and research vocabulary are designed for polymer science. You can use them as-is or adapt them for another field. For example, an ecology project might use `study_organisms` and `habitats` in place of `polymer_system` and `morphologies`. Make changes in the following order so the skill, template, and database agree.

#### 4.1 Describe your field

Edit the included [`research-context.md`](./.agents/skills/literature-intake/research-context.md) to describe your research questions, methods, measurements, and vocabulary. Explain what makes a source highly relevant, indirectly relevant, or unrelated to your work. The PDF remains the source for facts about the paper; this file guides only the relevance assessment and suggested topics.

#### 4.2 Choose note properties

Open [`Literature Note Template.md`](Literature%20Notes/Templates/Literature%20Note%20Template.md). Its first block, between the `---` lines, contains the note's **properties**. Properties appear in Obsidian and supply the database columns.

- Rename or replace field-specific properties. For example, change `polymer_system: []` to `study_organisms: []`.
- Keep fields with multiple tags as lists ending in `[]` when empty. Keep a short description such as `context_summary: ""` as text.
- Leave workflow fields such as `pdf`, `source_type`, `summary_status`, and `metadata_review_needed` in place unless you also plan to change the file-handling code.

Then update [`note-schema.md`](./.agents/skills/literature-intake/note-schema.md): replace the old property names, define what each new field means, and give examples of suitable tags. Tell the skill to leave a field empty when the PDF does not support a value. If you change note section headings, update the headings in the template and schema together.

The file helper also checks property names. In `scripts/literature_intake_io.py`, change `TAG_LIST_PROPERTIES` when you rename list fields and `TAG_PROPERTIES` when you change text tag fields. Update `scripts/test_literature_intake_io.py` to cover the new names. A template edit by itself will not rename properties in notes already created; update older notes separately if they should use the new fields.

#### 4.3 Show the fields in Obsidian

Open [`Literature Database.base`](Literature%20Notes/Literature%20Database.base) in Obsidian. Its named **views** are different ways to show the same notes. You can change a view's visible columns with **Properties**, its order with **Sort**, and which notes it includes with **Filter**. The existing folder filter applies to every view, so all of them start with notes in `Literature Notes/Papers`. If you prefer editing the `.base` file directly, its `views` list holds the names, columns in `order`, and optional view-specific `filters`.

To create a new view and add it to the [Dashboard](Literature%20Notes/Literature%20Dashboard.md):

1. In the open database, click the view name at the top left and choose **Add view**. Give it a clear name, such as **Simulation Methods**.
2. Under **Filter**, choose **This view** if the filter should apply only here; select a property such as `methodology`, a comparison, and a value. Choose **All views** only if every view should change. Use **Properties** to pick columns and **Sort** to order the results.
3. In `Literature Notes/Literature Dashboard.md`, add a list item such as `- [[Literature Database.base|Simulation Methods]] — papers using the selected methods.` The part before `|` is the file to open; the part after `|` is only the displayed label. Clicking it opens the database, where the reader selects **Simulation Methods** from the view menu. It does **not** switch views automatically.
4. If you want that exact view displayed inside the Dashboard, add `![[Literature Database.base#Simulation Methods]]` on its own line. The `!` makes it an embed, and the text after `#` must match the view name. If you rename or delete the view, update both the list label and any embed.

The same link rule applies to the Dashboard's template and README links: update their targets if you move or rename files, then click them in Obsidian to check that they work. [Obsidian's Bases view guide](https://obsidian.md/help/bases/views) has screenshots and the current menu instructions.

#### 4.4 Update the skill instructions

Open [`SKILL.md`](./.agents/skills/literature-intake/SKILL.md). Its `description` tells Codex when this skill is relevant; change it if people in your field will use different words for their sources or intake requests. Update the body only where the workflow itself needs to change. Keep the frontmatter limited to `name` and `description`, and keep the PDF-reading, file-collision, one-source-per-run, and human-owned-section safeguards.

The skill has a few focused reference files:

| File | Change it when... |
| --- | --- |
| [`source-types.md`](./.agents/skills/literature-intake/source-types.md) | You want different source types, chapter rules, or note outlines. Also update the matching rules and tests in `literature_intake_io.py`. |
| [`si-attachment.md`](./.agents/skills/literature-intake/si-attachment.md) | You want different rules for supplementary PDFs. Update matching guidance in the Dashboard and skill too. |
| [`reference-metadata.md`](./.agents/skills/literature-intake/reference-metadata.md) | You want to change the article metadata policy. Update [`reference_metadata.py`](scripts/reference_metadata.py), SKILL.md, and tests as well. |

The reference rule is: an unavailable, ambiguous, conflicting, or unmatched source does not stop **article** intake. The note uses only metadata visible in the PDF, sets `metadata_source: "PDF"` and `metadata_review_needed: true`, and records a warning. A local export older than 30 days gets a stale warning. Supplementary PDFs, textbooks, and theses skip the lookup.

#### 4.5 Check your customization

Run `python -m unittest scripts/test_literature_intake_io.py scripts/test_reference_metadata.py` from the repository folder. You can also ask Codex, “Validate the structure and frontmatter of the project-local `literature-intake` skill.” Open the Dashboard and Database in Obsidian and test their links and views.

### Step 5: Add a source package

Put a PDF in `PDFs/Inbox`. Filenames help organize source packages and pair supplementary information; classification, scientific content, and provisional metadata come from the PDF itself.

- **Articles:** `<Year> <Author(s)> - <Article Title>.pdf`
  - Example: `1993 Amundson et al. - Alignment of lamellar block copolymer microstructure.pdf`
- **Review articles:** `REVIEW - <Year> <Author(s)> - <Article Title>.pdf` is a naming convention.
  - The skill classifies the PDF title and full section headings. Review phrases or no distinct methods section route to `document_type: review`, the review extraction prompt, and the Review Note Template. Uncertain cases default to `document_type: primary`. Both use reference-manager matching when available.
- **Supplementary information:** prefix the entire matching article filename with `SI - `
  - Example: `SI - 1993 Amundson et al. - Alignment of lamellar block copolymer microstructure.pdf`
  - An exact pair can be processed together. SI is not a separate literature note.
- **Textbook chapters:** `TEXTBOOK - <Year> <Author> - <Book Title> - Ch <NN> - <Chapter Title>.pdf`
  - Chapter headings, learning objectives, worked examples, exercises, review questions, or other pedagogical structure route to `document_type: textbook_chapter` and the dedicated chapter template. Equations and variables use LaTeX math notation. Textbook chapters skip reference-manager lookup.
- **Thesis chapters:** `THESIS - <Year> <Author> - <Thesis Title> - Ch <NN> - <Chapter Title>.pdf`
  - PDF evidence of thesis identity selects `document_type: thesis_chapter`; chapter purpose selects the required `thesis_subtype`. Introductions reuse the review schema with specific aims, methods/theory chapters reuse the textbook schema with custom protocols, research chapters reuse the primary schema with a mapped aim, and concluding chapters use the Thesis Synthesis Note Template. Thesis chapters skip reference-manager lookup.

Process textbooks and theses one chapter at a time whenever practical. This keeps the AI's context from being overwhelmed and keeps each note focused on one coherent source unit. Use two-digit chapter numbers so chapters sort correctly. Process a complete thesis only when explicitly requested and when the agent can read it adequately. Malformed reserved prefixes are reported and left untouched.

Next you may prompt your AI to use the literature-intake skill, using the model and reasoning level of your choice. I find using a lower tier model on light reasoning performs quite well for this workflow. Using less sophisticated models also performs faster and consumes allowance more conservatively without sacrificing summary quality. 

Example prompts:

```text
Use $literature-intake to inspect the Inbox and report what is waiting.
```

Then process one source:

```text
Use $literature-intake to process this paper: PDFs/Inbox/example.pdf
```

A successful run moves the PDF to `PDFs/Ingested`, unless you ask Codex to leave it in Inbox. The skill stops on file collisions instead of overwriting notes or PDFs and creates a compact record in `data/processing_records`. If a source package cannot be processed, the skill leaves its PDFs in Inbox, records the reason under **Needs attention** on the [Dashboard](Literature%20Notes/Literature%20Dashboard.md), and skips that package on future “next paper” runs. The next run can continue with another eligible package.

After fixing the issue, ask the skill to retry the flagged filename, for example, `Use $literature-intake to retry this paper: PDFs/Inbox/example.pdf`. Editing or replacing the PDF also makes it eligible again on the next Inbox inspection. The Dashboard shows the reported reason so you can tell what needs fixing; the failure queue is stored locally in `data/tmp/intake_failures.json` and is deleted automatically when no flags remain.

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

### Step 6: Review the generated note

Open the new note in `Literature Notes/Papers` or through the [Literature Database](Literature%20Notes/Literature%20Database.base). Check its claims, metadata, numbers, figure suggestions, and tags against the linked PDF. The note is an AI draft until you review it. Confirm that the `pdf` property opens the source and that **My Notes**, **Figure Screenshots**, and **Connections to Other Papers** remain available for your own writing.

The [Dashboard](Literature%20Notes/Literature%20Dashboard.md) has more prompts, supplementary-file guidance, and review steps. The skill's workflow version is stored separately in the processing record.

## Using other AI agents

The workflow is built from an [Agent Skills](https://developers.openai.com/api/docs/guides/tools-skills) `SKILL.md`, Markdown references, and standard-library Python scripts. Those parts are portable, but each agent product has different skill-discovery locations, PDF tools, permissions, and scheduling features.

### Claude Code

Claude Code discovers project skills from `.claude/skills/<skill-name>/SKILL.md`, whereas this repository keeps the canonical skill in `.agents/skills/literature-intake` for Codex. After cloning, copy the skill into Claude Code's project-skill directory:

PowerShell:

```powershell
New-Item -ItemType Directory -Force .claude\skills | Out-Null
Copy-Item -Recurse .agents\skills\literature-intake .claude\skills\
```

macOS or Linux:

```bash
mkdir -p .claude/skills
cp -R .agents/skills/literature-intake .claude/skills/
```

Then open the repository root in Claude Code and ask it to use the `literature-intake` skill. The same Python helpers, note template, collision checks, and reference-manager options apply. See [Anthropic's Agent Skills documentation](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) for its current discovery rules.

Claude Code does not include Anthropic's pre-built PDF Agent Skill, so PDF-reading behavior depends on the tools available in that Claude Code environment. Test one disposable source first and ask Claude to leave it in Inbox. If the agent cannot inspect the complete PDF—including methods, results, figures, and limitations—stop rather than creating a partial note. Claude scheduling is also separate from Codex scheduled tasks; configure recurring runs using the automation mechanism provided by your chosen environment.

If you edit the skill in `.agents/skills/literature-intake` later, repeat the copy so Claude Code receives the same version.

### Other local AI agents

Another agent can use this workflow when it can:

- Read the selected PDF thoroughly, including figures and tables when relevant.
- Read and write files inside the repository while respecting the collision and human-owned-section safeguards.
- Run Python 3 scripts from the repository root.
- Load a `SKILL.md` or accept the workflow as project instructions.

If the agent does not automatically discover Agent Skills, point it to `.agents/skills/literature-intake/SKILL.md` and ask it to follow that file for the current task. Do not assume that generic chat interfaces can move local files, run the helpers, or access an Obsidian vault. Web-only assistants generally require manual file uploads and downloads, which does not reproduce the local intake workflow end to end.

Regardless of the model, keep the same safety rules: process one source package at a time, do not overwrite existing notes or PDFs, do not use filenames as scientific evidence, and review every generated note against the source.

## Why one source at a time?

The skill processes at most **one source package per request** by default. A package is one primary PDF plus its exact-matched supplementary PDF, if there is one. Reading the methods, results, figures, and limitations of many papers in one request can crowd the task's working context and make it harder to keep claims tied to the right source. One package per run also makes each note and file move easier to check or retry if something fails.

You can explicitly ask for multiple papers, but for a large Inbox, use separate Codex tasks that each process one package. Repeating “process the next paper” many times in the **same** long chat can still accumulate context, even though each request handles only one paper. A scheduled workflow can automate processing multiple packages in separate runs; the Dashboard includes a suggested prompt. Start with a few sources to evaluate and customize the workflow before processing an entire library.

## License

This project is available under the [MIT License](./LICENSE).
