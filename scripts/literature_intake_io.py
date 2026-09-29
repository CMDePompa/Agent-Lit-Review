"""Deterministic file operations for the project-local literature-intake skill.

This module never reads paper content with a model and makes no network calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER_SECTIONS = (
    "Rapid Summary", "Research Question", "Methods and System", "Key Findings",
    "Quantitative Results", "Authors’ Stated Limitations", "Relevance to My Research",
    "Figures Worth Reviewing", "Suggested Topics", "My Notes", "Figure Screenshots",
    "Connections to Other Papers",
)
TEXTBOOK_SECTIONS = (
    "Chapter Scope", "Core Concepts", "Models and Equations", "Assumptions and Limitations",
    "Important Examples", "Relevance to My Research", "Figures Worth Reviewing", "Suggested Topics",
    "My Notes", "Figure Screenshots", "Connections to Other Papers",
)
VERSION = "literature-intake-v2"
TAG_LIST_PROPERTIES = (
    "research_topics", "methodology", "evidence_type", "polymer_system", "morphologies", "paper_role",
)
TAG_PROPERTIES = (*TAG_LIST_PROPERTIES, "context_summary")
FAILURES_START = "<!-- literature-intake:needs-attention:start -->"
FAILURES_END = "<!-- literature-intake:needs-attention:end -->"


def inbox_items(root=ROOT):
    inbox = root / "PDFs" / "Inbox"
    return sorted((p.name for p in inbox.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"), key=str.casefold) if inbox.exists() else []


def resolve_inbox_file(value, root=ROOT):
    inbox = (root / "PDFs" / "Inbox").resolve()
    supplied = Path(value)
    candidate = (supplied if supplied.is_absolute() else root / supplied).resolve()
    if candidate.parent != inbox or not candidate.is_file() or candidate.suffix.lower() != ".pdf":
        raise ValueError("Choose an existing PDF directly inside PDFs/Inbox")
    return candidate


def resolve_pdf(value, root=ROOT):
    candidate = resolve_inbox_file(value, root)
    with candidate.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise ValueError("File does not have a PDF header")
    return candidate


def _failure_path(root):
    return root / "data" / "intake_failures.json"


def _load_failures(root):
    path = _failure_path(root)
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("items"), dict):
        raise ValueError(f"Invalid intake failure state: {path}")
    return value["items"]


def _package_fingerprint(filename, root):
    inbox = root / "PDFs" / "Inbox"
    primary = inbox / filename
    if not primary.is_file():
        return None
    paths = [primary]
    if not filename.startswith("SI - "):
        supplementary = inbox / ("SI - " + filename)
        if supplementary.is_file():
            paths.append(supplementary)
    return {path.name: {"size": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns} for path in paths}


def _dashboard_failure_text(dashboard, items):
    if not dashboard.exists():
        raise FileNotFoundError(f"Dashboard not found: {dashboard}")
    original = dashboard.read_text(encoding="utf-8")
    if original.count(FAILURES_START) != 1 or original.count(FAILURES_END) != 1:
        raise ValueError("Dashboard needs exactly one needs-attention marker pair")
    before, remainder = original.split(FAILURES_START, 1)
    _, after = remainder.split(FAILURES_END, 1)
    if items:
        lines = []
        for filename, entry in sorted(items.items(), key=lambda item: item[0].casefold()):
            name = _markdown_safe(filename)
            reason = _markdown_safe(entry["reason"])
            lines.append(f"- **{name}** — {reason}")
        content = "\n".join(lines)
    else:
        content = "No source packages are currently flagged."
    return original, before + FAILURES_START + "\n" + content + "\n" + FAILURES_END + after


def _markdown_safe(value):
    value = " ".join(str(value).split())
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_{}\[\]()#+.!|~-])", r"\\\1", value)


def _save_failures(items, root):
    path = _failure_path(root)
    dashboard = root / "Literature Notes" / "Literature Dashboard.md"
    original_dashboard, updated_dashboard = _dashboard_failure_text(dashboard, items)
    original_state = path.read_text(encoding="utf-8") if path.exists() else None
    updated_state = json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=2) + "\n"
    staged_state = _stage(path.parent, updated_state)
    staged_dashboard = _stage(dashboard.parent, updated_dashboard)
    try:
        if dashboard.read_text(encoding="utf-8") != original_dashboard or (path.read_text(encoding="utf-8") if path.exists() else None) != original_state:
            raise RuntimeError("Intake state or Dashboard changed during update")
        os.replace(staged_state, path)
        try:
            os.replace(staged_dashboard, dashboard)
        except Exception:
            if original_state is None:
                path.unlink(missing_ok=True)
            else:
                os.replace(_stage(path.parent, original_state), path)
            raise
    finally:
        staged_state.unlink(missing_ok=True)
        staged_dashboard.unlink(missing_ok=True)


def _refresh_failures(root):
    items = _load_failures(root)
    current = {name: entry for name, entry in items.items() if _package_fingerprint(name, root) == entry.get("fingerprint")}
    if current != items:
        _save_failures(current, root)
    return current


def _already_processed_in_inbox(filename, root):
    record = root / "data" / "processing_records" / (Path(filename).stem + ".json")
    if not record.is_file():
        return False
    try:
        value = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(value, dict):
        return False
    return (value.get("source_pdf_filename") == filename
            and value.get("success_status") == "success"
            and value.get("resulting_pdf_path", "").replace("\\", "/") == "PDFs/Inbox/" + filename)


def inspect_queue(root=ROOT):
    items = _refresh_failures(root)
    names = inbox_items(root)
    processed = [name for name in names if _already_processed_in_inbox(name, root)]
    eligible = [name for name in names if not name.startswith("SI - ") and name not in items and name not in processed]
    return {"eligible": eligible,
            "needs_attention": [{"filename": name, "reason": items[name]["reason"], "flagged_at": items[name]["flagged_at"]}
                                for name in sorted(items, key=str.casefold)],
            "already_processed": processed,
            "supplementary": [name for name in names if name.startswith("SI - ")]}


def defer_pdf(value, reason, root=ROOT):
    pdf = resolve_inbox_file(value, root)
    clean_reason = " ".join(reason.split())[:500]
    if not clean_reason:
        raise ValueError("Give a specific reason and the action needed to retry")
    items = _refresh_failures(root)
    items[pdf.name] = {"reason": clean_reason,
                       "flagged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "fingerprint": _package_fingerprint(pdf.name, root)}
    _save_failures(items, root)
    return {"filename": pdf.name, "reason": clean_reason, "status": "needs_attention"}


def retry_pdf(value, root=ROOT):
    pdf = resolve_inbox_file(value, root)
    items = _refresh_failures(root)
    if pdf.name in items:
        del items[pdf.name]
        _save_failures(items, root)
    return {"filename": pdf.name, "status": "eligible"}


def _clear_failure(filename, root):
    items = _load_failures(root)
    if filename in items:
        del items[filename]
        _save_failures(items, root)


def safe_name(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value)
    name = re.sub(r"\s+", " ", name).strip(" .")[:110].rstrip(" .")
    if not name or name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        raise ValueError("Invalid note name")
    return name + ".md"


def supplementary_for(pdf, value, root=ROOT):
    if value is None:
        return None
    supplementary = resolve_pdf(value, root)
    if supplementary.name != "SI - " + pdf.name or supplementary.parent != pdf.parent:
        raise ValueError("Supplementary PDF must be the exact paired file named 'SI - <primary filename>' in PDFs/Inbox")
    return supplementary


def destinations(pdf, note_name, root=ROOT, supplementary=None):
    name = safe_name(note_name.removesuffix(".md"))
    note = root / "Literature Notes" / "Papers" / name
    ingested = root / "PDFs" / "Ingested" / pdf.name
    record = root / "data" / "processing_records" / (note.stem + ".json")
    # Check both PDF and note collisions even when the caller requests no move.
    paths = [note, ingested, record]
    if supplementary:
        paths.append(root / "PDFs" / "Ingested" / supplementary.name)
    for path in paths:
        if path.exists():
            raise FileExistsError(f"Destination already exists: {path}")
    return note, ingested, record


def validate_note(markdown, *, require_blank_human_sections=True):
    if not markdown.startswith("---\n"):
        raise ValueError("Note must start with YAML frontmatter")
    source_match = re.search(r"^source_type:\s*[\"']?([^\"'\r\n]+)", markdown, re.M)
    if not source_match:
        raise ValueError("Note frontmatter must include source_type")
    source_type = source_match.group(1).strip().casefold()
    if source_type == "textbook-chapter":
        required = TEXTBOOK_SECTIONS
    elif source_type in {"paper", "journal-article", "review"}:
        required = PAPER_SECTIONS
    elif source_type in {"thesis", "thesis-chapter"}:
        required = ("Relevance to My Research", "My Notes", "Figure Screenshots", "Connections to Other Papers")
    else:
        raise ValueError(f"Unsupported source_type: {source_type}")
    for heading in required:
        if len(re.findall(r"^## " + re.escape(heading) + r"\s*$", markdown, re.M)) != 1:
            raise ValueError(f"Missing or duplicate section: {heading}")
    if "metadata_review_needed:" not in markdown or "pdf:" not in markdown:
        raise ValueError("Required metadata fields are missing")
    block, _, _ = _frontmatter(markdown)
    for key in TAG_PROPERTIES:
        if len(re.findall(r"^" + re.escape(key) + r":", block, re.M)) != 1:
            raise ValueError(f"Note frontmatter must include exactly one {key} property")
    for key in TAG_LIST_PROPERTIES:
        _frontmatter_list_values(markdown, key)
    pdf_values = _frontmatter_pdf_values(markdown)
    if not pdf_values or any(not value.strip() for value in pdf_values):
        raise ValueError("The pdf property must link to the primary PDF")
    supplementary_value = re.search(r"^supplementary_pdf:[ \t]*(.*?)[ \t]*$", markdown, re.M)
    supplementary_value = supplementary_value.group(1).strip(" \'\"") if supplementary_value else ""
    if supplementary_value.casefold() not in {"", "null", "~", "[]"}:
        if len(re.findall(r"^## Supplementary Information Used\s*$", markdown, re.M)) != 1:
            raise ValueError("A paired supplementary PDF requires the Supplementary Information Used section")
    if require_blank_human_sections:
        for heading in ("My Notes", "Figure Screenshots", "Connections to Other Papers"):
            match = re.search(r"^## " + re.escape(heading) + r"\s*$([\s\S]*?)(?=^## |\Z)", markdown, re.M)
            body = re.sub(r"<!--.*?-->", "", match.group(1), flags=re.S).strip()
            if body:
                raise ValueError(f"Human-owned section must be blank: {heading}")


def resolve_pdf_in_collection(value, collection, root=ROOT):
    folder = (root / "PDFs" / collection).resolve()
    supplied = Path(value)
    candidate = (supplied if supplied.is_absolute() else root / supplied).resolve()
    if candidate.parent != folder or not candidate.is_file() or candidate.suffix.lower() != ".pdf":
        raise ValueError(f"Choose an existing PDF directly inside PDFs/{collection}")
    with candidate.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise ValueError("File does not have a PDF header")
    return candidate


def _frontmatter(markdown):
    match = re.match(r"\A---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|\Z)", markdown)
    if not match:
        raise ValueError("Note must start with YAML frontmatter")
    return match.group(1), match.start(1), match.end(1)


def _frontmatter_value(markdown, key):
    block, _, _ = _frontmatter(markdown)
    matches = re.findall(r"^" + re.escape(key) + r":[ \t]*(.*?)[ \t]*$", block, re.M)
    if len(matches) != 1:
        raise ValueError(f"Expected one frontmatter field: {key}")
    return matches[0].strip(" \'\"")


def _frontmatter_optional_value(markdown, key, default=""):
    block, _, _ = _frontmatter(markdown)
    matches = re.findall(r"^" + re.escape(key) + r":[ \t]*(.*?)[ \t]*$", block, re.M)
    if not matches:
        return default
    if len(matches) != 1:
        raise ValueError(f"Expected at most one frontmatter field: {key}")
    return matches[0].strip(" \'\"")


def _frontmatter_pdf_values(markdown):
    raw = _frontmatter_value(markdown, "pdf")
    if raw.lstrip().startswith("[") and not raw.lstrip().startswith("[["):
        values = _frontmatter_list_values(markdown, "pdf")
    else:
        values = [raw]
    paths = []
    for value in values:
        value = value.strip()
        if value.startswith("[[") and value.endswith("]]"):
            value = value[2:-2].split("|", 1)[0].strip()
        paths.append(value)
    return paths


def _frontmatter_list_values(markdown, key):
    block, _, _ = _frontmatter(markdown)
    lines = block.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^" + re.escape(key) + r":[ \t]*(.*?)[ \t]*$", line)
        if not match:
            continue
        raw = match.group(1).strip()
        if raw.startswith("["):
            try:
                values = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{key} must be a YAML list of strings") from exc
            if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                raise ValueError(f"{key} must be a YAML list of strings")
            return values
        if raw:
            raise ValueError(f"{key} must be a YAML list of strings")
        values = []
        for child in lines[index + 1:]:
            if not child.strip():
                continue
            item = re.match(r"^[ \t]+-[ \t]*(.*?)\s*$", child)
            if item:
                value = item.group(1).strip()
                if len(value) >= 2 and value[0] == value[-1] == '"':
                    value = json.loads(value)
                elif len(value) >= 2 and value[0] == value[-1] == "'":
                    value = value[1:-1].replace("''", "'")
                values.append(value)
                continue
            if re.match(r"^[ \t]+", child):
                raise ValueError(f"{key} must be a YAML list of strings")
            break
        return values
    raise ValueError(f"Expected one frontmatter field: {key}")


def _obsidian_pdf_link(path, root):
    return "[[" + Path(path).relative_to(root).as_posix() + "]]"


def _set_default_tag_properties(markdown):
    for key in TAG_LIST_PROPERTIES:
        if not re.search(r"^" + re.escape(key) + r":", _frontmatter(markdown)[0], re.M):
            markdown = _set_or_add_frontmatter(markdown, key, [])
    if not re.search(r"^context_summary:", _frontmatter(markdown)[0], re.M):
        markdown = _set_or_add_frontmatter(markdown, "context_summary", "")
    return markdown


def _set_frontmatter(markdown, key, value, *, quoted=False):
    block, start, end = _frontmatter(markdown)
    replacement = json.dumps(value, ensure_ascii=False) if quoted else str(value)
    pattern = re.compile(r"^" + re.escape(key) + r":.*$", re.M)
    updated, count = pattern.subn(f"{key}: {replacement}", block)
    if count != 1:
        raise ValueError(f"Expected one frontmatter field to update: {key}")
    return markdown[:start] + updated + markdown[end:]


def _set_or_add_frontmatter(markdown, key, value):
    block, start, end = _frontmatter(markdown)
    if re.search(r"^" + re.escape(key) + r":", block, re.M):
        return _set_frontmatter(markdown, key, value, quoted=True)
    updated = block.rstrip() + f"\n{key}: {json.dumps(value, ensure_ascii=False)}"
    return markdown[:start] + updated + markdown[end:]


def _remove_obsolete_note_properties(markdown):
    block, start, end = _frontmatter(markdown)
    cleaned = re.sub(r"(?m)^(?:model|prompt_version|processed_at):[^\r\n]*(?:\r?\n|$)", "", block)
    return markdown[:start] + cleaned + markdown[end:]


def _remove_legacy_pdf_body_links(markdown):
    """Remove old duplicate PDF links from the note body; PDF property holds the links."""
    _, _, end = _frontmatter(markdown)
    body = markdown[end:]
    body = re.sub(r"(?m)^<!-- literature-intake:pdf-links:(?:start|end) -->\r?\n?", "", body)
    first_section = re.search(r"^## ", body, re.M)
    preamble_end = first_section.start() if first_section else len(body)
    preamble = body[:preamble_end]
    preamble = re.sub(r"(?m)^\*\*(?:PDF|Supplementary PDF):\*\*.*(?:\r?\n)?", "", preamble)
    if first_section:
        following = body[preamble_end:].lstrip("\r\n")
        body = preamble.rstrip() + ("\n\n" if preamble.strip() else "") + following
    else:
        body = preamble.rstrip()
    return markdown[:end] + body


def _resolve_note_pdf(value, note, root):
    value = value.strip().strip("\"'")
    if not value or value.casefold() in {"null", "~", "[]"}:
        raise ValueError(f"Note has no PDF path: {note}")
    supplied = Path(value)
    candidates = []
    if supplied.is_absolute():
        candidates.append(supplied)
    else:
        candidates.extend((root / supplied, note.parent / supplied))
    for collection in ("Ingested", "Inbox"):
        candidates.append(root / "PDFs" / collection / supplied.name)
    allowed = {(root / "PDFs" / "Inbox").resolve(), (root / "PDFs" / "Ingested").resolve()}
    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.parent not in allowed or not candidate.is_file() or candidate.suffix.lower() != ".pdf":
            continue
        with candidate.open("rb") as stream:
            if stream.read(5) == b"%PDF-":
                return candidate
    raise FileNotFoundError(f"Could not resolve note PDF to an existing Inbox or Ingested PDF: {value}")


def repair_pdf_links(root=ROOT):
    """Move PDF links into the pdf property without changing research sections."""
    notes_dir = root / "Literature Notes" / "Papers"
    plans = []
    if not notes_dir.is_dir():
        return {"updated": [], "count": 0}
    for note in sorted(notes_dir.glob("*.md"), key=lambda path: path.name.casefold()):
        original = note.read_text(encoding="utf-8")
        pdf_values = _frontmatter_pdf_values(original)
        if len(pdf_values) > 2:
            raise ValueError(f"Expected one primary PDF and at most one SI in {note.name}")
        primary = _resolve_note_pdf(pdf_values[0], note, root)
        supplementary_value = _frontmatter_optional_value(original, "supplementary_pdf")
        supplementary = None
        if supplementary_value and supplementary_value.casefold() not in {"null", "~", "[]"}:
            supplementary = _resolve_note_pdf(supplementary_value, note, root)
        elif len(pdf_values) == 2:
            supplementary = _resolve_note_pdf(pdf_values[1], note, root)
        updated = _set_or_add_frontmatter(original, "pdf", [_obsidian_pdf_link(primary, root)] + ([_obsidian_pdf_link(supplementary, root)] if supplementary else []))
        updated = _set_or_add_frontmatter(updated, "supplementary_pdf", supplementary.relative_to(root).as_posix() if supplementary else None)
        updated = _set_default_tag_properties(updated)
        updated = _remove_legacy_pdf_body_links(updated)
        for heading in ("My Notes", "Figure Screenshots", "Connections to Other Papers"):
            if _section_body(original, heading) != _section_body(updated, heading):
                raise ValueError(f"PDF-link repair would modify human-owned section in {note.name}: {heading}")
        plans.append((note, original, updated))

    changed = [(note, old, new) for note, old, new in plans if old != new]
    staged = []
    try:
        for note, _, updated in changed:
            staged.append((note, _stage(note.parent, updated)))
        for note, original, _ in changed:
            if note.read_text(encoding="utf-8") != original:
                raise RuntimeError(f"Note changed during PDF-link repair; stopped without overwriting: {note}")
        replaced = []
        try:
            for note, temporary in staged:
                os.replace(temporary, note)
                replaced.append(note)
        except Exception:
            for note, original, _ in changed:
                if note in replaced:
                    restore = _stage(note.parent, original)
                    os.replace(restore, note)
                    restore.unlink(missing_ok=True)
            raise
    finally:
        for _, temporary in staged:
            temporary.unlink(missing_ok=True)
    return {"updated": [str(note.relative_to(root)) for note, _, _ in changed], "count": len(changed)}


def _section_body(markdown, heading):
    match = re.search(r"^## " + re.escape(heading) + r"\s*$([\s\S]*?)(?=^## |\Z)", markdown, re.M)
    if not match:
        raise ValueError(f"Missing required section: {heading}")
    return match.group(1)


def check_supplementary_attachment(primary_value, supplementary_value, root=ROOT):
    primary_inbox = (root / "PDFs" / "Inbox").resolve()
    primary_ingested = (root / "PDFs" / "Ingested").resolve()
    supplied = Path(primary_value)
    primary = (supplied if supplied.is_absolute() else root / supplied).resolve()
    if primary.parent not in {primary_inbox, primary_ingested} or not primary.is_file() or primary.suffix.lower() != ".pdf":
        raise ValueError("Choose the existing primary PDF directly inside PDFs/Inbox or PDFs/Ingested")
    with primary.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise ValueError("Primary file does not have a PDF header")
    supplementary = resolve_pdf(supplementary_value, root)
    if supplementary.name != "SI - " + primary.name:
        raise ValueError("Supplementary PDF must be named exactly 'SI - <primary filename>'")

    note = root / "Literature Notes" / "Papers" / safe_name(primary.stem)
    record = root / "data" / "processing_records" / (note.stem + ".json")
    if not note.is_file():
        raise FileNotFoundError(f"Existing literature note not found: {note}")
    if not record.is_file():
        raise FileNotFoundError(f"Processing record not found: {record}")
    ingested_supplementary = root / "PDFs" / "Ingested" / supplementary.name
    if ingested_supplementary.exists():
        raise FileExistsError(f"Destination already exists: {ingested_supplementary}")

    markdown = note.read_text(encoding="utf-8")
    if _frontmatter_value(markdown, "source_type").casefold() not in {"paper", "journal-article", "review"}:
        raise ValueError("Separated supplementary attachment is supported for existing journal-paper notes")
    pdf_values = _frontmatter_pdf_values(markdown)
    if not pdf_values or _resolve_note_pdf(pdf_values[0], note, root) != primary:
        raise ValueError("Existing note does not point to the selected primary PDF")
    if _frontmatter_value(markdown, "supplementary_pdf").casefold() not in {"", "null", "~", "[]"}:
        raise ValueError("Existing note already has a supplementary PDF")
    if re.search(r"^## Supplementary Information Used\s*$", markdown, re.M):
        raise ValueError("Existing note already contains a supplementary-information section")
    if _frontmatter_value(markdown, "source_file_count") != "1":
        raise ValueError("Existing note is not a single-file note eligible for attachment")

    record_data = json.loads(record.read_text(encoding="utf-8"))
    if record_data.get("success_status") != "success" or record_data.get("source_pdf_filename") != primary.name:
        raise ValueError("Processing record does not identify a successful intake of this primary PDF")
    if record_data.get("generated_note_path", "").replace("\\", "/") != note.relative_to(root).as_posix():
        raise ValueError("Processing record does not point to the existing note")
    if supplementary.name in record_data.get("source_pdf_filenames", []):
        raise ValueError("Processing record already lists this supplementary PDF")
    return primary, supplementary, note, record


def attach_supplementary(primary_value, supplementary_value, section_markdown, update_spec, *, no_move=False, root=ROOT):
    primary, supplementary, note, record = check_supplementary_attachment(primary_value, supplementary_value, root)
    old_note = note.read_text(encoding="utf-8")
    old_record_text = record.read_text(encoding="utf-8")
    record_data = json.loads(old_record_text)
    section_markdown = section_markdown.strip() + "\n"
    if not section_markdown.startswith("## Supplementary Information Used\n"):
        raise ValueError("Supplementary section draft must start with '## Supplementary Information Used'")
    if len(re.findall(r"^## Supplementary Information Used\s*$", section_markdown, re.M)) != 1:
        raise ValueError("Supplementary section draft must contain that heading exactly once")
    if "**File:**" not in section_markdown or "**Material consulted:**" not in section_markdown or "**Important contributions to this note:**" not in section_markdown:
        raise ValueError("Supplementary section must identify the file, inspected material, and contributions")
    if supplementary.name not in section_markdown:
        raise ValueError("Supplementary section must name the exact supplementary PDF")
    if not isinstance(update_spec, dict):
        raise ValueError("Note update instructions must be a JSON object")

    updated = old_note
    for replacement in update_spec.get("replacements", []):
        old_text, new_text = replacement.get("old"), replacement.get("new")
        if not old_text or not new_text or updated.count(old_text) != 1:
            raise ValueError("Each note replacement must match exactly once")
        human_content = "\n".join(_section_body(updated, heading) for heading in ("My Notes", "Figure Screenshots", "Connections to Other Papers"))
        if old_text in human_content:
            raise ValueError("Note replacement would modify a human-owned section")
        updated = updated.replace(old_text, new_text, 1)

    for key, value in (
        ("source_file_count", 2),
        ("supplementary_pdf", str((supplementary if no_move else root / "PDFs" / "Ingested" / supplementary.name).relative_to(root)).replace("\\", "/")),
        ("summary_scope", update_spec["summary_scope"]),
        ("page_scope", update_spec["page_scope"]),
    ):
        updated = _set_frontmatter(updated, key, value, quoted=isinstance(value, str))

    supplementary_result = supplementary if no_move else root / "PDFs" / "Ingested" / supplementary.name
    updated = _set_or_add_frontmatter(updated, "pdf", [
        _obsidian_pdf_link(primary, root), _obsidian_pdf_link(supplementary_result, root),
    ])
    updated = _set_default_tag_properties(updated)

    insertion = re.search(r"^## (?:Claims to Verify Manually|Supporting Evidence|Suggested Topics)\s*$", updated, re.M)
    if not insertion:
        raise ValueError("Could not find a safe insertion point for supplementary information")
    updated = updated[:insertion.start()] + section_markdown + "\n" + updated[insertion.start():]
    updated = _remove_legacy_pdf_body_links(updated)
    validate_note(updated, require_blank_human_sections=False)
    for heading in ("My Notes", "Figure Screenshots", "Connections to Other Papers"):
        if _section_body(old_note, heading) != _section_body(updated, heading):
            raise ValueError(f"Attachment update changed human-owned section: {heading}")
    if _frontmatter_value(updated, "source_file_count") != "2":
        raise ValueError("Updated note must record two source files")
    expected_supplement = str((supplementary if no_move else root / "PDFs" / "Ingested" / supplementary.name).relative_to(root)).replace("\\", "/")
    if _frontmatter_value(updated, "supplementary_pdf").replace("\\", "/") != expected_supplement:
        raise ValueError("Updated note supplementary_pdf path is incorrect")
    if _frontmatter_pdf_values(updated) != [primary.relative_to(root).as_posix(), supplementary_result.relative_to(root).as_posix()]:
        raise ValueError("Updated note pdf property must link to the primary and supplementary PDFs")

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    resulting_supplementary = supplementary if no_move else root / "PDFs" / "Ingested" / supplementary.name
    record_data["source_pdf_filenames"] = [primary.name, supplementary.name]
    record_data["resulting_supplementary_pdf_path"] = str(resulting_supplementary.relative_to(root))
    record_data["supplementary_pdf_sha256"] = sha256(supplementary)
    resolved_warnings = update_spec.get("resolved_provenance_warnings", [])
    if resolved_warnings:
        prior_warnings = record_data.get("warnings", [])
        record_data["warnings"] = [warning for warning in prior_warnings if warning not in resolved_warnings]
        history = record_data.get("resolved_warnings", [])
        history.extend({"warning": warning, "resolved_at": timestamp,
                        "resolution": "The exact supplementary PDF filename was corrected and the SI was attached."}
                       for warning in resolved_warnings if warning in prior_warnings)
        record_data["resolved_warnings"] = history
    record_data["supplementary_attachment_updates"] = record_data.get("supplementary_attachment_updates", []) + [{
        "processing_timestamp": timestamp,
        "supplementary_pdf_filename": supplementary.name,
        "resulting_pdf_path": str(resulting_supplementary.relative_to(root)),
        "pdf_sha256": record_data["supplementary_pdf_sha256"],
        "workflow_version": VERSION,
    }]
    record_data["last_updated_at"] = timestamp

    staged_note = _stage(note.parent, updated)
    staged_record = _stage(record.parent, json.dumps(record_data, ensure_ascii=False, indent=2) + "\n")
    moved = False
    replaced_note = replaced_record = False
    try:
        if note.read_text(encoding="utf-8") != old_note or record.read_text(encoding="utf-8") != old_record_text:
            raise RuntimeError("Note or processing record changed during attachment; stopped without overwriting")
        os.replace(staged_note, note)
        replaced_note = True
        os.replace(staged_record, record)
        replaced_record = True
        if not no_move:
            os.rename(supplementary, resulting_supplementary)
            moved = True
    except Exception:
        if moved:
            os.rename(resulting_supplementary, supplementary)
        if replaced_record:
            restore_record = _stage(record.parent, old_record_text)
            os.replace(restore_record, record)
        if replaced_note:
            restore_note = _stage(note.parent, old_note)
            os.replace(restore_note, note)
        raise
    finally:
        for staged in (staged_note, staged_record):
            staged.unlink(missing_ok=True)
    return {"primary_pdf": str(primary.relative_to(root)), "supplementary_pdf": str(resulting_supplementary.relative_to(root)),
            "generated_note_path": str(note.relative_to(root)), "processing_record_path": str(record.relative_to(root)),
            "supplementary_pdf_sha256": record_data["supplementary_pdf_sha256"], "processing_timestamp": timestamp,
            "success_status": "success"}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stage(directory, content):
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=directory, prefix=".intake-", suffix=".tmp", delete=False) as stream:
        stream.write(content)
        return Path(stream.name)


def commit(pdf_value, note_name, markdown, *, supplementary_pdf_value=None, no_move=False, model=None, tier=None, warnings=None, metadata_lookup=None, root=ROOT):
    model = model.strip() or None if model is not None else None
    tier = tier.strip() or None if tier is not None else None
    pdf = resolve_pdf(pdf_value, root)
    is_review_filename = pdf.name.startswith("REVIEW - ")
    is_review_note = _frontmatter_value(markdown, "source_type").casefold() == "review"
    if is_review_filename != is_review_note:
        raise ValueError("REVIEW - filenames require source_type: review, and review notes require the REVIEW - prefix")
    supplementary = supplementary_for(pdf, supplementary_pdf_value, root)
    note, ingested, record = destinations(pdf, note_name, root, supplementary)
    result_pdf = pdf if no_move else ingested
    result_supplementary = (supplementary if no_move else root / "PDFs" / "Ingested" / supplementary.name) if supplementary else None
    pdf_property = [_obsidian_pdf_link(result_pdf, root)] + ([_obsidian_pdf_link(result_supplementary, root)] if result_supplementary else [])
    markdown = _set_or_add_frontmatter(markdown, "pdf", pdf_property)
    markdown = _set_or_add_frontmatter(markdown, "supplementary_pdf", result_supplementary.relative_to(root).as_posix() if result_supplementary else None)
    markdown = _remove_obsolete_note_properties(markdown)
    markdown = _set_default_tag_properties(markdown)
    markdown = _remove_legacy_pdf_body_links(markdown)
    validate_note(markdown)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    provenance = {
        "source_pdf_filename": pdf.name,
        "source_pdf_filenames": [pdf.name] + ([supplementary.name] if supplementary else []),
        "resulting_pdf_path": str(result_pdf.relative_to(root)),
        "resulting_supplementary_pdf_path": str(result_supplementary.relative_to(root)) if result_supplementary else None,
        "generated_note_path": str(note.relative_to(root)),
        "processing_timestamp": timestamp,
        "selected_codex_model": model,
        "selected_codex_tier": tier,
        "skill_name": "literature-intake",
        "skill_workflow_version": VERSION,
        "pdf_sha256": sha256(pdf),
        "supplementary_pdf_sha256": sha256(supplementary) if supplementary else None,
        "warnings": warnings or [],
        "success_status": "success",
    }
    if metadata_lookup:
        provenance["metadata_verification"] = {
            key: metadata_lookup.get(key) for key in (
                "status", "match_method", "export_path", "export_modified_at", "export_age_days",
                "stale", "metadata_review_needed", "reason", "zotero_item_key", "missing_fields",
                "conflicting_fields",
            ) if key in metadata_lookup
        }
    staged_note = staged_record = None
    wrote_note = wrote_record = False
    moved_files = []
    try:
        staged_note = _stage(note.parent, markdown)
        staged_record = _stage(record.parent, json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
        # Exclusive create prevents replacement if another task creates the note meanwhile.
        with note.open("x", encoding="utf-8", newline="\n") as stream:
            wrote_note = True
            stream.write(staged_note.read_text(encoding="utf-8"))
        if not no_move:
            ingested.parent.mkdir(parents=True, exist_ok=True)
            sources = [(pdf, ingested)]
            if supplementary:
                sources.append((supplementary, root / "PDFs" / "Ingested" / supplementary.name))
            for source, target in sources:
                if target.exists():
                    raise FileExistsError(f"Destination already exists: {target}")
                os.rename(source, target)
                moved_files.append((source, target))
        with record.open("x", encoding="utf-8", newline="\n") as stream:
            wrote_record = True
            stream.write(staged_record.read_text(encoding="utf-8"))
    except Exception:
        for source, target in reversed(moved_files):
            os.rename(target, source)
        if wrote_record:
            record.unlink()
        if wrote_note:
            note.unlink()
        raise
    finally:
        for temp in (staged_note, staged_record):
            if temp is not None:
                temp.unlink(missing_ok=True)
    _clear_failure(pdf.name, root)
    return provenance


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect")
    defer = sub.add_parser("defer", help="Flag an unprocessable Inbox PDF and skip it in next-source selection")
    defer.add_argument("pdf")
    defer.add_argument("reason")
    retry = sub.add_parser("retry", help="Clear a failure flag after fixing the issue")
    retry.add_argument("pdf")
    check = sub.add_parser("check")
    check.add_argument("pdf")
    check.add_argument("note_name")
    check.add_argument("--supplementary-pdf")
    check_si = sub.add_parser("check-supplementary")
    check_si.add_argument("primary_pdf")
    check_si.add_argument("supplementary_pdf")
    save = sub.add_parser("commit")
    save.add_argument("pdf")
    save.add_argument("note_name")
    save.add_argument("draft_file", type=Path)
    save.add_argument("--supplementary-pdf")
    save.add_argument("--no-move", action="store_true")
    save.add_argument("--model")
    save.add_argument("--tier")
    save.add_argument("--warnings-json", default="[]")
    save.add_argument("--metadata-lookup-file", type=Path)
    attach = sub.add_parser("attach-supplementary")
    attach.add_argument("primary_pdf")
    attach.add_argument("supplementary_pdf")
    attach.add_argument("section_file", type=Path)
    attach.add_argument("update_json", type=Path)
    attach.add_argument("--no-move", action="store_true")
    sub.add_parser("repair-pdf-links", help="Move PDF links into the pdf property and remove duplicate body links on existing notes")
    args = parser.parse_args()
    if args.command == "inspect":
        print(json.dumps(inspect_queue(), ensure_ascii=False, indent=2))
    elif args.command == "defer":
        print(json.dumps(defer_pdf(args.pdf, args.reason), ensure_ascii=False, indent=2))
    elif args.command == "retry":
        print(json.dumps(retry_pdf(args.pdf), ensure_ascii=False, indent=2))
    elif args.command == "check":
        pdf = resolve_pdf(args.pdf)
        supplementary = supplementary_for(pdf, args.supplementary_pdf) if args.supplementary_pdf else None
        print(json.dumps({"pdf": str(pdf), "supplementary_pdf": str(supplementary) if supplementary else None, "destinations": [str(p) for p in destinations(pdf, args.note_name, supplementary=supplementary)]}, ensure_ascii=False, indent=2))
    elif args.command == "check-supplementary":
        primary, supplementary, note, record = check_supplementary_attachment(args.primary_pdf, args.supplementary_pdf)
        print(json.dumps({"primary_pdf": str(primary), "supplementary_pdf": str(supplementary),
                          "existing_note": str(note), "processing_record": str(record),
                          "resulting_supplementary_pdf": str(ROOT / "PDFs" / "Ingested" / supplementary.name)}, ensure_ascii=False, indent=2))
    elif args.command == "commit":
        metadata_lookup = json.loads(args.metadata_lookup_file.read_text(encoding="utf-8")) if args.metadata_lookup_file else None
        print(json.dumps(commit(args.pdf, args.note_name, args.draft_file.read_text(encoding="utf-8"), supplementary_pdf_value=args.supplementary_pdf, no_move=args.no_move, model=args.model, tier=args.tier, warnings=json.loads(args.warnings_json), metadata_lookup=metadata_lookup), ensure_ascii=False, indent=2))
    elif args.command == "attach-supplementary":
        section = args.section_file.read_text(encoding="utf-8")
        update_spec = json.loads(args.update_json.read_text(encoding="utf-8"))
        print(json.dumps(attach_supplementary(args.primary_pdf, args.supplementary_pdf, section, update_spec, no_move=args.no_move), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(repair_pdf_links(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
