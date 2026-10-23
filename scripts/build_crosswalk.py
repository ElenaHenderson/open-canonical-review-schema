#!/usr/bin/env python3
# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Build the OCRS crosswalk in crosswalk/: which source field fills each OCRS field, per system.

The crosswalk is generated, never edited: every registered mapper (and the saved-page OpenReview
mapper) is run over the fixtures the tests use, and what it did is read back.

- AI reviewers (`map_with_record`): each step of the mapping record gives the source field and
  the rule (`copied`, `lookup`, `parsed`, `anchored_exact`, `anchored_fuzzy`).
- OpenReview saved page: `extensions.openreview.source_fields` gives the page field and `how`.
- Every other mapper records no steps. Its column holds `observed`: the OCRS fields its reviews
  fill, with no source field. Fields a recorded mapper fills without a step (the envelope's
  `review_id`, say) are `observed` too.

A review's fields are named by their schema path with `[]` for list positions. A path the schema
does not list (a key inside an open object, an item of a list of strings) is cut back to the
longest path it does list. Paths under these hold opaque source data and are left out:

- `extensions`
- `provenance.raw_payload`
- `checks[].procedure.settings`
- `referees[].ai_referee.system.models[].parameters`
- `referees[].ai_referee.system.tools[].config`

`fixtures` counts reviews, not files: an OpenAIReview paper.json holds one review per model, and
a saved OpenReview page one per Official Review. For the same reason, OpenAIReview's `unmapped`
counts add up over every model run: each run counts the other models' entries as unmapped.

Usage: `uv run scripts/build_crosswalk.py` writes crosswalk/; `--check` compares instead and
exits 1 on any difference. scripts/generate_docs.py publishes it beside the current schema.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import io
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
OUT = ROOT / "crosswalk"
sys.path[:0] = [str(ROOT / "src"), str(TESTS)]

from test_real_reviews import REAL, SOURCES, form  # noqa: E402
from test_roundtrip import AI_REVIEWS, AI_RUN, AI_SOURCES, LOSSES, SOURCE_REVIEWS  # noqa: E402

from ocrs import map_from, map_with_record  # noqa: E402
from ocrs.gaps import generic_path, iter_leaves  # noqa: E402
from ocrs.mappers.openaireview import method_wildcard  # noqa: E402
from ocrs.mappers.openreview_page import reviews_from_forum_page  # noqa: E402
from ocrs.registry import supported_sources  # noqa: E402
from ocrs.schema import load_schema, schema_id  # noqa: E402

SKIPPED = (
    "extensions",
    "provenance.raw_payload",
    "checks[].procedure.settings",
    "referees[].ai_referee.system.models[].parameters",
    "referees[].ai_referee.system.tools[].config",
)
PAGE = "openreview_page"
AI_BLOCKS = TESTS / "fixtures" / "ai" / "paper_blocks.json"
PAGE_FIXTURES = sorted((TESTS / "fixtures" / "openreview").glob("*.html"))
# Fixture folders named otherwise than their system, in test_roundtrip.LOSSES
FOLDER_SYSTEM = {"journal": "journal_narrative", "openreview_v2": "openreview"}
TOP_LEVEL = "top level"
SECTION_ORDER = [TOP_LEVEL, "opinion", "findings", "metrics", "referees", "target"]
RECORDED = "fields and sources recorded"
OBSERVED = "fields observed, sources not recorded"


# The schema


def under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith((f"{prefix}.", f"{prefix}["))


def is_skipped(path: str) -> bool:
    return any(under(path, prefix) for prefix in SKIPPED)


