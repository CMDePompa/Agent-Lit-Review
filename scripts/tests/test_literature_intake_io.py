import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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
        self.note_text = "---\ntitle: ''\nsource_type: paper\nmetadata_review_needed: true\npdf: ../../PDFs/Inbox/paper.pdf\n---\n" + "\n".join(f"## {h}\n\n" + ("" if h in human else "Not stated.\n") for h in intake.PAPER_SECTIONS)

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
        self.assertEqual(json.loads((self.root / "data" / "intake_failures.json").read_text(encoding="utf-8"))["items"]["a.pdf"]["reason"],
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
        intake.defer_pdf(self.pdf, "Metadata export missing.", self.root)
        intake.commit(self.pdf, "paper", self.note_text, no_move=True, root=self.root)
        queue = intake.inspect_queue(self.root)
        self.assertEqual(queue["needs_attention"], [])
        self.assertEqual(queue["already_processed"], ["paper.pdf"])
        self.assertEqual(queue["eligible"], [])
        self.assertIn("No source packages are currently flagged.", dashboard.read_text(encoding="utf-8"))

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

    def test_review_filename_requires_review_source_type(self):
        review_pdf = self.inbox / "REVIEW - 2020 Author - Title.pdf"
        review_pdf.write_bytes(b"%PDF-1.4\nfixture")
        review_note = self.note_text.replace("source_type: paper", "source_type: review")
        with self.assertRaises(ValueError):
            intake.commit(review_pdf, review_pdf.stem, self.note_text, no_move=True, root=self.root)
        with self.assertRaises(ValueError):
            intake.commit(self.pdf, "paper", review_note, no_move=True, root=self.root)
        result = intake.commit(review_pdf, review_pdf.stem, review_note, no_move=True, root=self.root)
        saved = (self.root / result["generated_note_path"]).read_text(encoding="utf-8")
        self.assertEqual(intake._frontmatter_value(saved, "source_type"), "review")
        self.assertTrue(review_pdf.exists())

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
