"""Checks that one YAML edit updates the domain-specific workflow surfaces."""

import tempfile
import unittest
from pathlib import Path

import setup_research as setup


class SetupResearchTests(unittest.TestCase):
    def test_reconfigure_and_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [setup.SKILL / "SKILL.md", setup.SKILL / "note-schema.md", setup.SKILL / "research-context.md",
                     setup.HELPER, setup.BASE, setup.DASHBOARD, *setup.TEMPLATES.glob("*Note Template.md")]
            for source in paths:
                target = root / source.relative_to(setup.ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            old = {name: getattr(setup, name) for name in ("ROOT", "SKILL", "HELPER", "BASE", "DASHBOARD", "TEMPLATES")}
            try:
                setup.ROOT = root
                setup.SKILL = root / ".agents/skills/literature-intake"
                setup.HELPER = root / "scripts/literature_intake_io.py"
                setup.BASE = root / "Literature Notes/Literature Database.base"
                setup.DASHBOARD = root / "Literature Notes/Literature Dashboard.md"
                setup.TEMPLATES = root / "Literature Notes/Templates"
                config = root / "research-config.yaml"
                config.write_text(
                    "research_context: |\n  Research on ecosystems.\n"
                    "domain_properties:\n"
                    "  - name: study_organisms\n    type: list\n    description: Organisms actually studied.\n"
                    "  - name: habitats\n    type: list\n    description: Habitats actually studied.\n"
                    "  - name: field_notes\n    type: string\n    description: Field observations.\n"
                    "domain_view_name: Ecology Details\n"
                    "formatting_rules:\n"
                    "  - '**LaTeX commands:** Use proper backslashes for symbols and functions.'\n"
                    "  - '**Species names:** Italicize scientific names.'\n", encoding="utf-8")
                self.assertTrue(setup.apply(config))
                self.assertEqual(setup.apply(config, dry_run=True), [])
                base = setup.BASE.read_text(encoding="utf-8")
                self.assertIn("name: Ecology Details", base)
                self.assertIn("      - field_notes", base)
                self.assertNotIn("morphologies", base)
                self.assertIn("study_organisms", setup.HELPER.read_text(encoding="utf-8"))
                self.assertNotIn("polymer_system", setup.HELPER.read_text(encoding="utf-8"))
                for template in setup.TEMPLATES.glob("*Note Template.md"):
                    text = template.read_text(encoding="utf-8")
                    self.assertIn('field_notes: ""', text)
                    self.assertNotIn("polymer_system:", text)
                    self.assertNotIn("research_topics:", text)
                self.assertIn("Organisms actually studied", (setup.SKILL / "note-schema.md").read_text(encoding="utf-8"))
                self.assertIn("Ecosystems", (setup.SKILL / "research-context.md").read_text(encoding="utf-8").title())
                self.assertIn("Ecology Details", setup.DASHBOARD.read_text(encoding="utf-8"))
                skill = (setup.SKILL / "SKILL.md").read_text(encoding="utf-8")
                self.assertEqual(skill.count("**LaTeX commands:**"), 1)
                self.assertEqual(skill.count("**Species names:**"), 1)
                config.write_text(
                    "research_context: |\n  Research on climate.\n"
                    "domain_properties:\n"
                    "  - name: climate_region\n    type: list\n    description: Region actually studied.\n"
                    "  - name: research_topics\n    type: string\n    description: Main topic.\n"
                    "domain_view_name: Climate\nformatting_rules:\n", encoding="utf-8")
                setup.apply(config)
                self.assertEqual(setup.apply(config, dry_run=True), [])
                self.assertNotIn("study_organisms", setup.BASE.read_text(encoding="utf-8"))
                self.assertIn("climate_region", setup.BASE.read_text(encoding="utf-8"))
                self.assertIn("Climate", setup.DASHBOARD.read_text(encoding="utf-8"))
                self.assertNotIn("**Species names:**", (setup.SKILL / "SKILL.md").read_text(encoding="utf-8"))
                import runpy
                helper = runpy.run_path(str(setup.HELPER))
                note = '---\nauthors: []\nresearch_topics: "climate"\n---\n'
                self.assertEqual(helper["_vault_connections"](note, root / "new.md", root), "None identified at intake.")
            finally:
                for name, value in old.items():
                    setattr(setup, name, value)


if __name__ == "__main__":
    unittest.main()
