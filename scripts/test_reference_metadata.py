"""Focused tests for the two local formats and API adapters."""

import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference_metadata as refs


REQUEST = {"source_type": "paper", "title": "A Polymer Study", "authors": ["Ada Author"],
           "year": 2024, "journal": "Example Journal", "doi": "10.1000/example"}
CSL_ITEM = {"id": "ABC123", "type": "article-journal", "title": "A Polymer Study",
            "author": [{"given": "Ada", "family": "Author"}], "issued": {"date-parts": [[2024]]},
            "container-title": "Example Journal", "DOI": "10.1000/example"}


class ReferenceMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_saved_windows_user_variables_are_available_to_intake_process(self):
        registry_values = {"ZOTERO_USER_ID": "42", "ZOTERO_API_KEY": "private-key"}
        registry = SimpleNamespace(
            HKEY_CURRENT_USER=1,
            OpenKey=MagicMock(),
            QueryValueEx=lambda _key, name: (registry_values[name], 1),
        )
        with patch.dict(os.environ, {}, clear=True), patch.object(refs.sys, "platform", "win32"), \
                patch.dict(sys.modules, {"winreg": registry}):
            provider = refs.ZoteroProvider(self.root / "missing.json")
            self.assertEqual(provider.user_id, "42")
            self.assertTrue(provider.inspect_source()["api_available"])
            os.environ["ZOTERO_USER_ID"] = "99"
            self.assertEqual(refs._credential("ZOTERO_USER_ID"), "99")

    def test_zotero_csl_export_matches_with_standard_shape_and_stale_flag(self):
        path = self.root / "zotero-export.json"
        path.write_text(json.dumps([CSL_ITEM]), encoding="utf-8")
        now = datetime(2026, 10, 2, tzinfo=timezone.utc)
        old = (now - timedelta(days=31)).timestamp()
        os.utime(path, (old, old))
        result = refs.ZoteroProvider(path, api_key="", user_id="", now=now).lookup(REQUEST)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["provider"], "zotero")
        self.assertEqual(result["match_method"], "exact-doi")
        self.assertEqual(result["item_key"], "ABC123")
        self.assertEqual(result["item_type"], "article-journal")
        self.assertEqual(result["metadata"]["authors"], ["Ada Author"])
        self.assertEqual(result["export_age_days"], 31)
        self.assertTrue(result["metadata_review_needed"])

    def test_mendeley_bibtex_and_csl_exports(self):
        bib = self.root / "mendeley-export.bib"
        bib.write_text('@article{bib-key, title={A {Polymer} Study}, author={Ada Author and Bea Writer}, '
                       'year={2024}, journal={Example Journal}, doi={10.1000/example}}', encoding="utf-8")
        result = refs.MendeleyProvider([bib], access_token="").lookup(REQUEST)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["provider"], "mendeley")
        self.assertEqual(result["metadata"]["authors"], ["Ada Author", "Bea Writer"])
        json_path = self.root / "mendeley-export.json"
        json_path.write_text(json.dumps([CSL_ITEM]), encoding="utf-8")
        result = refs.MendeleyProvider([json_path], access_token="").lookup(REQUEST)
        self.assertEqual(result["status"], "matched")
        json_path.write_text("invalid JSON", encoding="utf-8")
        result = refs.MendeleyProvider([json_path, bib], access_token="").lookup(REQUEST)
        self.assertEqual(result["status"], "matched")
        self.assertTrue(any("could not be read" in warning for warning in result["warnings"]))

    def test_zotero_api_and_mendeley_api_use_the_same_result_contract(self):
        zotero_item = {"key": "ZOTERO1", "data": {"itemType": "journalArticle", "title": "A Polymer Study",
                       "creators": [{"creatorType": "author", "firstName": "Ada", "lastName": "Author"}],
                       "date": "2024", "publicationTitle": "Example Journal", "DOI": "10.1000/example"}}
        mendeley_item = {"id": "MEND1", "type": "journal", "title": "A Polymer Study",
                         "authors": [{"first_name": "Ada", "last_name": "Author"}], "year": 2024,
                         "source": "Example Journal", "identifiers": {"doi": "10.1000/example"}}
        with patch.object(refs, "_http_json", return_value=([zotero_item], None)) as api:
            zotero = refs.ZoteroProvider(self.root / "missing.json", api_key="secret", user_id="42").lookup(REQUEST)
            self.assertIn("api.zotero.org/users/42/items/top", api.call_args.args[0])
        with patch.object(refs, "_http_json", return_value=([mendeley_item], None)) as api:
            mendeley = refs.MendeleyProvider([self.root / "missing.json"], access_token="secret").lookup(REQUEST)
            self.assertIn("api.mendeley.com/documents", api.call_args.args[0])
        for result, provider in ((zotero, "zotero"), (mendeley, "mendeley")):
            self.assertEqual(result["status"], "matched")
            self.assertEqual(result["provider"], provider)
            self.assertEqual(result["metadata"]["doi"], "10.1000/example")
            self.assertEqual(result["metadata"]["authors"], ["Ada Author"])
            self.assertIsNone(result["export_path"])

    def test_pdf_fallback_on_missing_export_and_conflicting_doi(self):
        missing = refs.ZoteroProvider(self.root / "missing.json", api_key="", user_id="").lookup(REQUEST)
        self.assertEqual(missing["status"], "unavailable")
        self.assertEqual(missing["provider"], "pdf_fallback")
        self.assertEqual(missing["metadata"]["title"], REQUEST["title"])
        path = self.root / "zotero-export.json"
        path.write_text(json.dumps([{**CSL_ITEM, "DOI": "10.1000/other"}]), encoding="utf-8")
        conflict = refs.ZoteroProvider(path, api_key="", user_id="").lookup(REQUEST)
        self.assertEqual(conflict["status"], "conflict")
        self.assertEqual(conflict["conflicting_fields"], ["doi"])
        self.assertEqual(conflict["metadata"]["doi"], REQUEST["doi"])

    def test_api_failure_uses_local_export_and_records_review_warning(self):
        path = self.root / "zotero-export.json"
        path.write_text(json.dumps([CSL_ITEM]), encoding="utf-8")
        with patch.object(refs, "_http_json", side_effect=URLError("offline")):
            result = refs.ZoteroProvider(path, api_key="secret", user_id="42").lookup(REQUEST)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["provider"], "zotero")
        self.assertTrue(result["metadata_review_needed"])
        self.assertTrue(any("API lookup failed" in warning for warning in result["warnings"]))

    def test_auto_tries_mendeley_after_unmatched_zotero_and_skips_chapters(self):
        zotero = self.root / "zotero.json"
        mendeley = self.root / "mendeley.json"
        zotero.write_text("[]", encoding="utf-8")
        mendeley.write_text(json.dumps([CSL_ITEM]), encoding="utf-8")
        with patch.dict(os.environ, {"ZOTERO_API_KEY": "", "ZOTERO_USER_ID": "", "MENDELEY_ACCESS_TOKEN": ""}):
            matched = refs.lookup(REQUEST, "auto", zotero_export=zotero, mendeley_export=mendeley)
            skipped = refs.lookup({**REQUEST, "source_type": "textbook-chapter"}, "auto",
                                  zotero_export=zotero, mendeley_export=mendeley)
        self.assertEqual(matched["provider"], "mendeley")
        self.assertEqual(skipped["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
