# Reference metadata verification

Use reference-manager metadata only for the primary journal article in a source package, including review articles. Skip supplementary PDFs, textbooks, and theses. The selected PDF package remains the only source for scientific claims. Reference records supply bibliographic fields only; never use their abstracts, notes, tags, or narrative fields in a summary.

Run `python scripts/reference_metadata.py --check-source` to inspect available Zotero and Mendeley sources. By default, `--provider auto` tries available Zotero sources, then Mendeley sources. Use `--provider zotero` or `--provider mendeley` when the user has chosen a manager. An available API is used before its local export, so regular manual export is optional. A local export remains a fallback when an API request fails or has no confident match. In Codex, a restricted command can block the API call while still reading a local export. If a lookup warns `API lookup failed: URLError`, rerun it with network-enabled command execution before treating the export result as the intended API lookup. An API match has `export_path: null`. API credentials are never written to request files, notes, or provenance.

Supported sources:

- Zotero CSL-JSON at `data/zotero-export.json`, or Zotero Web API v3 when `ZOTERO_API_KEY` and `ZOTERO_USER_ID` are set.
- Mendeley CSL-JSON at `data/mendeley-export.json` or BibTeX at `data/mendeley-export.bib`, or the user's Mendeley Documents API when `MENDELEY_ACCESS_TOKEN` is set. The token must authorize access to the user's documents. The helper does not perform OAuth login or token refresh.

## Configure the Zotero Web API

1. Sign in to [Zotero's API Keys page](https://www.zotero.org/settings/keys). Copy the numeric **user ID** shown there; it is not your username. Create a **new private key** for this workflow. Give it read access to your personal library. The helper sends only GET requests for item metadata and does not need write, notes, or file access. Copy the key when it is displayed.
2. Set `ZOTERO_USER_ID` to that number and `ZOTERO_API_KEY` to the new key under Windows “Edit environment variables for your account.” The helper reads these saved user variables when its process does not already have them, including from an already-running Codex app. An explicitly set process value takes precedence. Setting `$env:` values in a separate PowerShell window affects that window and its child processes only. The helper does **not** load `.env` files.
3. For a one-time manual run from the repository root, use the same PowerShell window for setup and the helper:

   ```powershell
   $env:ZOTERO_USER_ID = '123456'     # replace with your numeric Zotero user ID
   $env:ZOTERO_API_KEY = 'your-key'    # replace with your private API key
   python scripts/reference_metadata.py --provider zotero --check-source
   ```

   `api_status: "configured_unverified"` means the variables are present; `--check-source` does not contact Zotero or validate the key. Run this check from the same app or terminal that will perform intake. Do not print or share the key.
4. Verify that the key works and belongs to the expected account, without placing it in a URL:

   ```powershell
   $headers = @{ 'Zotero-API-Key' = $env:ZOTERO_API_KEY; 'Zotero-API-Version' = '3' }
   $keyInfo = Invoke-RestMethod -Uri 'https://api.zotero.org/keys/current' -Headers $headers
   $keyInfo.userID
   $keyInfo.access.user.library
   ```

   The returned number should equal `ZOTERO_USER_ID`, and the library-access value should be `True`. A 403 response usually means the key is invalid or lacks permission to read this library. A successful key check does not prove that a particular article is in the online library; Zotero Desktop must sync it to zotero.org for the Web API to find it.

For an end-to-end lookup, create `data/tmp/zotero-check.json` using the title and DOI of an article already in your Zotero library:

```json
{"source_type": "paper", "title": "Exact Article Title", "doi": "10.1000/example"}
```

Run `python scripts/reference_metadata.py data/tmp/zotero-check.json --provider zotero`. A matched API item has `status: "matched"`, `provider: "zotero"`, and `export_path: null`; a non-null `export_path` means the local export supplied the match. Never put the API key in the request JSON, a note, a commit, or a chat message.

After reading PDF-visible title, authors, year, journal, and DOI, write a small request JSON under `data/tmp/` with `source_type` (`paper` or `review`) and those fields. Run `python scripts/reference_metadata.py data/tmp/<request.json> --output data/tmp/<lookup.json>` (and `--provider ...` if desired). Only these bibliographic fields are used for matching. Matching prefers exact DOI, then exact normalized title, then a unique high-similarity title supported by year and first-author checks. Duplicate candidates are narrowed by PDF-visible year and first author. Never guess when the result is ambiguous or conflicting.

The result always has `status`, `provider`, `match_method`, `item_key`, `item_type`, `metadata`, `metadata_review_needed`, `missing_fields`, `conflicting_fields`, export details, `stale`, and `warnings`. Use a matched record's title, authors, year, journal, and DOI only. Set the note's `metadata_source` to its provider and populate `reference_provider`, `reference_item_key`, `reference_match_method`, and local export timestamp/age properties from the result. A source older than 30 days is stale and requires a visible warning and metadata review. API results have null export timestamps and are not called stale.

For `not_found`, `ambiguous`, `conflict`, or `unavailable`, continue with only bibliographic metadata clearly visible in the PDF. Set `metadata_source: "PDF"`, `metadata_review_needed: true`, leave uncertain fields empty, and put the reason/warnings in the note and provenance. The result uses `provider: pdf_fallback` in these cases. A matched record missing fields may be supplemented only with clearly visible PDF values and should retain a review warning. Pass the lookup JSON to intake commit via `--metadata-lookup-file`; pass the request JSON via `--temporary-file`. Successful commit removes both scratch files.
