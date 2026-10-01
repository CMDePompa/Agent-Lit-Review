"""Resolve article metadata from a local Zotero CSL-JSON export.

Read-only: this helper never contacts Zotero, the web, or an external API.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT = ROOT / "data" / "zotero-export.json"
ARTICLE_TYPES = {"article", "article-journal"}
STALE_DAYS = 30


def normalize(value):
    value = unicodedata.normalize("NFKD", str(value or "")).casefold()
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


def normalize_doi(value):
    value = str(value or "").strip().casefold()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
    return value.removeprefix("doi:").strip().rstrip(".,; ")


def year_from_item(item):
    parts = item.get("issued", {}).get("date-parts", [[]])
    if parts and parts[0]:
        try:
            return int(parts[0][0])
        except (TypeError, ValueError):
            pass
    match = re.search(r"\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b", str(item.get("issued", "")))
    return int(match.group(1)) if match else None


def authors_from_item(item):
    result = []
    for person in item.get("author", []) or []:
        name = person.get("literal") or " ".join(x for x in (person.get("given"), person.get("family")) if x)
        if name.strip():
            result.append(name.strip())
    return result


def container_from_item(item):
    value = item.get("container-title") or item.get("journalAbbreviation") or ""
    return value[0] if isinstance(value, list) and value else value if isinstance(value, str) else ""


def item_metadata(item):
    item_id = str(item.get("id") or item.get("key") or "")
    if "/" in item_id:
        item_id = item_id.rstrip("/").split("/")[-1]
    return {
        "title": str(item.get("title") or "").strip(),
        "authors": authors_from_item(item),
        "year": year_from_item(item),
        "journal": str(container_from_item(item)).strip(),
        "doi": normalize_doi(item.get("DOI") or item.get("doi")),
        "zotero_item_key": item_id or None,
        "zotero_item_type": str(item.get("type") or item.get("itemType") or ""),
    }


def author_family(name):
    parts = re.sub(r"[,;]", " ", str(name or "")).split()
    return normalize(parts[-1]) if parts else ""


def score_title(title, item):
    return difflib.SequenceMatcher(None, normalize(title), normalize(item.get("title", ""))).ratio()


def inspect_export(path, now=None):
    path = Path(path)
    if not path.is_file():
        return {"available": False, "status": "unavailable", "export_path": str(path),
                "warnings": ["Zotero metadata retrieval unavailable: data/zotero-export.json was not found."]}
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    now = now or datetime.now(timezone.utc)
    age_days = max(0, int((now - modified).total_seconds() // 86400))
    stale = age_days > STALE_DAYS
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"available": False, "status": "unavailable", "export_path": str(path),
                "warnings": [f"Zotero export could not be read as CSL-JSON: {exc}"]}
    if isinstance(data, dict):
        data = data.get("items", data.get("data"))
    if not isinstance(data, list):
        return {"available": False, "status": "unavailable", "export_path": str(path),
                "warnings": ["Zotero export is not a CSL-JSON item list."]}
    return {"available": True, "status": "available", "items": data, "export_path": str(path),
            "export_modified_at": modified.isoformat(timespec="seconds"), "export_age_days": age_days,
            "stale": stale, "warnings": [f"Zotero export is stale ({age_days} days old; threshold is {STALE_DAYS} days)."] if stale else []}


def lookup(request, export_path=DEFAULT_EXPORT, now=None):
    source_type = str(request.get("source_type") or "").casefold()
    if source_type not in {"paper", "review"}:
        return {"status": "skipped", "reason": "Zotero lookup is limited to primary journal articles; supplementary PDFs, textbooks, and theses are skipped.", "metadata_review_needed": False, "warnings": []}
    title = str(request.get("title") or "").strip()
    if not title:
        return {"status": "not_found", "reason": "A title read from the article PDF is required for Zotero matching.", "metadata_review_needed": True,
                "warnings": ["Zotero metadata lookup was not attempted because no title could be established from the PDF."]}
    status = inspect_export(export_path, now=now)
    if not status["available"]:
        return {**status, "metadata_source": "PDF", "metadata_review_needed": True,
                "reason": "Continuing with metadata visible in the PDF because no readable Zotero export is available."}

    eligible = [item for item in status["items"] if str(item.get("type") or item.get("itemType") or "").casefold() in ARTICLE_TYPES]
    doi = normalize_doi(request.get("doi"))
    matches = []
    method = ""
    if doi:
        matches = [item for item in eligible if normalize_doi(item.get("DOI") or item.get("doi")) == doi]
        method = "exact-doi"
    if not matches:
        target_title = normalize(title)
        exact = [item for item in eligible if normalize(item.get("title")) == target_title]
        if exact:
            matches = exact
            method = "exact-title"
        else:
            scored = sorted(((score_title(title, item), item) for item in eligible), key=lambda pair: pair[0], reverse=True)
            if scored and scored[0][0] >= 0.93 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.05):
                candidate = scored[0][1]
                candidate_year = year_from_item(candidate)
                candidate_authors = authors_from_item(candidate)
                year_ok = request.get("year") is None or candidate_year == request.get("year")
                request_authors = request.get("authors") or []
                author_ok = not request_authors or not candidate_authors or author_family(request_authors[0]) == author_family(candidate_authors[0])
                if year_ok and author_ok:
                    matches = [candidate]
                    method = f"title-similarity-{scored[0][0]:.3f}-year-author-checked"

    # Use PDF-visible year and first author to disambiguate duplicate exact titles.
    if len(matches) > 1:
        requested_authors = request.get("authors") or []
        narrowed = matches
        if request.get("year") is not None:
            by_year = [item for item in narrowed if year_from_item(item) == request.get("year")]
            if by_year:
                narrowed = by_year
        if requested_authors:
            expected_family = author_family(requested_authors[0])
            by_author = [item for item in narrowed if authors_from_item(item) and author_family(authors_from_item(item)[0]) == expected_family]
            if by_author:
                narrowed = by_author
        matches = narrowed

    if len(matches) != 1:
        reason = "No confident journal-article match was found in the Zotero export." if not matches else "Multiple Zotero article records match; metadata resolution is ambiguous."
        warnings = list(status["warnings"]) + [reason]
        return {"status": "not_found" if not matches else "ambiguous", "reason": reason,
                "export_path": status["export_path"], "export_modified_at": status["export_modified_at"],
                "export_age_days": status["export_age_days"], "stale": status["stale"],
                "metadata_review_needed": True, "warnings": warnings}

    resolved = item_metadata(matches[0])
    requested_doi = normalize_doi(request.get("doi"))
    if requested_doi and resolved["doi"] and requested_doi != resolved["doi"]:
        warning = "The Zotero record DOI conflicts with the DOI visible in the PDF; refusing metadata substitution."
        return {"status": "conflict", "reason": warning, "export_path": status["export_path"],
                "export_modified_at": status["export_modified_at"], "export_age_days": status["export_age_days"],
                "stale": status["stale"], "metadata_review_needed": True,
                "conflicting_fields": ["doi"], "warnings": list(status["warnings"]) + [warning]}
    missing = [field for field in ("title", "authors", "year", "journal", "doi") if not resolved.get(field)]
    warnings = list(status["warnings"])
    if missing:
        warnings.append("Matched Zotero record lacks: " + ", ".join(missing) + ".")
    conflicts = []
    for field in ("title", "year", "journal"):
        pdf_value = request.get(field)
        zotero_value = resolved.get(field)
        differs = (normalize(pdf_value) != normalize(zotero_value)) if field != "year" and pdf_value and zotero_value else (pdf_value != zotero_value if field == "year" and pdf_value is not None and zotero_value is not None else False)
        if differs:
            conflicts.append(field)
    if conflicts:
        warnings.append("PDF-visible metadata differs from Zotero for: " + ", ".join(conflicts) + "; review before relying on those fields.")
    return {"status": "matched", "match_method": method, "zotero_item_key": resolved["zotero_item_key"], "metadata": resolved,
            "metadata_review_needed": bool(missing or status["stale"] or conflicts), "missing_fields": missing,
            "conflicting_fields": conflicts,
            "export_path": status["export_path"], "export_modified_at": status["export_modified_at"],
            "export_age_days": status["export_age_days"], "stale": status["stale"], "warnings": warnings}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_json", type=Path, nargs="?", help="JSON containing source_type and metadata read from the PDF")
    parser.add_argument("--export", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--check-export", action="store_true", help="Report whether the CSL-JSON export is available and stale")
    parser.add_argument("--output", type=Path, help="Also write the result JSON to this path")
    args = parser.parse_args(argv)
    if args.check_export:
        result = inspect_export(args.export)
        result.pop("items", None)
    else:
        if args.request_json is None:
            parser.error("request_json is required unless --check-export is used")
        request = json.loads(args.request_json.read_text(encoding="utf-8"))
        result = lookup(request, args.export)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
