"""Read-only bibliographic lookup in Zotero or Mendeley libraries.

Only a configured reference-manager API is contacted. No PDF or note content is sent.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import unicodedata
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STALE_DAYS = 30
FIELDS = ("title", "authors", "year", "journal", "doi")
ARTICLE_TYPES = {"article", "article-journal", "journalarticle", "journal"}


def normalize(value):
    value = unicodedata.normalize("NFKD", str(value or "")).casefold()
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


def normalize_doi(value):
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", str(value or "").strip().casefold())
    return value.removeprefix("doi:").strip().rstrip(".,; ")


def _year(value):
    if isinstance(value, dict):
        value = value.get("date-parts", [[]])
        value = value[0][0] if value and value[0] else None
    match = re.search(r"\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b", str(value or ""))
    return int(match.group(1)) if match else None


def _authors(people):
    result = []
    for person in people or []:
        if isinstance(person, str):
            name = person
            if "," in name:
                family, given = name.split(",", 1)
                name = f"{given.strip()} {family.strip()}"
        else:
            name = person.get("literal") or person.get("name") or " ".join(str(x) for x in (
                person.get("given") or person.get("first_name") or person.get("firstName"),
                person.get("family") or person.get("last_name") or person.get("lastName")) if x)
        if name.strip():
            result.append(name.strip())
    return result


def _first_family(name):
    parts = re.sub(r"[,;]", " ", str(name or "")).split()
    return normalize(parts[-1]) if parts else ""


def _standard_item(item, provider):
    if provider == "zotero" and isinstance(item.get("data"), dict):
        item = {**item["data"], "key": item.get("key") or item["data"].get("key")}
    people = item.get("author") or item.get("authors")
    if people is None:
        people = [creator for creator in item.get("creators", [])
                  if creator.get("creatorType") == "author"]
    identifiers = item.get("identifiers") or {}
    journal = item.get("container-title") or item.get("source") or item.get("publicationTitle") or item.get("journalAbbreviation") or ""
    if isinstance(journal, list):
        journal = journal[0] if journal else ""
    kind = str(item.get("type") or item.get("itemType") or "").casefold()
    if kind in {"journalarticle", "journal", "article"}:
        kind = "article-journal"
    return {
        "item_key": str(item.get("key") or item.get("id") or "").rstrip("/").split("/")[-1] or None,
        "item_type": kind,
        "metadata": {
            "title": str(item.get("title") or "").strip(),
            "authors": _authors(people),
            "year": _year(item.get("issued") or item.get("year") or item.get("date") or item.get("published")),
            "journal": str(journal).strip(),
            "doi": normalize_doi(item.get("DOI") or item.get("doi") or identifiers.get("doi")),
        },
    }


def _bibtex_items(text):
    """Parse ordinary BibTeX entries, including nested braced field values."""
    items = []
    for match in re.finditer(r"@([\w-]+)\s*\{\s*([^,]+)\s*,", text):
        pos = match.end()
        fields = {}
        while pos < len(text):
            ws = re.match(r"\s*,?\s*", text[pos:])
            pos += ws.end()
            if text[pos:pos + 1] == "}":
                break
            key_match = re.match(r"([\w-]+)\s*=\s*", text[pos:])
            if not key_match:
                break
            key = key_match.group(1).casefold()
            pos += key_match.end()
            if text[pos:pos + 1] in "{\"":
                opening = text[pos]
                closing = "}" if opening == "{" else '"'
                pos += 1
                start = pos
                depth = 1
                while pos < len(text) and depth:
                    if opening == "{" and text[pos] == "{":
                        depth += 1
                    elif text[pos] == closing and (pos == 0 or text[pos - 1] != "\\"):
                        depth -= 1
                    pos += 1
                value = text[start:pos - 1]
            else:
                end = re.search(r"[,}]", text[pos:])
                value = text[pos:pos + end.start()].strip() if end else text[pos:].strip()
                pos += end.start() if end else len(text) - pos
            fields[key] = re.sub(r"[{}]", "", value).strip()
        kind = match.group(1).casefold()
        items.append({"id": match.group(2).strip(), "type": "article-journal" if kind == "article" else kind,
                      "title": fields.get("title"), "author": [x.strip() for x in re.split(r"\s+and\s+", fields.get("author", "")) if x.strip()],
                      "year": fields.get("year"), "container-title": fields.get("journal"), "DOI": fields.get("doi")})
    return items


def _http_json(url, headers):
    request = Request(url, headers=headers)
    with urlopen(request, timeout=12) as response:
        data = json.load(response)
        links = response.headers.get("Link", "")
    if not isinstance(data, list):
        raise ValueError("API response was not an item list")
    next_url = None
    for part in links.split(","):
        match = re.search(r'<([^>]+)>;\s*rel="?next"?', part)
        if match:
            next_url = match.group(1)
            break
    return data, next_url


def _safe_next(url, host):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != host:
        raise ValueError("API returned an unsafe pagination URL")
    return url


def _display_path(path):
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


class ReferenceProvider(ABC):
    name: str

    @abstractmethod
    def inspect_source(self) -> dict:
        """Report local export and API availability without exposing credentials."""

    @abstractmethod
    def lookup(self, request: dict) -> dict:
        """Return a standardized bibliographic lookup result."""


class _LibraryProvider(ReferenceProvider):
    def __init__(self, export_paths, token=None, now=None):
        self.export_paths = [Path(path) for path in export_paths]
        self.token = token
        self.now = now or datetime.now(timezone.utc)

    def _export(self):
        errors = []
        last_info = None
        for path in self.export_paths:
            if not path.is_file():
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            age = max(0, int((self.now - modified).total_seconds() // 86400))
            info = {"export_path": _display_path(path), "export_modified_at": modified.isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "export_age_days": age, "stale": age > STALE_DAYS}
            last_info = info
            try:
                if path.suffix.casefold() == ".bib":
                    items = _bibtex_items(path.read_text(encoding="utf-8-sig"))
                else:
                    items = json.loads(path.read_text(encoding="utf-8-sig"))
                    if isinstance(items, dict):
                        items = items.get("items", items.get("data"))
                if not isinstance(items, list):
                    raise ValueError("export is not an item list")
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                errors.append(f"{self.name.title()} export could not be read: {exc}")
                continue
            warnings = [f"{self.name.title()} export is stale ({age} days old; threshold is {STALE_DAYS} days)."] if info["stale"] else []
            return items, info, errors + warnings
        if errors:
            return None, last_info, errors
        return None, {"export_path": _display_path(self.export_paths[0]), "export_modified_at": None, "export_age_days": None, "stale": False}, [
            f"{self.name.title()} export was not found."]

    def inspect_source(self):
        items, info, warnings = self._export()
        api_ready = self._api_ready()
        if api_ready and items is None and not any("could not be read" in warning for warning in warnings):
            warnings = []
        return {"provider": self.name, "available": items is not None or api_ready,
                "status": "available" if items is not None else "configured_unverified" if api_ready else "unavailable",
                "local_available": items is not None, "api_available": api_ready,
                "api_status": "configured_unverified" if api_ready else "not_configured", **info, "warnings": warnings}

    def _api_ready(self):
        return bool(self.token)

    @abstractmethod
    def _api_items(self, request):
        pass

    def lookup(self, request):
        if str(request.get("source_type") or "").casefold() not in {"paper", "review", "journal-article"}:
            return _result("skipped", "pdf_fallback", reason="Reference lookup applies only to journal articles.", review=False)
        if not str(request.get("title") or "").strip() and not normalize_doi(request.get("doi")):
            return _result("not_found", "pdf_fallback", metadata=_pdf_metadata(request),
                           reason="PDF title or DOI is required for reference lookup.",
                           warnings=["No PDF title or DOI was available for matching."])
        items, info, warnings = self._export()
        api_error = None
        api_result = None
        # An available API avoids requiring a fresh manual export. The local export remains a fallback.
        if self._api_ready():
            try:
                api_items = self._api_items(request)
                api_result = _match(request, api_items, self.name, {"export_path": None, "export_modified_at": None,
                                                                     "export_age_days": None, "stale": False}, [])
                if api_result["status"] in {"matched", "ambiguous", "conflict"}:
                    return api_result
            except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
                api_error = f"{self.name.title()} API lookup failed: {type(exc).__name__}" + (f" ({exc.code})" if isinstance(exc, HTTPError) else "")
        if items is not None:
            result = _match(request, items, self.name, info, warnings)
            if api_error:
                result["warnings"].append(api_error)
                result["metadata_review_needed"] = True
            return result
        all_warnings = warnings + ([api_error] if api_error else api_result["warnings"] if api_result else [])
        return _result("unavailable" if api_error or not self._api_ready() else "not_found", "pdf_fallback",
                       metadata=_pdf_metadata(request),
                       reason="No usable reference-manager match; use PDF-visible metadata.", warnings=all_warnings, **info)


class ZoteroProvider(_LibraryProvider):
    name = "zotero"

    def __init__(self, export_path=ROOT / "data" / "zotero-export.json", *, api_key=None, user_id=None, now=None):
        self.user_id = user_id if user_id is not None else os.getenv("ZOTERO_USER_ID")
        super().__init__([export_path], api_key if api_key is not None else os.getenv("ZOTERO_API_KEY"), now)

    def _api_ready(self):
        return bool(self.token and self.user_id)

    def _api_items(self, request):
        # Fetch the entire top-level library so DOI matches are not missed by title-only q search.
        url = f"https://api.zotero.org/users/{self.user_id}/items/top?" + urlencode({"format": "json", "limit": 100})
        headers = {"Zotero-API-Key": self.token, "Zotero-API-Version": "3"}
        items = []
        seen = set()
        while url:
            if url in seen:
                raise ValueError("Zotero API pagination repeated a page")
            seen.add(url)
            page, following = _http_json(url, headers)
            items.extend(page)
            url = _safe_next(following, "api.zotero.org") if following else None
        return items


class MendeleyProvider(_LibraryProvider):
    name = "mendeley"

    def __init__(self, export_paths=None, *, access_token=None, now=None):
        paths = export_paths or [ROOT / "data" / "mendeley-export.json", ROOT / "data" / "mendeley-export.bib"]
        super().__init__(paths, access_token if access_token is not None else os.getenv("MENDELEY_ACCESS_TOKEN"), now)

    def _api_items(self, request):
        url = "https://api.mendeley.com/documents?" + urlencode({"view": "bib", "limit": 500})
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.mendeley-document.1+json"}
        items = []
        seen = set()
        while url:
            if url in seen:
                raise ValueError("Mendeley API pagination repeated a page")
            seen.add(url)
            page, following = _http_json(url, headers)
            items.extend(page)
            url = _safe_next(following, "api.mendeley.com") if following else None
        return items


def _result(status, provider, *, method=None, key=None, kind=None, metadata=None, review=True, missing=None,
            conflicts=None, warnings=None, reason=None, export_path=None, export_modified_at=None,
            export_age_days=None, stale=False):
    result = {"status": status, "provider": provider, "match_method": method, "item_key": key, "item_type": kind,
              "metadata": metadata, "metadata_review_needed": review, "missing_fields": missing or [],
              "conflicting_fields": conflicts or [], "export_path": export_path, "export_modified_at": export_modified_at,
              "export_age_days": export_age_days, "stale": stale, "warnings": warnings or []}
    if reason:
        result["reason"] = reason
    return result


def _pdf_metadata(request):
    return {"title": str(request.get("title") or "").strip(),
            "authors": [str(author).strip() for author in (request.get("authors") or []) if str(author).strip()],
            "year": _year(request.get("year")), "journal": str(request.get("journal") or "").strip(),
            "doi": normalize_doi(request.get("doi"))}


def _match(request, raw_items, provider, info, warnings):
    items = [_standard_item(item, provider) for item in raw_items if isinstance(item, dict)]
    items = [item for item in items if item["item_type"] in ARTICLE_TYPES]
    doi = normalize_doi(request.get("doi"))
    title = normalize(request.get("title"))
    matches = [item for item in items if doi and item["metadata"]["doi"] == doi]
    method = "exact-doi" if matches else None
    if not matches and title:
        matches = [item for item in items if normalize(item["metadata"]["title"]) == title]
        method = "exact-title" if matches else None
    if not matches and title:
        scored = sorted(((difflib.SequenceMatcher(None, title, normalize(item["metadata"]["title"])).ratio(), item)
                         for item in items), key=lambda pair: pair[0], reverse=True)
        if scored and scored[0][0] >= 0.93 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.05):
            candidate = scored[0][1]
            wanted_authors = request.get("authors") or []
            actual_authors = candidate["metadata"]["authors"]
            if ((request.get("year") is None or candidate["metadata"]["year"] == _year(request["year"])) and
                    (not wanted_authors or not actual_authors or _first_family(wanted_authors[0]) == _first_family(actual_authors[0]))):
                matches = [candidate]
                method = f"title-similarity-{scored[0][0]:.3f}-year-author-checked"
    if len(matches) > 1:
        if request.get("year") is not None:
            narrowed = [item for item in matches if item["metadata"]["year"] == _year(request["year"])]
            matches = narrowed or matches
        authors = request.get("authors") or []
        if authors:
            narrowed = [item for item in matches if item["metadata"]["authors"] and
                        _first_family(item["metadata"]["authors"][0]) == _first_family(authors[0])]
            matches = narrowed or matches
    if len(matches) != 1:
        status = "ambiguous" if matches else "not_found"
        reason = "Multiple reference records match." if matches else "No confident journal-article match was found."
        return _result(status, "pdf_fallback", method=method, metadata=_pdf_metadata(request), reason=reason,
                       warnings=list(warnings) + [reason], **info)
    item = matches[0]
    metadata = item["metadata"]
    conflicts = []
    for field in ("doi", "title", "year", "journal"):
        supplied = request.get(field)
        resolved = metadata[field]
        if supplied and resolved and ((normalize_doi(supplied) != resolved) if field == "doi" else
                                      (normalize(supplied) != normalize(resolved))):
            conflicts.append(field)
    if conflicts:
        reason = "PDF-visible metadata conflicts with the reference record: " + ", ".join(conflicts) + "."
        return _result("conflict", "pdf_fallback", method=method, key=item["item_key"], kind=item["item_type"],
                       metadata=_pdf_metadata(request),
                       conflicts=conflicts, warnings=list(warnings) + [reason], reason=reason, **info)
    missing = [field for field in FIELDS if not metadata[field]]
    result_warnings = list(warnings)
    if missing:
        result_warnings.append("Matched reference record lacks: " + ", ".join(missing) + ".")
    return _result("matched", provider, method=method, key=item["item_key"], kind=item["item_type"], metadata=metadata,
                   review=bool(missing or info["stale"] or warnings), missing=missing, warnings=result_warnings, **info)


def providers(provider="auto", *, zotero_export=None, mendeley_export=None, now=None):
    if provider not in {"auto", "zotero", "mendeley"}:
        raise ValueError("provider must be auto, zotero, or mendeley")
    zotero = ZoteroProvider(zotero_export or ROOT / "data" / "zotero-export.json", now=now)
    mendeley = MendeleyProvider([mendeley_export] if mendeley_export else None, now=now)
    if provider == "zotero":
        return [zotero]
    if provider == "mendeley":
        return [mendeley]
    return [p for p in (zotero, mendeley) if p.inspect_source()["available"]] or [zotero, mendeley]


def lookup(request, provider="auto", *, zotero_export=None, mendeley_export=None, now=None):
    candidates = providers(provider, zotero_export=zotero_export, mendeley_export=mendeley_export, now=now)
    if str(request.get("source_type") or "").casefold() not in {"paper", "review", "journal-article"}:
        return _result("skipped", "pdf_fallback", reason="Reference lookup applies only to journal articles.", review=False)
    results = []
    for candidate in candidates:
        result = candidate.lookup(request)
        results.append(result)
        if result["status"] == "matched":
            return result
    for result in results:
        if result["status"] in {"ambiguous", "conflict"}:
            return result
    result = results[0]
    result["warnings"] = [warning for candidate in results for warning in candidate["warnings"]]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_json", type=Path, nargs="?")
    parser.add_argument("--provider", choices=("auto", "zotero", "mendeley"), default="auto")
    parser.add_argument("--zotero-export", type=Path)
    parser.add_argument("--mendeley-export", type=Path)
    parser.add_argument("--check-source", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    selected = providers(args.provider, zotero_export=args.zotero_export, mendeley_export=args.mendeley_export)
    if args.check_source:
        result = [item.inspect_source() for item in selected]
    else:
        if not args.request_json:
            parser.error("request_json is required unless --check-source is used")
        result = lookup(json.loads(args.request_json.read_text(encoding="utf-8")), args.provider,
                        zotero_export=args.zotero_export, mendeley_export=args.mendeley_export)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