def schema_fields(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every property path, with its types and whether every valid review has it.

    Like `ocrs.gaps.iter_schema_paths`, plus `type` and `required`. A path is required when it
    is required in its parent and its parent is required; inside a oneOf or anyOf alternative
    nothing is."""
    fields: dict[str, dict[str, Any]] = {}

    def walk(node: dict[str, Any], path: str, required: bool, seen: frozenset[str]) -> None:
        ref = node.get("$ref")
        if ref:
            if ref not in seen:
                name = ref.removeprefix("#/$defs/")
                walk(schema["$defs"][name], path, required, seen | {ref})
            return
        if path in fields:
            types = node.get("type", [])
            fields[path]["type"].update([types] if isinstance(types, str) else types)
            if "enum" in node or "const" in node:
                fields[path]["type"].add("enum")
        for alternative in node.get("oneOf", []) + node.get("anyOf", []):
            walk(alternative, path, False, seen)
        for part in node.get("allOf", []):
            walk(part, path, required, seen)
        if isinstance(node.get("items"), dict):
            walk(node["items"], f"{path}[]", required, seen)
        needed = set(node.get("required", []))
        for key, child in node.get("properties", {}).items():
            child_path = f"{path}.{key}" if path else key
            field = fields.setdefault(child_path, {"type": set(), "required": False})
            field["required"] |= required and key in needed
            walk(child, child_path, required and key in needed, seen)

    walk(schema, "", True, frozenset())
    return {path: field for path, field in fields.items() if not is_skipped(path)}


def leaves(fields: dict[str, Any]) -> list[str]:
    """Paths no other path extends."""
    paths = sorted(fields)
    return [p for i, p in enumerate(paths) if not any(under(q, p) for q in paths[i + 1 :])]


def schema_path(path: str, known: set[str]) -> str:
    """`path` with list positions as `[]`, cut back to the longest path the schema lists."""
    path = generic_path(path)
    while path and path not in known:
        path = path[:-2] if path.endswith("[]") else path.rpartition(".")[0]
    return path


# Running the mappers


def load(path: Path) -> Any:
    return json.loads(path.read_text()) if path.suffix == ".json" else path.read_text()


def ai_runs(system: str, path: Path, blocks: list | None = None) -> list[tuple]:
    """An AI reviewer's output mapped with its record: a paper.json once for each model."""
    output = load(path)
    models = [None]
    if system == "openaireview":
        models = [m["model"] for k, m in output["methods"].items() if k.startswith("progressive__")]
    results = [
        map_with_record(system, output, **{**AI_RUN, "model_id": model}, blocks=blocks)
        for model in models
    ]
    return [(system, path, result.review, result) for result in results]


def runs() -> list[tuple[str, Path, dict[str, Any], Any]]:
    """(system, fixture, review, record or None) for every review in the fixtures."""
    out = []
    for param in SOURCE_REVIEWS:
        system, path, how = param.values
        out.append((system, path, map_from(system, load(path), **how), None))
    for param in AI_REVIEWS:
        system, path, _ = param.values
        # The paper's text is that of the OpenAIReview review; the other reports are invented
        blocks = load(AI_BLOCKS) if system == "openaireview" else None
        out.extend(ai_runs(system, path, blocks))
    for source in SOURCES:
        system, path = source["system"], REAL / source["file"]
        if system in AI_SOURCES:
            out.extend(ai_runs(system, path))
        else:
            payload = load(path)
            out.append((system, path, map_from(system, payload, **form(source, payload)), None))
    for path in PAGE_FIXTURES:
        out.extend((PAGE, path, review, None) for review in reviews_from_forum_page(load(path)))
    return out


def source_generic(system: str, path: Path) -> Any:
    """How a system's source paths are made generic: OpenAIReview names each model's run."""
    if system == "openaireview":
        return method_wildcard(list(load(path)["methods"]))
    return generic_path


def collect(fields: dict[str, Any]):
    # A list item is a place too: a step may fill a whole finding, `findings.weaknesses[0]`
    known = set(fields) | {
        p[: i + 2] for p in fields for i in range(len(p)) if p[i : i + 3] == "[]."
    }
    # (path, system, source_field, method) → fixtures, and the headings a saved page gave
    seen: dict[tuple[str, str, str, str], set[tuple[str, int]]] = defaultdict(set)
    headings: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    # (system, kind, source_field, path) → count
    gaps: dict[tuple[str, str, str, str], int] = defaultdict(int)
    fixtures: dict[str, int] = defaultdict(int)
    # system → OCRS paths its reviews fill, whoever the mapper credits them to
    filled: dict[str, set[str]] = defaultdict(set)
    for index, (system, path, review, result) in enumerate(runs()):
        fixture = (path.relative_to(ROOT).as_posix(), index)
        fixtures[system] += 1
        # (OCRS path, source field, method, heading) for each value the mapper says it took
        links: list[tuple[str, str, str, str]] = []
        if result is not None:
            generic = source_generic(system, path)
            for step in result.record.steps:
                links.append((step.target, generic(step.source), step.rule.value, ""))
            for field in result.record.gaps.unmapped:
                gaps[(system, "unmapped", field.path, "")] += field.count
            for c in result.record.gaps.coerced:
                gaps[(system, "coerced", generic(c.source), schema_path(c.target, known))] += 1
        elif system == PAGE:
            page = review["extensions"]["openreview"]
            for e in page["source_fields"]:
                links.append((e["ocrs"], e["field"], e["how"], e.get("heading", "")))
            for label in page["unmapped_fields"]:
                gaps[(system, "unmapped", label, "")] += 1
        else:
            kept = dict(review.get("extensions", {}).get(system) or {})
            # The caller's scale bounds, not the source's: added by ocrs.registry.map_from
            kept.pop("caller_scale_bounds", None)
            for leaf, _ in iter_leaves(kept):
                gaps[(system, "unmapped", generic_path(leaf), "")] += 1
        covered = [target for target, *_ in links]
        for leaf, _ in iter_leaves(review):
            filled[system].add(schema_path(leaf, known))
            if not any(under(leaf, target) for target in covered):
                links.append((leaf, "", "observed", ""))
        for target, source, method, heading in links:
            target_path = schema_path(target, known)
            if not target_path or is_skipped(target_path):
                continue
            key = (target_path, system, source, method)
            seen[key].add(fixture)
            if heading:
                headings[key].add(heading)
    for fixture, changes in LOSSES.items():
        folder = fixture.split("/")[0]
        for change in changes:
            sign, field = change.split(" ", 1)
            if sign == "-":
                gaps[(FOLDER_SYSTEM.get(folder, folder), "lost_on_roundtrip", field, "")] += 1
    return seen, headings, gaps, fixtures, filled


# Writing


def csv_text(header: list[str], rows: list[list[Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def md_cell(text: Any) -> str:
    return str(text).replace("|", "\\|")


def section_of(path: str) -> str:
    """The top-level field a path is under; fields at the top level are grouped as one."""
    section = path.split(".")[0].split("[")[0]
    return section if section != path else TOP_LEVEL


def build() -> dict[str, str]:
    schema = load_schema()
    fields = schema_fields(schema)
    seen, headings, gaps, fixtures, filled = collect(fields)
    systems = sorted([*supported_sources(), PAGE])
    recorded = {system for _, system, _, method in seen if method != "observed"}
    rows = sorted(set(leaves(fields)) | {path for path, *_ in seen})
    leaf_set = set(leaves(fields))

    long_rows = []
    cells: dict[tuple[str, str], list[str]] = defaultdict(list)
    for key in sorted(seen):
        path, system, source, method = key
        notes = "headings: " + "; ".join(sorted(headings[key])) if headings[key] else ""
        long_rows.append([path, system, "from", source, method, len(seen[key]), notes])
        cells[(path, system)].append(f"{method}:{source}" if source else method)

    def describe(path: str) -> tuple[str, str]:
        field = fields.get(path, {"type": set(), "required": False})
        return ("yes" if field["required"] else "", " ".join(sorted(field["type"])))

    wide_rows = [
        [path, *describe(path), *(" | ".join(cells[(path, s)]) for s in systems)] for path in rows
    ]

    gap_rows = [[*key[:3], key[3], count] for key, count in sorted(gaps.items())]

    required = {path for path in leaf_set if fields[path]["required"]}
    coverage_rows = []
    for system in systems:
        fills = leaf_set & filled[system]
        unmapped = sum(1 for s, kind, *_ in gaps if s == system and kind == "unmapped")
        coverage_rows.append(
            [
                system,
                len(fills),
                f"{100 * len(fills) / len(leaf_set):.1f}",
                len(fills & required),
                len(required),
                unmapped,
                fixtures[system],
                RECORDED if system in recorded else OBSERVED,
            ]
        )

    return {
        "crosswalk.long.csv": csv_text(
            ["ocrs_path", "system", "direction", "source_field", "method", "fixtures", "notes"],
            long_rows,
        ),
        "crosswalk.csv": csv_text(["ocrs_path", "required", "type", *systems], wide_rows),
        "gaps.csv": csv_text(["system", "kind", "source_field", "ocrs_path", "count"], gap_rows),
        "coverage.csv": csv_text(
            [
                "system",
                "leaf_paths_filled",
                "leaf_paths_filled_pct",
                "required_paths_filled",
                "required_paths",
                "unmapped_source_fields",
                "fixtures",
                "columns",
            ],
            coverage_rows,
        ),
        "CROSSWALK.md": markdown(systems, wide_rows, gap_rows, coverage_rows, len(leaf_set)),
    }


def markdown(systems, wide_rows, gap_rows, coverage_rows, leaf_count) -> str:
    version = schema_id()
    lines = [
        "# OCRS crosswalk",
        "",
        "**This file is generated. Do not edit it.** Run `uv run scripts/build_crosswalk.py` to "
        "rebuild it.",
        "",
        "The crosswalk shows what each mapper does on the test fixtures. A blank cell means no "
        "fixture for that system filled the field. It does not always mean the system cannot "
        "fill it.",
        "",
        "## How it is made",
        "",
        "The generator runs each mapper over every fixture in `tests/fixtures/` and "
        "`tests/fixtures/real/` for its system. It then reads back where each OCRS value came "
        "from.",
        "",
        "- The AI reviewers (DeepReview, OpenAIReview, Reviewer3) keep a mapping record. Each "
        "step names the reviewer's field and how its value was taken.",
        "- The saved-page OpenReview mapper (`openreview_page`) lists the page field behind "
        "each value.",
        "- The other mappers keep no record. Their columns say only which OCRS fields their "
        "reviews fill: **fields observed, sources not recorded**.",
        "",
        "## How to read it",
        "",
        "Each cell is `method:source_field`. Several are separated by `|`.",
        "",
        "| Method | Meaning |",
        "|---|---|",
        "| `copied` | The value was copied as it was. |",
        "| `lookup` | The value was looked up in a table (a label to a recommendation, say). |",
        "| `parsed` | The value was read from the text by a pattern (a page number, say). |",
        "| `anchored_exact` | A quote was found word for word in the paper. |",
        "| `anchored_fuzzy` | A quote was found approximately in the paper. |",
        "| `observed` | The field was filled, but the mapper does not say from what. |",
        "",
        "Paths use `[]` for any list position. The files beside this one hold the same data:",
        "",
        "- `crosswalk.long.csv`: one row per OCRS field, system and source field, with the "
        "number of fixtures that showed it.",
        f"- `crosswalk.csv`: one row per OCRS field, including all {leaf_count} leaf fields, "
        "one column per system.",
        "- `gaps.csv`: source fields with no OCRS field, fields lost on a round trip, and "
        "values coerced to an allowed one.",
        "- `coverage.csv`: the table below.",
        "",
        f"Schema: `{version}`.",
        "",
        "## Coverage",
        "",
        f"Out of {leaf_count} OCRS leaf fields.",
        "",
        "| System | Leaf fields filled | % | Required filled | Unmapped source fields "
        "| Fixtures | Column |",
        "|---|---|---|---|---|---|---|",
    ]
    for system, filled, pct, req, req_total, unmapped, count, kind in coverage_rows:
        lines.append(
            f"| `{system}` | {filled} | {pct} | {req} of {req_total} | {unmapped} "
            f"| {count} | {kind} |"
        )

    lines += ["", "## Fields by section", ""]
    lines += [
        "Only fields at least one system fills are shown. `crosswalk.csv` lists every field.",
    ]
    by_section: dict[str, list[list[str]]] = defaultdict(list)
    for row in wide_rows:
        by_section[section_of(row[0])].append(row)
    order = SECTION_ORDER + sorted(set(by_section) - set(SECTION_ORDER))
    header = "| OCRS field | Required | " + " | ".join(f"`{s}`" for s in systems) + " |"
    rule = "|---|---|" + "---|" * len(systems)
    for section in order:
        rows = by_section.get(section, [])
        filled = [row for row in rows if any(row[3:])]
        title = section if section == TOP_LEVEL else f"`{section}`"
        lines += ["", f"### {title}"]
        if filled:
            lines += ["", header, rule]
            for path, req, _, *values in filled:
                lines.append(
                    f"| `{path}` | {req} | " + " | ".join(md_cell(v) for v in values) + " |"
                )
        if len(rows) > len(filled):
            unfilled = len(rows) - len(filled)
            lines += ["", f"No fixture fills {unfilled} of the {len(rows)} fields in this section."]

    lines += [
        "",
        "## Gaps",
        "",
        "- **unmapped**: a source field with no OCRS field. Its value is kept in "
        "`extensions.<system>`. The count is how many times it was seen. An OpenAIReview "
        "paper.json is mapped once per model, and each run counts the other models' entries as "
        "unmapped, so its counts add up over all the models.",
        "- **lost_on_roundtrip**: a source field that does not come back when an OCRS review is "
        "written in the source's format again. Taken from `tests/test_roundtrip.py`. The count "
        "is how many fixtures lose it.",
        "- **coerced**: a source value OCRS does not allow, replaced by the nearest allowed one.",
    ]
    by_system: dict[str, list[list[Any]]] = defaultdict(list)
    for row in gap_rows:
        by_system[row[0]].append(row)
    for system in systems:
        lines += ["", f"### `{system}`", ""]
        if not by_system[system]:
            lines.append("No gaps seen.")
            continue
        lines += ["| Kind | Source field | OCRS field | Count |", "|---|---|---|---|"]
        for _, kind, source, path, count in by_system[system]:
            target = f"`{path}`" if path else ""
            lines.append(f"| {kind} | `{md_cell(source)}` | {target} | {count} |")
    return "\n".join(lines) + "\n"


def outputs() -> dict[Path, str]:
    """Each file to write, by its path from the repository root."""
    return {Path("crosswalk") / name: text for name, text in build().items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare, write nothing")
    args = parser.parse_args()
    files = outputs()
    if not args.check:
        for path, text in files.items():
            (ROOT / path).parent.mkdir(exist_ok=True)
            (ROOT / path).write_text(text)
        return 0
    failed = False
    with tempfile.TemporaryDirectory() as tmp:
        for path, text in files.items():
            fresh = Path(tmp) / path
            fresh.parent.mkdir(parents=True, exist_ok=True)
            fresh.write_text(text)
            current = ROOT / path
            old = current.read_text() if current.exists() else ""
            if old != fresh.read_text():
                failed = True
                sys.stdout.writelines(
                    difflib.unified_diff(
                        old.splitlines(keepends=True),
                        text.splitlines(keepends=True),
                        path.as_posix(),
                        f"{path.as_posix()} (regenerated)",
                    )
                )
    if failed:
        print(
            "\nThe crosswalk is out of date. Run: uv run scripts/build_crosswalk.py",
            file=sys.stderr,
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
