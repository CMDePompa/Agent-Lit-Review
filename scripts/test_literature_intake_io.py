import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import literature_intake_io as intake
import zotero_metadata


class IntakeFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.inbox = self.root / "PDFs" / "Inbox"
        self.inbox.mkdir(parents=True)
        self.pdf = self.inbox / "paper.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\nfixture")
        human = {"My Notes", "Figure Screenshots", "Connections to Other Papers"}
        self.note_text = "---\ntitle: ''\nsource_type: paper\ndocument_type: primary\nmetadata_review_needed: true\npdf: ../../PDFs/Inbox/paper.pdf\n---\n" + "\n".join(f"## {h}\n\n" + ("" if h in human else "Not stated.\n") for h in intake.PAPER_SECTIONS)

    def tearDown(self):
        self.tmp.cleanup()

    def test_inspection_and_empty_inbox(self):
        self.assertEqual(intake.inbox_items(self.root), ["paper.pdf"])
        self.assertEqual(intake.inspect_queue(self.root)["eligible"], ["paper.pdf"])
        self.pdf.unlink()
        self.assertEqual(intake.inbox_items(self.root), [])
        self.assertFalse((self.root / "Literature Notes").exists())

    def dashboard_fixture(self):
        dashboard = self.root / "Literature Notes" / "Literature Dashboard.md"
        dashboard.parent.mkdir(parents=True, exist_ok=True)
        dashboard.write_text(
            "# My dashboard\n\n" + intake.FAILURES_START + "\nNo source packages are currently flagged.\n"
            + intake.FAILURES_END + "\n\nMy own section stays here.\n", encoding="utf-8"
        )
        return dashboard

    def test_failed_first_pdf_is_flagged_and_next_pdf_is_eligible(self):
        dashboard = self.dashboard_fixture()
        first = self.inbox / "a.pdf"
        first.write_bytes(b"not a PDF")
        intake.defer_pdf(first, "Unreadable PDF; replace it with a valid export.", self.root)
        queue = intake.inspect_queue(self.root)
        self.assertEqual(queue["eligible"], ["paper.pdf"])
        self.assertEqual(queue["needs_attention"][0]["filename"], "a.pdf")
        self.assertIn("Unreadable PDF", dashboard.read_text(encoding="utf-8"))
        self.assertIn("My own section stays here.", dashboard.read_text(encoding="utf-8"))
        self.assertTrue(first.exists())
        self.assertEqual(json.loads((self.root / "data" / "tmp" / "intake_failures.json").read_text(encoding="utf-8"))["items"]["a.pdf"]["reason"],
                         "Unreadable PDF; replace it with a valid export.")

    def test_changed_pdf_requeues_and_clears_dashboard_flag(self):
        dashboard = self.dashboard_fixture()
        intake.defer_pdf(self.pdf, "Cannot read pages; replace the PDF.", self.root)
        self.pdf.write_bytes(b"%PDF-1.4\nreplacement content")
        queue = intake.inspect_queue(self.root)
        self.assertEqual(queue["eligible"], ["paper.pdf"])
        self.assertEqual(queue["needs_attention"], [])
        self.assertIn("No source packages are currently flagged.", dashboard.read_text(encoding="utf-8"))

    def test_retry_and_success_clear_failure_flag(self):
        dashboard = self.dashboard_fixture()
        intake.defer_pdf(self.pdf, "Metadata export missing.", self.root)
        self.assertEqual(intake.inspect_queue(self.root)["eligible"], [])
        intake.retry_pdf(self.pdf, self.root)
        self.assertEqual(intake.inspect_queue(self.root)["eligible"], ["paper.pdf"])
        self.assertFalse((self.root / "data" / "tmp" / "intake_failures.json").exists())
        intake.defer_pdf(self.pdf, "Metadata export missing.", self.root)
        intake.commit(self.pdf, "paper", self.note_text, no_move=True, root=self.root)
        queue = intake.inspect_queue(self.root)
        self.assertEqual(queue["needs_attention"], [])
        self.assertEqual(queue["already_processed"], ["paper.pdf"])
        self.assertEqual(queue["eligible"], [])
        self.assertIn("No source packages are currently flagged.", dashboard.read_text(encoding="utf-8"))
        self.assertFalse((self.root / "data" / "tmp" / "intake_failures.json").exists())

    def test_missing_zotero_export_falls_back_to_pdf_and_cleans_temporary_file(self):
        lookup = zotero_metadata.lookup(
            {"source_type": "paper", "title": "Visible PDF title", "authors": ["A. Author"], "year": 2024},
            export_path=self.root / "data" / "missing-zotero-export.json",
        )
        self.assertEqual(lookup["status"], "unavailable")
        self.assertEqual(lookup["metadata_source"], "PDF")
        self.assertTrue(lookup["metadata_review_needed"])
        temporary = self.root / "data" / "tmp" / "draft.md"
        temporary.parent.mkdir(parents=True)
        temporary.write_text(self.note_text, encoding="utf-8")
        result = intake.commit(
            self.pdf, "paper", temporary.read_text(encoding="utf-8"), no_move=True,
            metadata_lookup=lookup, temporary_files=[temporary], root=self.root,
        )
        saved = (self.root / result["generated_note_path"]).read_text(encoding="utf-8")
        self.assertEqual(intake._frontmatter_value(saved, "metadata_source"), "PDF")
        self.assertEqual(intake._frontmatter_value(saved, "metadata_review_needed"), "true")
        self.assertIn("was not found", result["warnings"][0])
        self.assertFalse(temporary.exists())

    def test_unreadable_zotero_export_uses_same_soft_fallback(self):
        export = self.root / "data" / "zotero-export.json"
        export.parent.mkdir(parents=True)
        export.write_text("not valid JSON", encoding="utf-8")
        lookup = zotero_metadata.lookup(
            {"source_type": "paper", "title": "Visible PDF title"}, export_path=export,
        )
        self.assertEqual(lookup["status"], "unavailable")
        self.assertEqual(lookup["metadata_source"], "PDF")
        self.assertTrue(lookup["metadata_review_needed"])
        self.assertIn("could not be read", lookup["warnings"][0])

    def test_existing_note_collision(self):
        note = self.root / "Literature Notes" / "Papers" / "paper.md"
        note.parent.mkdir(parents=True)
        note.write_text("Human notes", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            intake.destinations(self.pdf, "paper", self.root)
        self.assertEqual(note.read_text(encoding="utf-8"), "Human notes")
        self.assertTrue(self.pdf.exists())

    def test_existing_ingested_pdf_collision_even_no_move(self):
        target = self.root / "PDFs" / "Ingested" / "paper.pdf"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"old")
        with self.assertRaises(FileExistsError):
            intake.commit(self.pdf, "paper", self.note_text, no_move=True, root=self.root)
        self.assertTrue(self.pdf.exists())

    def test_no_move_and_provenance(self):
        result = intake.commit(self.pdf, "paper", self.note_text, no_move=True, root=self.root)
        self.assertTrue(self.pdf.exists())
        note = self.root / result["generated_note_path"]
        self.assertTrue(note.exists())
        saved = note.read_text(encoding="utf-8")
        self.assertNotIn("**PDF:**", saved)
        self.assertNotIn("literature-intake:pdf-links", saved)
        self.assertEqual(intake._frontmatter_pdf_values(saved), ["PDFs/Inbox/paper.pdf"])
        self.assertEqual(intake._frontmatter_value(saved, "research_topics"), "[]")
        self.assertEqual(intake._frontmatter_value(saved, "context_summary"), "")
        self.assertEqual(result["resulting_pdf_path"], "PDFs\\Inbox\\paper.pdf" if sys.platform == "win32" else "PDFs/Inbox/paper.pdf")
        self.assertEqual(result["skill_name"], "literature-intake")
        for key in ("model", "prompt_version", "processed_at"):
            self.assertNotIn(f"{key}:", saved.split("---", 2)[1])
        self.assertIsNone(result["selected_codex_tier"])
        self.assertEqual(len(result["pdf_sha256"]), 64)

    def test_commit_records_selected_model_and_tier(self):
        legacy_draft = self.note_text.replace("source_type: paper\n", 'source_type: paper\nmodel: "old"\nprompt_version: "old"\nprocessed_at: "old"\n', 1)
        result = intake.commit(self.pdf, "paper", legacy_draft, no_move=True, model="gpt-example", tier="high", root=self.root)
        saved = (self.root / result["generated_note_path"]).read_text(encoding="utf-8")
        for key in ("model", "prompt_version", "processed_at"):
            self.assertNotIn(f"{key}:", saved.split("---", 2)[1])
        self.assertEqual(result["selected_codex_model"], "gpt-example")
        self.assertEqual(result["selected_codex_tier"], "high")
        self.assertEqual(result["skill_workflow_version"], intake.VERSION)

    def test_review_schema_routes_without_filename_prefix(self):
        template = (intake.ROOT / "Literature Notes" / "Templates" / "Review Note Template.md").read_text(encoding="utf-8")
        review_note = template.replace('title: ""', 'title: "Review title"', 1)
        review_note = review_note.replace("## Rapid Summary", "## Rapid Summary\n\nA field synthesis.\n", 1)
        with self.assertRaises(ValueError):
            intake.commit(self.pdf, "paper", review_note.replace("## Scope & Taxonomy of the Field", "## Research Question"), no_move=True, root=self.root)
        result = intake.commit(self.pdf, "paper", review_note, no_move=True, root=self.root)
        saved = (self.root / result["generated_note_path"]).read_text(encoding="utf-8")
        self.assertEqual(intake._frontmatter_value(saved, "source_type"), "review")
        self.assertEqual(intake._frontmatter_value(saved, "document_type"), "review")
        self.assertEqual(result["document_type"], "review")
        self.assertTrue(self.pdf.exists())

    def test_classify_paper_routing(self):
        headings = ["Introduction", "Results", "Materials and Methods", "Discussion"]
        self.assertEqual(intake.classify_document("Experimental self assembly", headings)["document_type"], "primary")
        self.assertEqual(intake.classify_document("Progress in polymer interfaces", headings)["document_type"], "review")
        self.assertEqual(intake.classify_document("Polymer interfaces", ["Introduction", "Outlook"])["document_type"], "review")
        self.assertEqual(intake.classify_document("Polymer interfaces")["document_type"], "primary")
        self.assertEqual(intake.classify_document("Chapter 4: Polymer Thermodynamics", ["Learning Objectives", "Worked Example 4.1"])["document_type"], "textbook_chapter")
        self.assertEqual(intake.classify_document("Fundamentals of Polymers", ["Introduction", "Chapter Summary"])["document_type"], "textbook_chapter")
        self.assertEqual(intake.classify_document("Fundamentals of Polymers", ["Introduction"], has_end_of_chapter_exercises=True)["document_type"], "textbook_chapter")
        self.assertEqual(intake.classify_document("Fundamentals of Polymers", pedagogical_structure=True)["document_type"], "textbook_chapter")

    def test_textbook_chapter_uses_dedicated_schema_and_latex_formulas(self):
        template = (intake.ROOT / "Literature Notes" / "Templates" / "Textbook Chapter Note Template.md").read_text(encoding="utf-8")
        chapter_pdf = self.inbox / "chapter.pdf"
        chapter_pdf.write_bytes(b"%PDF-1.4\nfixture")
        draft = template.replace("| Name of Equation/Law | $...$ | Define each variable using $...$ notation | Significance or application |",
                                 "| Ideal gas law | $PV=nRT$ | $P$: pressure; $V$: volume | Relates state variables |")
        classification = {"title": "Chapter 2: Thermodynamics", "section_headings": ["Learning Objectives", "Worked Example 2.1"]}
        result = intake.commit(chapter_pdf, "chapter", draft, no_move=True, classification=classification, root=self.root)
        saved = (self.root / result["generated_note_path"]).read_text(encoding="utf-8")
        self.assertEqual(intake._frontmatter_value(saved, "document_type"), "textbook_chapter")
        self.assertEqual(intake._frontmatter_value(saved, "source_type"), "textbook-chapter")
        self.assertIn("## Concept Check & Self-Assessment Questions", saved)
        self.assertNotIn("## Methods and System", saved)
        self.assertEqual(result["document_type"], "textbook_chapter")

    def test_textbook_formula_table_rejects_non_latex_expression(self):
        template = (intake.ROOT / "Literature Notes" / "Templates" / "Textbook Chapter Note Template.md").read_text(encoding="utf-8")
        draft = template.replace("$...$", "PV=nRT", 1)
        with self.assertRaisesRegex(ValueError, "LaTeX notation"):
            intake.validate_note(draft)

    def test_thesis_two_tier_classification_and_schema_routes(self):
        cases = (
            ("intro_literature_review", "Chapter 1: Background and Literature Review",
             ["Prior Work", "Specific Aims"], "Review Note Template.md", "review",
             "Thesis Scope & Specific Aims", "Suggested Topics"),
            ("methodology_theory", "Chapter 2: Experimental Methodology",
             ["Custom Apparatus", "Experimental Protocol"], "Textbook Chapter Note Template.md",
             "textbook_chapter", "Custom Setups & Key Protocols", "My Notes"),
            ("research_body", "Chapter 3: Results and Discussion",
             ["Data Analysis", "Results", "Discussion"], "Literature Note Template.md",
             "primary", "Mapped Thesis Aim", "Suggested Topics"),
            ("synthesis_conclusion", "Chapter 6: Conclusions and Future Directions",
             ["Overall Contributions", "Future Research"], "Thesis Synthesis Note Template.md",
             "thesis_chapter", None, None),
        )
        for subtype, title, headings, template_name, base_type, extra, insertion in cases:
            with self.subTest(subtype=subtype):
                classification = {"title": title, "section_headings": headings, "is_thesis_chapter": True}
                decision = intake.classify_document(title, headings, is_thesis_chapter=True)
                self.assertEqual(decision["document_type"], "thesis_chapter")
                self.assertEqual(decision["thesis_subtype"], subtype)
                self.assertEqual(decision["required_section"], extra)
                draft = (intake.ROOT / "Literature Notes" / "Templates" / template_name).read_text(encoding="utf-8")
                if base_type != "thesis_chapter":
                    source = {"review": "review", "textbook_chapter": "textbook-chapter", "primary": "paper"}[base_type]
                    draft = draft.replace(f'source_type: "{source}"', 'source_type: "thesis-chapter"', 1)
                    draft = draft.replace(f'document_type: "{base_type}"',
                                          f'document_type: "thesis_chapter"\nthesis_subtype: "{subtype}"', 1)
                    draft = draft.replace(f"## {insertion}", f"## {extra}\n\nNot stated in this chapter.\n\n## {insertion}", 1)
                    if subtype == "research_body":
                        draft = draft.replace('thesis_subtype: "research_body"',
                                              'thesis_subtype: "research_body"\nmapped_thesis_aim: "Aim stated in this chapter"', 1)
                pdf = self.inbox / f"{subtype}.pdf"
                pdf.write_bytes(b"%PDF-1.4\nfixture")
                result = intake.commit(pdf, subtype, draft, no_move=True, classification=classification, root=self.root)
                note = (self.root / result["generated_note_path"]).read_text(encoding="utf-8")
                self.assertEqual(intake._frontmatter_value(note, "document_type"), "thesis_chapter")
                self.assertEqual(intake._frontmatter_value(note, "thesis_subtype"), subtype)
                self.assertEqual(result["thesis_subtype"], subtype)
                if extra:
                    self.assertIn(f"## {extra}", note)

    def test_thesis_subtype_and_research_aim_are_required(self):
        template = (intake.ROOT / "Literature Notes" / "Templates" / "Thesis Synthesis Note Template.md").read_text(encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "thesis_subtype"):
            intake.validate_note(template.replace('thesis_subtype: "synthesis_conclusion"\n', "", 1))
        primary = (intake.ROOT / "Literature Notes" / "Templates" / "Literature Note Template.md").read_text(encoding="utf-8")
        research = primary.replace('source_type: "paper"', 'source_type: "thesis-chapter"', 1)
        research = research.replace('document_type: "primary"',
                                    'document_type: "thesis_chapter"\nthesis_subtype: "research_body"', 1)
        research = research.replace("## Suggested Topics", "## Mapped Thesis Aim\n\nNot stated.\n\n## Suggested Topics", 1)
        with self.assertRaisesRegex(ValueError, "mapped_thesis_aim"):
            intake.validate_note(research)

    def test_unclear_thesis_subtype_does_not_guess(self):
        with self.assertRaisesRegex(ValueError, "subtype is unclear"):
            intake.classify_document("Chapter 4: Additional Topics", ["Introduction", "Overview"], is_thesis_chapter=True)
        with self.assertRaisesRegex(ValueError, "must be a boolean"):
            intake.classify_document("Chapter 4: Results", ["Results"], is_thesis_chapter="false")

    def test_commit_rejects_wrong_thesis_subtype_before_writing(self):
        template = (intake.ROOT / "Literature Notes" / "Templates" / "Thesis Synthesis Note Template.md").read_text(encoding="utf-8")
        chapter_pdf = self.inbox / "thesis-chapter.pdf"
        chapter_pdf.write_bytes(b"%PDF-1.4\nfixture")
        with self.assertRaisesRegex(ValueError, "disagrees"):
            intake.commit(
                chapter_pdf, "thesis-chapter", template, no_move=True,
                classification={"title": "Chapter 3: Results", "section_headings": ["Results", "Data Analysis"],
                                "is_thesis_chapter": True}, root=self.root,
            )
        self.assertTrue(chapter_pdf.exists())
        self.assertFalse((self.root / "Literature Notes" / "Papers" / "thesis-chapter.md").exists())

    def test_commit_rejects_schema_that_disagrees_with_classification(self):
        with self.assertRaisesRegex(ValueError, "disagrees"):
            intake.commit(
                self.pdf, "paper", self.note_text, no_move=True,
                classification={"title": "A Survey of Polymer Interfaces", "section_headings": ["Introduction", "Outlook"]},
                root=self.root,
            )
        self.assertTrue(self.pdf.exists())
        self.assertFalse((self.root / "Literature Notes" / "Papers" / "paper.md").exists())

    def test_review_uses_article_zotero_lookup(self):
        export = self.root / "zotero.json"
        export.write_text(json.dumps([{
            "type": "article-journal", "title": "Review title", "DOI": "10.1000/review",
            "author": [{"given": "A.", "family": "Researcher"}],
            "issued": {"date-parts": [[2020]]}, "container-title": "Example Journal",
        }]), encoding="utf-8")
        result = zotero_metadata.lookup({"source_type": "review", "title": "Review title", "doi": "10.1000/review"}, export_path=export)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["match_method"], "exact-doi")

    def test_commit_stores_primary_and_supplementary_links_in_pdf_property(self):
        supplementary = self.inbox / "SI - paper.pdf"
        supplementary.write_bytes(b"%PDF-1.4\nfixture SI")
        draft = self.note_text.replace("## Rapid Summary", "## Supplementary Information Used\n\n- **File:** SI - paper.pdf\n- **Material consulted:** All pages.\n- **Important contributions to this note:** Not stated.\n\n## Rapid Summary", 1)
        result = intake.commit(self.pdf, "paper", draft, supplementary_pdf_value=str(supplementary), no_move=True, root=self.root)
        saved = (self.root / result["generated_note_path"]).read_text(encoding="utf-8")
        self.assertNotIn("**PDF:**", saved)
        self.assertNotIn("**Supplementary PDF:**", saved)
        self.assertNotIn("literature-intake:pdf-links", saved)
        self.assertEqual(intake._frontmatter_pdf_values(saved), [
            "PDFs/Inbox/paper.pdf", "PDFs/Inbox/SI - paper.pdf",
        ])

    def test_project_template_placeholders_become_pdf_property_links(self):
        template = (intake.ROOT / "Literature Notes" / "Templates" / "Literature Note Template.md").read_text(encoding="utf-8")
        result = intake.commit(self.pdf, "paper", template, no_move=True, root=self.root)
        saved = (self.root / result["generated_note_path"]).read_text(encoding="utf-8")
        self.assertEqual(intake._frontmatter_pdf_values(saved), ["PDFs/Inbox/paper.pdf"])
        self.assertNotIn("**PDF:**", saved)
        self.assertNotIn("primary.pdf", saved)
        self.assertNotIn("supplementary.pdf", saved)
        self.assertEqual(intake._frontmatter_value(saved, "research_topics"), "[]")

    def test_commit_accepts_obsidian_block_style_tag_lists(self):
        draft = self.note_text.replace(
            "pdf: ../../PDFs/Inbox/paper.pdf\n---",
            "pdf: ../../PDFs/Inbox/paper.pdf\nresearch_topics:\n  - phase-behavior\n---",
            1,
        )
        result = intake.commit(self.pdf, "paper", draft, no_move=True, root=self.root)
        saved = (self.root / result["generated_note_path"]).read_text(encoding="utf-8")
        self.assertEqual(intake._frontmatter_list_values(saved, "research_topics"), ["phase-behavior"])

    def test_invalid_note_leaves_source(self):
        with self.assertRaises(ValueError):
            intake.commit(self.pdf, "paper", "incomplete", root=self.root)
        self.assertTrue(self.pdf.exists())

    def test_record_failure_restores_pdf_and_removes_new_note(self):
        real_open = Path.open

        def fail_record(path, *args, **kwargs):
            if path.suffix == ".json" and args and args[0] == "x":
                raise OSError("record failure")
            return real_open(path, *args, **kwargs)

        with patch.object(Path, "open", fail_record):
            with self.assertRaises(OSError):
                intake.commit(self.pdf, "paper", self.note_text, root=self.root)
        self.assertTrue(self.pdf.exists())
        self.assertFalse((self.root / "Literature Notes" / "Papers" / "paper.md").exists())

    def attachment_fixture(self):
        primary = self.root / "PDFs" / "Ingested" / "paper.pdf"
        primary.parent.mkdir(parents=True, exist_ok=True)
        primary.write_bytes(b"%PDF-1.4\nprimary")
        supplementary = self.inbox / "SI - paper.pdf"
        supplementary.write_bytes(b"%PDF-1.4\nsupplement")
        note = self.root / "Literature Notes" / "Papers" / "paper.md"
        note.parent.mkdir(parents=True)
        human = {"My Notes", "Figure Screenshots", "Connections to Other Papers"}
        body = []
        for heading in intake.PAPER_SECTIONS:
            if heading == "Suggested Topics":
                body.extend(["## Claims to Verify Manually", "", "- Old SI filename warning.", ""])
            body.extend([f"## {heading}", ""])
            if heading in human:
                body.append(f"Human-authored {heading} text.")
            elif heading == "Figures Worth Reviewing":
                body.append("Primary-paper figure note.")
            else:
                body.append("Not stated.")
            body.append("")
        note_text = (
            "---\n"
            "title: Paper\n"
            "source_type: paper\n"
            "document_type: primary\n"
            "source_file_count: 1\n"
            'summary_scope: "Primary paper"\n'
            'page_scope: "pp. 1–2"\n'
            'pdf: "PDFs/Ingested/paper.pdf"\n'
            "supplementary_pdf: null\n"
            "metadata_review_needed: true\n"
            "---\n\n" + "\n".join(body)
        )
        note.write_text(note_text, encoding="utf-8")
        record = self.root / "data" / "processing_records" / "paper.json"
        record.parent.mkdir(parents=True)
        record_data = {
            "source_pdf_filename": primary.name,
            "source_pdf_filenames": [primary.name],
            "resulting_pdf_path": "PDFs/Ingested/paper.pdf",
            "generated_note_path": "Literature Notes/Papers/paper.md",
            "success_status": "success",
            "warnings": ["Old unmatched SI warning."],
        }
        record.write_text(json.dumps(record_data), encoding="utf-8")
        section = (
            "## Supplementary Information Used\n\n"
            "- **File:** SI - paper.pdf\n"
            "- **Material consulted:** All pages.\n"
            "- **Important contributions to this note:** Adds the tutorial details.\n"
        )
        update = {
            "summary_scope": "Primary paper and paired SI",
            "page_scope": "pp. 1–2; SI PDF pages 1–3",
            "resolved_provenance_warnings": ["Old unmatched SI warning."],
            "replacements": [{"old": "Old SI filename warning.", "new": "The SI was attached and reviewed."}],
        }
        return primary, supplementary, note, record, note_text, record.read_text(encoding="utf-8"), section, update

    def test_attach_separated_si_preserves_human_sections_and_updates_provenance(self):
        primary, supplementary, note, record, original_note, _, section, update = self.attachment_fixture()
        result = intake.attach_supplementary(primary, supplementary, section, update, root=self.root)
        updated_note = note.read_text(encoding="utf-8")
        updated_record = json.loads(record.read_text(encoding="utf-8"))
        self.assertFalse(supplementary.exists())
        self.assertTrue((self.root / "PDFs" / "Ingested" / supplementary.name).exists())
        self.assertEqual(intake._frontmatter_value(updated_note, "source_file_count"), "2")
        self.assertEqual(intake._frontmatter_value(updated_note, "supplementary_pdf"), f"PDFs/Ingested/{supplementary.name}")
        self.assertEqual(intake._frontmatter_pdf_values(updated_note), [
            "PDFs/Ingested/paper.pdf", f"PDFs/Ingested/{supplementary.name}",
        ])
        self.assertIn("## Supplementary Information Used", updated_note)
        self.assertNotIn("**PDF:**", updated_note)
        self.assertNotIn("**Supplementary PDF:**", updated_note)
        self.assertIn("The SI was attached and reviewed.", updated_note)
        for heading in ("My Notes", "Figure Screenshots", "Connections to Other Papers"):
            self.assertEqual(intake._section_body(updated_note, heading), intake._section_body(original_note, heading))
        self.assertEqual(updated_record["source_pdf_filenames"], [primary.name, supplementary.name])
        self.assertEqual(len(updated_record["supplementary_pdf_sha256"]), 64)
        self.assertEqual(updated_record["warnings"], [])
        self.assertEqual(updated_record["resolved_warnings"][0]["warning"], "Old unmatched SI warning.")
        self.assertEqual(result["success_status"], "success")

    def test_repair_moves_links_to_property_and_preserves_human_sections(self):
        ingested = self.root / "PDFs" / "Ingested"
        ingested.mkdir(parents=True)
        actual_pdf = ingested / "paper name.pdf"
        actual_pdf.write_bytes(b"%PDF-1.4\nfixture")
        note = self.root / "Literature Notes" / "Papers" / "paper.md"
        note.parent.mkdir(parents=True)
        human = {"My Notes", "Figure Screenshots", "Connections to Other Papers"}
        body = "\n".join(f"## {heading}\n\n" + ("Human section.\n" if heading in human else "Not stated.\n") for heading in intake.PAPER_SECTIONS)
        note.write_text(
            "---\ntitle: Paper\nsource_type: paper\nmetadata_review_needed: true\npdf: ../../PDFs/Inbox/paper name.pdf\nsupplementary_pdf: null\n---\n\n# Paper\n\n" + body,
            encoding="utf-8",
        )
        before = note.read_text(encoding="utf-8")
        result = intake.repair_pdf_links(self.root)
        after = note.read_text(encoding="utf-8")
        self.assertEqual(result["count"], 1)
        self.assertEqual(intake._frontmatter_pdf_values(after), ["PDFs/Ingested/paper name.pdf"])
        self.assertNotIn("**PDF:**", after)
        for heading in human:
            self.assertEqual(intake._section_body(before, heading), intake._section_body(after, heading))

    def test_attach_failure_leaves_note_record_and_si_unchanged(self):
        primary, supplementary, note, record, original_note, original_record, section, update = self.attachment_fixture()
        real_rename = intake.os.rename

        def fail_si_move(source, destination):
            if Path(source) == supplementary:
                raise OSError("simulated SI move failure")
            return real_rename(source, destination)

        with patch.object(intake.os, "rename", fail_si_move):
            with self.assertRaises(OSError):
                intake.attach_supplementary(primary, supplementary, section, update, root=self.root)
        self.assertEqual(note.read_text(encoding="utf-8"), original_note)
        self.assertEqual(record.read_text(encoding="utf-8"), original_record)
        self.assertTrue(supplementary.exists())
        self.assertFalse((self.root / "PDFs" / "Ingested" / supplementary.name).exists())


if __name__ == "__main__":
    unittest.main()
