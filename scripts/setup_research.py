"""Apply research-config.yaml to the local intake skill (Python standard library only)."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "research-config.yaml"
SKILL = ROOT / ".agents/skills/literature-intake"
TEMPLATES = ROOT / "Literature Notes/Templates"
BASE = ROOT / "Literature Notes/Literature Database.base"
DASHBOARD = ROOT / "Literature Notes/Literature Dashboard.md"
HELPER = ROOT / "scripts/literature_intake_io.py"
BEGIN = "# research-setup:domain-properties:start"
END = "# research-setup:domain-properties:end"
SCHEMA_BEGIN = "<!-- research-setup:domain-properties:start -->"
SCHEMA_END = "<!-- research-setup:domain-properties:end -->"
FORMAT_BEGIN = "<!-- research-setup:formatting-rules:start -->"
FORMAT_END = "<!-- research-setup:formatting-rules:end -->"
PREVIOUS_SHARED = ("research_topics", "methodology", "evidence_type", "paper_role")
RESERVED = {
    "title", "parent_title", "authors", "year", "source_type", "document_type",
    "thesis_subtype", "mapped_thesis_aim", "source_file_count", "journal", "doi",
    "chapter_number", "chapter_title", "page_scope", "summary_scope", "pdf",
    "supplementary_pdf", "context_summary", "metadata_source", "reference_provider",
    "reference_item_key", "reference_match_method", "reference_export_modified_at",
    "reference_export_age_days", "summary_status", "review_status",
    "metadata_review_needed", "file",
}


def read_config(path: Path):
    """Read the documented YAML subset without a third-party YAML dependency."""
    lines = path.read_text(encoding="utf-8").splitlines()
    context = []
    properties = []
    formatting_rules = []
    view_name = None
    section = None
    for number, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            if section == "context" and line.startswith("  "):
                context.append("")
            continue
        if not line.startswith(" "):
            if line == "research_context: |":
                section = "context"
            elif line == "domain_properties:":
                section = "properties"
            elif line.startswith("domain_view_name: "):
                view_name = line.partition(": ")[2].strip().strip('"\'')
                section = None
            elif line == "formatting_rules:":
                section = "formatting"
            else:
                raise ValueError(f"Unsupported configuration at line {number}: {line}")
        elif section == "context" and line.startswith("  "):
            context.append(line[2:])
        elif section == "properties":
            if line.startswith("  - name: "):
                properties.append({"name": line[10:].strip().strip('"\''), "description": "", "type": ""})
            elif line.startswith("    type: ") and properties:
                properties[-1]["type"] = line[10:].strip().strip('"\'')
            elif line.startswith("    description: ") and properties:
                properties[-1]["description"] = line[17:].strip().strip('"\'')
            else:
                raise ValueError(f"Expected a property name, type, or description at line {number}")
        elif section == "formatting" and re.match(r"^\s*-\s+", line):
            rule = re.sub(r"^\s*-\s+", "", line).strip()
            if rule.startswith("'") and rule.endswith("'"):
                rule = rule[1:-1].replace("''", "'")
            elif rule.startswith('"') and rule.endswith('"'):
                rule = rule[1:-1]
            if not rule or "\n" in rule:
                raise ValueError(f"Empty formatting rule at line {number}")
            formatting_rules.append(rule)
        else:
            raise ValueError(f"Unexpected indentation at line {number}")
    context_text = "\n".join(context).strip()
    if not context_text:
        raise ValueError("research_context must contain text")
    if not view_name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]*", view_name):
        raise ValueError("domain_view_name must use letters, numbers, spaces, underscores, or hyphens")
    names = [item["name"] for item in properties]
    if not names:
        raise ValueError("domain_properties must contain at least one property")
    if len(set(names)) != len(names):
        raise ValueError("domain_properties contains duplicate names")
    for item in properties:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", item["name"]):
            raise ValueError(f"Invalid property name: {item['name']}")
        if item["name"] in RESERVED or not item["description"]:
            raise ValueError(f"Reserved property or missing description: {item['name']}")
        if item["type"] not in {"list", "string"}:
            raise ValueError(f"Property {item['name']} needs type: list or type: string")
    return context_text, properties, view_name, formatting_rules


def replace_region(text, begin, end, content):
    pattern = re.escape(begin) + r"\n.*?" + re.escape(end)
    replacement = begin + "\n" + content.rstrip("\n") + "\n" + end
    updated, count = re.subn(pattern, lambda _: replacement, text, flags=re.S)
    if count != 1:
        raise ValueError(f"Expected one managed region beginning {begin}")
    return updated


def formatting_key(rule):
    title = re.match(r"\*\*([^*]+):\*\*", rule.strip())
    return ("title", title.group(1).strip().casefold()) if title else ("text", " ".join(rule.split()).casefold())


def apply(config=CONFIG, *, dry_run=False):
    context, properties, view_name, formatting_rules = read_config(config)
    names = [item["name"] for item in properties]
    changes = {}

    # Keep template-specific defaults, such as evidence_type: ["review"].
    template_paths = sorted(TEMPLATES.glob("*Note Template.md"))
    old_names = None
    for path in template_paths:
        original = path.read_text(encoding="utf-8")
        frontmatter_end = original.find("\n---", 4)
        if not original.startswith("---\n") or frontmatter_end < 0:
            raise ValueError(f"Missing template frontmatter: {path}")
        front = original[:frontmatter_end]
        existing = dict(re.findall(r"^([a-z][a-z0-9_]*): ([^\n]*)$", front, re.M))
        if BEGIN in original:
            match = re.search(re.escape(BEGIN) + r"\n(.*?)\n" + re.escape(END), front, re.S)
            if not match:
                raise ValueError(f"Broken domain property markers in {path}")
            marked_names = re.findall(r"^([a-z][a-z0-9_]*):", match.group(1), re.M)
            front = front[:match.start()] + front[match.end():].lstrip("\n")
        else:
            marked_names = ["polymer_system", "morphologies"]
        current = list(dict.fromkeys([name for name in PREVIOUS_SHARED if name in existing] + marked_names))
        for name in set(current):
            front = re.sub(r"^" + re.escape(name) + r": [^\n]*\n?", "", front, flags=re.M)
        generated = []
        for item in properties:
            default = "[]" if item["type"] == "list" else '""'
            previous = existing.get(item["name"])
            if previous and ((item["type"] == "list" and previous.startswith("[")) or
                             (item["type"] == "string" and previous.startswith(('"', "'")))):
                default = previous
            generated.append(f"{item['name']}: {default}")
        region = BEGIN + "\n" + "\n".join(generated) + "\n" + END
        front, count = re.subn(r"^pdf: \[\]$", lambda _: "pdf: []\n" + region, front, count=1, flags=re.M)
        if count != 1:
            raise ValueError(f"Cannot locate pdf anchor in {path}")
        updated = front + original[frontmatter_end:]
        if old_names is None:
            old_names = current
        elif old_names != current:
            raise ValueError("Template domain properties disagree; resolve them before setup")
        changes[path] = updated

    schema = SKILL / "note-schema.md"
    original = schema.read_text(encoding="utf-8")
    # The first run replaces the two polymer-specific entries; later runs use markers.
    block = "\n".join(f"- `{item['name']}` ({item['type']}): {item['description']}" for item in properties)
    if SCHEMA_BEGIN in original:
        updated = replace_region(original, SCHEMA_BEGIN, SCHEMA_END, block)
    else:
        start = original.index("- `polymer_system`:")
        finish = original.index("- `paper_role`:", start)
        updated = original[:start] + SCHEMA_BEGIN + "\n" + block + "\n" + SCHEMA_END + "\n" + original[finish:]
        updated = updated.replace("`polymer_system` (list), `morphologies` (list), ", "")
        updated = updated.replace("Populate the six tag lists", "Populate the shared and domain tag lists")
        updated = updated.replace("For the current polymer research vocabulary and examples", "For the configured research vocabulary")
        updated = updated.replace("Frontmatter: ", "Frontmatter (plus the domain properties below): ", 1)
    changes[schema] = updated

    context_path = SKILL / "research-context.md"
    changes[context_path] = "# Research context for relevance assessment\n\n" + context + "\n"

    original = HELPER.read_text(encoding="utf-8")
    list_names = tuple(item["name"] for item in properties if item["type"] == "list")
    text_names = tuple(item["name"] for item in properties if item["type"] == "string")
    def tuple_source(values):
        return "(" + ", ".join(repr(value) for value in values) + ("," if len(values) == 1 else "") + ")"
    formatted = ("TAG_LIST_PROPERTIES = " + tuple_source(list_names) + "\n"
                 "DOMAIN_TEXT_PROPERTIES = " + tuple_source(text_names) + "\n"
                 'TAG_PROPERTIES = (*TAG_LIST_PROPERTIES, *DOMAIN_TEXT_PROPERTIES, "context_summary")')
    updated, count = re.subn(
        r"TAG_LIST_PROPERTIES = \(.*?\)\n(?:DOMAIN_TEXT_PROPERTIES = \(.*?\)\n)?TAG_PROPERTIES = [^\n]*",
        lambda _: formatted, original, count=1, flags=re.S,
    )
    if count != 1:
        raise ValueError("Cannot locate tag property constants in intake helper")
    if "    for key in DOMAIN_TEXT_PROPERTIES:" not in updated:
        updated = updated.replace(
            '    if not re.search(r"^context_summary:", _frontmatter(markdown)[0], re.M):',
            '    for key in DOMAIN_TEXT_PROPERTIES:\n'
            '        if not re.search(r"^" + re.escape(key) + r":", _frontmatter(markdown)[0], re.M):\n'
            '            markdown = _set_or_add_frontmatter(markdown, key, "")\n'
            '    if not re.search(r"^context_summary:", _frontmatter(markdown)[0], re.M):',
        )
    changes[HELPER] = updated

    skill_path = SKILL / "SKILL.md"
    original = skill_path.read_text(encoding="utf-8")
    without_custom = re.sub(
        r"\n+" + re.escape(FORMAT_BEGIN) + r"\n.*?\n" + re.escape(FORMAT_END) + r"\n+",
        "\n\n", original, flags=re.S,
    )
    section = re.search(r"## Formatting rule for math, equations, and units\n(.*?)\n## Source packages", without_custom, re.S)
    if not section:
        raise ValueError("Cannot locate formatting rules in SKILL.md")
    existing_keys = {formatting_key(line[2:]) for line in section.group(1).splitlines() if line.startswith("- ")}
    additions = []
    for rule in formatting_rules:
        key = formatting_key(rule)
        if key not in existing_keys:
            additions.append("- " + rule)
            existing_keys.add(key)
    if additions:
        marker_block = FORMAT_BEGIN + "\n" + "\n".join(additions) + "\n" + FORMAT_END + "\n\n"
        without_custom = without_custom.replace("## Source packages", marker_block + "## Source packages", 1)
    changes[skill_path] = without_custom

    dashboard_original = DASHBOARD.read_text(encoding="utf-8")
    domain_link = re.search(
        r"(?m)^- \[\[Literature Database\.base\|([^\]]+)\]\] — notes with "
        r"(?:morphology-related columns|configured domain properties)", dashboard_original,
    )
    if not domain_link:
        raise ValueError("Cannot identify the domain view link in the Dashboard")
    old_domain_view = domain_link.group(1)
    original = BASE.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    result = []
    view = ""
    old_view_name = None
    inserted_in_view = False
    skip_sort_direction = False
    for line in lines:
        if skip_sort_direction:
            skip_sort_direction = False
            if re.match(r"        direction: \w+", line):
                continue
        match = re.match(r"    name: (.*)\s*$", line)
        if match:
            view = match.group(1).strip()
            inserted_in_view = False
            if view == old_domain_view:
                old_view_name = view
                line = f"    name: {view_name}\n"
        match = re.match(r"(      - )(\w+)(\s*)$", line)
        if match and match.group(2) in old_names:
            if view in {"All Literature", old_domain_view}:
                if not inserted_in_view:
                    result.extend(f"{match.group(1)}{name}\n" for name in names)
                    inserted_in_view = True
            elif match.group(2) in names:
                result.append(line)
            continue
        match = re.match(r"(      - property: )(\w+)(\s*)$", line)
        if match and match.group(2) in old_names:
            if match.group(2) in names:
                result.append(line)
            elif names:
                result.append(f"{match.group(1)}{names[0]}\n")
            else:
                skip_sort_direction = True
            continue
        result.append(line)
    base_text = "".join(result)
    if set(old_names) == set(names):
        base_text = original.replace(f"    name: {old_domain_view}\n", f"    name: {view_name}\n", 1)
    changes[BASE] = base_text
    original = dashboard_original
    if old_view_name and old_view_name != view_name:
        original = original.replace(f"|{old_view_name}]]", f"|{view_name}]]")
        original = original.replace(f"#{old_view_name}]]", f"#{view_name}]]")
        original = original.replace("— notes with morphology-related columns; this view currently has no morphology filter.", "— notes with configured domain properties.")
    changes[DASHBOARD] = original

    changed = [path for path, content in changes.items() if path.read_text(encoding="utf-8") != content]
    if not dry_run:
        for path in changed:
            path.write_text(changes[path], encoding="utf-8", newline="")
    return changed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG, help="YAML configuration path")
    parser.add_argument("--check", action="store_true", help="Show files that would change")
    args = parser.parse_args()
    for changed_path in apply(args.config, dry_run=args.check):
        print(changed_path.relative_to(ROOT))
