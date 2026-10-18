# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Reviewer3 report (Markdown) → OCRS.

Reviewer3 exports its report as Markdown:

    # Review Report
    <the paper's title>                 → target.title
    ### Overview                        → opinion.contributions
    ### AI Text Detection               → checks[]: ai_text_detection
    ### Fatal Flaws                     → checks[]: fatal_flaw_screen
    ### Reference Check                 → checks[]: reference_verification
    ### Reviewer Comments               → findings.comments

The mapper first parses the report into the export's own structure, and the paths
in the mapping record name places in it:

    title, overview[i].{title, text}, ai_text_detection,
    fatal_flaws.{text, items[i].{title, text}},
    reference_check.{summary, entries[i].{number, citation, status}, text},
    comments[i].{number, title, page, page_end, excerpt, text},
    other.<heading>, other.preamble (text above the first section, other than the
    report's wrapper and title)

Overview bullets (`**Title** — text`) are what the reviewer reads the paper as
contributing; they make no judgment, so they are contributions, not strengths.

The three checks keep the report's own sentence as their `summary`. A check gets an
`outcome` only when the report states one: "No fatal methodological flaws were
identified" is `no_issues`, and fatal flaws listed as points are `issues_found`,
each a `critical` weakness the check names in `finding_ids`. The AI-text and
reference checks report numbers without a verdict, so they get none. Percentages
become `measurements` as 0–1 fractions (33% → 0.33), the detector named in the
sentence ("the full Pangram report") becomes `performed_by`, and the reference
counts become integer measurements. Each row of the reference table becomes an
item with the entry's number and citation as printed and its status in the
report's words. An entry is `flagged` when its status says it failed ("Not Found",
"Unverified") and not flagged when it says it passed ("Verified (DOI)"); a status
that says neither ("Pending") gets no `flagged`, rather than a guess. "Not Found"
does not mean the reference is wrong.

Reviewer Comments are numbered points: `N. **Title**`, optionally `— Page N`, an
optional excerpt of the paper as a blockquote, then the explanation. The report
does not say whether a comment is a weakness, a question or a remark, so comments
go in `findings.comments`, with no severity. A comment's page and excerpt give
one evidence link: a quote with its page, or, when the excerpt is only a label
such as `Fig 3`, a link to that figure. Places the explanation names only in its
prose are not parsed.

The report is Markdown with TeX, so the review's `text_format` says so. All
values read by a pattern are recorded as `parsed` steps.
"""

from __future__ import annotations

import re
from typing import Any

from ..anchors import Block
from ..mapping import MappingResult
from .ai import Recorder, finish

MAPPER_VERSION = "1.0.0"
TEXT_FORMAT = {"markup": "markdown", "math": "tex"}
# OCRS requires a check to say something: one of these
CHECK_CONTENT = {"summary", "outcome", "measurements", "items"}
COMMENTS_GROUP = "Reviewer Comments"
FATAL_SEVERITY = {"Fatal Flaws": "critical"}
SECTIONS = {
    "Overview": "overview",
    "AI Text Detection": "ai_text_detection",
    "Fatal Flaws": "fatal_flaws",
    "Reference Check": "reference_check",
    "Reviewer Comments": "comments",
}
WRAPPER = {"# Review Report", "---"}

SECTION = re.compile(r"^### (?!#)(.*)$", re.MULTILINE)
BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
# A list marker may sit up to three spaces in (CommonMark); deeper markers are nested items
# A line that starts a block of its own, so it never lazily continues a point: a blockquote,
# a heading, a thematic break or an ordered list item
NEW_BLOCK = re.compile(r"^ {0,3}(?:>|#{1,6}(?:\s|$)|(?:[-*_]\s*){3,}$|\d{1,9}[.)](?:\s|$))")
TOP_BULLET = re.compile(r"^( {0,3})([-*]\s+)(.*)$")
TITLED = re.compile(r"^\*\*(.+?)\*\*\s*(?:[—–:]|\s-)?\s*(.*)$", re.DOTALL)
COMMENT_START = re.compile(
    r"^( {0,3})(\d+)\.\s+\*\*(.+?)\*\*\s*(?:[—–-]\s*Pages?\s+(\d+)(?:\s*[–-]\s*(\d+))?)?\s*$"
)
# A fenced code block opens and closes with three or more backticks or tildes
# (a backtick fence's info string has no backticks, so ```example``` is inline code, not a fence)
FENCE = re.compile(r"^ {0,3}(`{3,}(?=[^`]*$)|~{3,})")
# A closing fence has nothing after its marker but whitespace (```python opens, never closes)
CLOSING_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*$")


class Fences:
    """Tracks whether a line is inside a fenced code block, line by line."""

    def __init__(self) -> None:
        self.open: str | None = None

    def inside(self, line: str) -> bool:
        """Whether `line` is part of a fence (its opening and closing lines included)."""
        fence = FENCE.match(line)
        if self.open is None:
            if fence:
                self.open = fence.group(1)
                return True
            return False
        closing = CLOSING_FENCE.match(line)
        if closing and closing.group(1)[0] == self.open[0]:
            if len(closing.group(1)) >= len(self.open):
                self.open = None
        return True


# The excerpt is a label, not the paper's text: `Fig 3`, `Figure 2(b)`, `Table 1`, `Eq. (4)`
LABEL_TYPES = [
    (re.compile(r"^fig(?:ure)?s?\.?\s*\(?\d+[a-z]?\)?(?:\([a-z]\))?$", re.IGNORECASE), "figure"),
    (re.compile(r"^tables?\.?\s*\(?[\dIVX]+[a-z]?\)?$", re.IGNORECASE), "table"),
    (re.compile(r"^eq(?:uation)?s?\.?\s*\(?\d+[a-z]?\)?$", re.IGNORECASE), "equation"),
]
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%\s+([A-Za-z][\w-]*)")
DETECTOR = re.compile(r"\bfull ([A-Z][\w.-]*(?: [A-Z][\w.-]*)*) report\b")
NO_FATAL = re.compile(r"^No fatal\b[^.]*\b(?:identified|found|detected)\b", re.IGNORECASE)
CHECKED = re.compile(r"\bChecked\s+(\d+)\s+references?\b", re.IGNORECASE)
COUNT = re.compile(r"(\d+)\s+([a-z][a-z ]*?)\s*(?=[,.;]|$)")
# The .docx renders a reference row as `#12 — Citation: … — Status: Not Found`
ENTRY_LINE = re.compile(r"^#(\d+)\s*[—–-]\s*Citation:\s*(.+?)\s*[—–-]\s*Status:\s*(.+)$")
# A status's verdict. A problem it rules out ("No errors", "No mismatch") reads as passing;
# then failure phrases are checked before passing words, so "Not Found" is never "Found"
PROBLEM = r"(?:errors?|mismatch(?:es)?|issues?|problems?|discrepanc(?:y|ies))"
# The whole ruled-out list: "no errors or mismatches", "without errors, issues and problems"
NEGATED_PROBLEM = re.compile(
    rf"\b(?:no|without|zero)\s+{PROBLEM}(?:\s*(?:,|/|\bor\b|\band\b|\bnor\b)\s*{PROBLEM})*\b",
    re.IGNORECASE,
)
# A problem the status says was dealt with: "Mismatch resolved" (but "not resolved" fails)
RESOLVED_PROBLEM = re.compile(
    rf"\b{PROBLEM}\s+(?:(?:was|were|has been|have been)\s+)?(?:resolved|fixed|corrected|cleared)\b",
    re.IGNORECASE,
)
FAILED_STATUS = re.compile(
    r"\b(?:not\s+(?:found|verified|matched|resolved|available)|no\s+(?:match|record|result)s?|"
    r"unverified|unresolved|unmatched|missing|fail(?:ed|s|ure)?|errors?|mismatch(?:ed|es)?|"
    r"invalid|retracted|broken)\b",
    re.IGNORECASE,
)
PASSED_STATUS = re.compile(
    r"\b(?:verified|found|ok|matched|valid|confirmed|resolved)\b", re.IGNORECASE
)


def status_flag(status: str) -> bool | None:
    """True when the status says the check failed, False when it says it passed, and None
    when it says neither."""
    cleared = RESOLVED_PROBLEM.sub(" ok ", NEGATED_PROBLEM.sub(" ok ", status))
    if FAILED_STATUS.search(cleared):
        return True
    if PASSED_STATUS.search(cleared):
        return False
    return None


UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
TABLE_FIELDS = {"#": "number", "citation": "citation", "status": "status"}
BLOCKQUOTE = re.compile(r"^\s*> ?")
EMPHASIS = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")


def trim_blank_lines(lines: list[str]) -> str:
    """`lines` joined, without blank lines at either end; indentation and trailing spaces
    (a Markdown hard break) are kept."""
    start = next((i for i, line in enumerate(lines) if line.strip()), len(lines))
    end = next((i for i in range(len(lines), 0, -1) if lines[i - 1].strip()), start)
    return "\n".join(lines[start:end])


def prose_paragraphs(text: str) -> list[str]:
    """The paragraphs of `text` outside fenced code, each stripped."""
    paragraphs: list[list[str]] = [[]]
    fences = Fences()
    for line in text.splitlines():
        if fences.inside(line) or not line.strip():
            paragraphs.append([])
        else:
            paragraphs[-1].append(line.strip())
    return [" ".join(lines) for lines in paragraphs if lines]


def plain(text: str) -> str:
    """`text` without bold markers, which the report puts on counts and statuses."""
    return EMPHASIS.sub(lambda m: m.group(1) or m.group(2), text).strip()


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")


# Parsing the report


def split_sections(markdown: str) -> list[tuple[str | None, str]]:
    """(heading, body) for each `###` section; text before the first has None. A heading
    inside a fenced code block is part of the code."""
    parts: list[tuple[str | None, str]] = []
    heading: str | None = None
    lines: list[str] = []
    fences = Fences()
    for line in markdown.splitlines():
        match = None if fences.inside(line) else SECTION.match(line)
        if match:
            parts.append((heading, "\n".join(lines)))
            heading, lines = match.group(1).strip(), []
        else:
            lines.append(line)
    parts.append((heading, "\n".join(lines)))
    return parts


def keep(other: dict[str, str], heading: str, text: str) -> None:
    """Keep text the mapper has no field for, adding to any already kept under `heading`."""
    if text:
        other[heading] = f"{other[heading]}\n\n{text}" if heading in other else text


def parse_bullets(body: str) -> tuple[list[dict[str, str]], str]:
    """Bulleted points as {title, text} (`**Title** — text`) or {text}, and the other text.

    A point runs on through blank lines and indented lines, so its paragraphs, nested
    lists and code blocks are kept as written, less the list's own indentation.
    """
    items: list[tuple[int, list[str]]] = []  # (content indentation, lines)
    rest: list[str] = []
    in_item = False
    list_indent: int | None = None
    fences = Fences()
    for line in body.splitlines():
        # A line of fenced code is never a point, though it may continue one
        code = fences.inside(line)
        bullet = None if code else TOP_BULLET.match(line)
        if bullet and (list_indent is None or len(bullet.group(1)) <= list_indent):
            list_indent = len(bullet.group(1)) if list_indent is None else list_indent
            items.append((len(bullet.group(1)) + len(bullet.group(2)), [bullet.group(3)]))
            in_item = True
        elif in_item and (not line.strip() or line.startswith((" ", "\t"))):
            items[-1][1].append(line)
        elif in_item and not code and items[-1][1][-1].strip() and not NEW_BLOCK.match(line):
            # A lazy continuation: an unindented line straight after the point's text,
            # with no blank line between, still belongs to it (a soft-wrapped bullet)
            items[-1][1].append(line)
        elif line.strip():
            rest.append(line)
            in_item = False  # an unindented line ends the point
        elif not in_item:
            rest.append(line)  # a blank line between paragraphs of other prose
    points = []
    for content_indent, lines in items:
        # Dedent by the point's own content indentation, so deeper indentation (a nested
        # list, an indented code block) is kept
        more = [
            line[min(content_indent, len(line) - len(line.lstrip(" "))) :] for line in lines[1:]
        ]
        text = "\n".join([lines[0], *more]).strip()
        titled = TITLED.match(text)
        if titled and titled.group(2).strip():
            points.append({"title": titled.group(1).strip(), "text": titled.group(2).strip()})
        else:
            points.append({"text": text})
    return points, "\n".join(rest).strip("\n").rstrip()


def table_cells(line: str) -> list[str]:
    """A table row's cells, split at unescaped pipes; `\\|` in a cell is a literal pipe."""
    row = line.strip()
    row = row[1:] if row.startswith("|") else row
    row = row[:-1] if row.endswith("|") and not row.endswith("\\|") else row
    return [cell.strip().replace("\\|", "|") for cell in UNESCAPED_PIPE.split(row)]


def table_rows(lines: list[str]) -> list[dict[str, str]]:
    """A Markdown table's rows as {header: cell}, without the separator row. Cells past the
    header are kept as `column_<n>`, so nothing in a malformed row is lost."""
    cells = [table_cells(line) for line in lines]
    if len(cells) < 2:
        return []
    header = [plain(name).casefold() for name in cells[0]]
    rows = [row for row in cells[1:] if not all(set(cell) <= set("-: ") for cell in row)]
    keys = [
        *header,
        *(f"column_{n + 1}" for n in range(len(header), max(map(len, rows), default=0))),
    ]
    return [dict(zip(keys, row, strict=False)) for row in rows]


def parse_references(body: str) -> dict[str, Any]:
    """The counts sentence, an entry per row of the table (or per `#N — Citation:` line),
    and any other text."""
    fences = Fences()
    lines = [(line, fences.inside(line)) for line in body.splitlines()]
    # Table rows and `#N — Citation:` entries count only outside code; examples stay prose
    table = [line for line, code in lines if not code and line.strip().startswith("|")]
    entries = []
    for row in table_rows(table):
        # The columns the mapper knows, by its names; any other column as the report names it
        entry = {TABLE_FIELDS.get(key, slug(key) or key): value for key, value in row.items()}
        if "number" in entry:
            entry["number"] = entry["number"].lstrip("#")
        entries.append({key: value for key, value in entry.items() if value})
    # Prose is kept as written, blank lines and indentation included
    text: list[str] = []
    for line, code in lines:
        if code:
            text.append(line)
            continue
        if line.strip().startswith("|"):
            continue
        entry_line = ENTRY_LINE.match(BULLET.sub(r"\1", line).strip())
        if entry_line:
            number, citation, status = entry_line.groups()
            entries.append({"number": number, "citation": citation, "status": status})
        else:
            text.append(line)
    parsed: dict[str, Any] = {}
    first = next((index for index, line in enumerate(text) if line.strip()), None)
    if first is not None and CHECKED.search(plain(text[first])):
        parsed["summary"] = text.pop(first).strip()
    if entries:
        parsed["entries"] = entries
    prose = "\n".join(text).strip("\n").rstrip()
    if prose.strip():
        parsed["text"] = prose
    return parsed


def parse_comments(body: str) -> tuple[list[dict[str, str]], str]:
    """The numbered comments, each with its title, page, excerpt and explanation, and any
    text above the first."""
    comments: list[dict[str, Any]] = []
    above: list[str] = []
    lines: list[str] = []
    fences = Fences()
    list_indent: int | None = None
    for line in body.splitlines():
        # A comment starts at the list's own indentation, outside code: deeper numbered
        # items and code are part of the explanation
        in_code = fences.inside(line)
        start = None if in_code else COMMENT_START.match(line)
        if start and list_indent is not None and len(start.group(1)) > list_indent:
            start = None
        if start:
            list_indent = len(start.group(1)) if list_indent is None else list_indent
            if comments:
                comments[-1]["lines"] = lines
            _, number, title, page, page_end = start.groups()
            comments.append({"number": number, "title": title.strip(), "page": page})
            if page_end:
                comments[-1]["page_end"] = page_end
            lines = []
        elif comments:
            lines.append(line)
        elif line.strip():
            above.append(line)
    if comments:
        comments[-1]["lines"] = lines
    parsed = []
    for comment in comments:
        body_lines = comment.pop("lines")
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        excerpt = []
        while body_lines and body_lines[0].lstrip().startswith(">"):
            # Only the blockquote marker and its one optional space go; code spaces stay
            excerpt.append(BLOCKQUOTE.sub("", body_lines.pop(0), count=1))
        if excerpt:
            comment["excerpt"] = trim_blank_lines(excerpt)
        comment["text"] = trim_blank_lines(body_lines)
        parsed.append({key: value for key, value in comment.items() if value})
    return parsed, "\n".join(above).strip()


def parse_report(markdown: str) -> dict[str, Any]:
    """The report in its own structure (see the module docstring)."""
    report: dict[str, Any] = {}
    other: dict[str, str] = {}
    for heading, body in split_sections(markdown):
        if heading is None:
            lines = [line.strip() for line in body.splitlines()]
            lines = [line for line in lines if line and line not in WRAPPER]
            if lines and not lines[0].startswith("#"):
                report["title"] = lines.pop(0)
            keep(other, "preamble", "\n".join(lines))
        elif heading == "Overview":
            points, rest = parse_bullets(body)
            report.setdefault("overview", []).extend(points)
            keep(other, heading, rest)
        elif heading == "AI Text Detection":
            keep(report, "ai_text_detection", body.strip())
        elif heading in ("Fatal Flaws", "Reference Check") and SECTIONS[heading] in report:
            # One check per kind: a repeated section is kept, not merged or overwritten
            keep(other, heading, body.strip())
        elif heading == "Fatal Flaws":
            items, rest = parse_bullets(body)
            flaws: dict[str, Any] = {}
            if rest:
                flaws["text"] = rest
            if items:
                flaws["items"] = items
            if flaws:
                report["fatal_flaws"] = flaws
        elif heading == "Reference Check":
            references = parse_references(body)
            if references:
                report["reference_check"] = references
        elif heading == COMMENTS_GROUP:
            comments, rest = parse_comments(body)
            report.setdefault("comments", []).extend(comments)
            keep(other, heading, rest)
        else:
            keep(other, heading, body.strip())
    if other:
        report["other"] = other
    return report


# Mapping


def map_contributions(report: dict[str, Any], recorder: Recorder) -> list[dict[str, str]]:
    contributions = []
    for index, point in enumerate(report.get("overview", [])):
        source, target = f"overview[{index}]", f"opinion.contributions[{index}]"
        contribution = {}
        if point.get("title"):
            contribution["title"] = recorder.copy(
                f"{source}.title", f"{target}.title", point["title"]
            )
        contribution["text"] = recorder.copy(f"{source}.text", f"{target}.text", point["text"])
        contributions.append(contribution)
    return contributions


def ai_text_check(sentence: str, target: str, recorder: Recorder) -> dict[str, Any]:
    check: dict[str, Any] = {"id": "ai-text-detection", "kind": "ai_text_detection"}
    check["label"] = "AI Text Detection"
    detector = DETECTOR.search(sentence)
    if detector:
        name = recorder.parse(
            "ai_text_detection", f"{target}.performed_by.name", sentence, detector.group(1)
        )
        check["performed_by"] = {"name": name}
    check["summary"] = recorder.copy("ai_text_detection", f"{target}.summary", sentence)
    measurements = []
    for match in PERCENT.finditer(sentence):
        percent, label = match.groups()
        measurement = {
            "key": slug(label),
            "label": label,
            "value": round(float(percent) / 100, 6),
            "unit": "fraction",
        }
        measurement_target = f"{target}.measurements[{len(measurements)}]"
        measurements.append(
            recorder.parse("ai_text_detection", measurement_target, match.group(0), measurement)
        )
    if measurements:
        check["measurements"] = measurements
    return check


def fatal_flaw_check(
    flaws: dict[str, Any], target: str, weaknesses: list[dict[str, Any]], recorder: Recorder
) -> dict[str, Any]:
    """The screen, and a critical weakness for each flaw it lists."""
    check: dict[str, Any] = {"id": "fatal-flaws", "kind": "fatal_flaw_screen"}
    check["label"] = "Fatal Flaws"
    text = flaws.get("text", "")
    summary: list[tuple[str, str]] = []  # (source path, text)
    if text:
        summary.append(
            ("fatal_flaws.text", recorder.copy("fatal_flaws.text", f"{target}.summary", text))
        )
    finding_ids = []
    for index, item in enumerate(flaws.get("items", [])):
        source = f"fatal_flaws.items[{index}]"
        if not item.get("title") and NO_FATAL.match(item["text"]):
            # A bulleted verdict ("- No fatal … identified."), not a flaw
            verdict_text = recorder.copy(f"{source}.text", f"{target}.summary", item["text"])
            summary.append((f"{source}.text", verdict_text))
            continue
        point_target = f"findings.weaknesses[{len(weaknesses)}]"
        point: dict[str, Any] = {"id": f"fatal-flaw-{index + 1}"}
        if item.get("title"):
            point["title"] = recorder.copy(
                f"{source}.title", f"{point_target}.title", item["title"]
            )
        point["text"] = recorder.copy(f"{source}.text", f"{point_target}.text", item["text"])
        severity = recorder.lookup(
            source, f"{point_target}.severity", "Fatal Flaws", FATAL_SEVERITY
        )
        if severity:
            point["severity"] = severity
        weaknesses.append(point)
        finding_ids.append(point["id"])
    if summary:
        check["summary"] = "\n\n".join(line for _, line in summary)
    # The verdict may be any paragraph of the prose, but not part of a code example
    verdict = next(
        (
            (path, paragraph)
            for path, line in summary
            for paragraph in prose_paragraphs(line)
            if NO_FATAL.match(paragraph)
        ),
        None,
    )
    if finding_ids:
        check["outcome"] = recorder.parse(
            "fatal_flaws.items", f"{target}.outcome", "listed flaws", "issues_found"
        )
        check["finding_ids"] = finding_ids
    elif verdict:
        verdict_path, verdict_line = verdict
        check["outcome"] = recorder.parse(
            verdict_path, f"{target}.outcome", verdict_line, "no_issues"
        )
    return check


def reference_check(references: dict[str, Any], target: str, recorder: Recorder) -> dict:
    check: dict[str, Any] = {"id": "reference-check", "kind": "reference_verification"}
    check["label"] = "Reference Check"
    measurements = []
    summary = references.get("summary")
    if not summary and references.get("text"):
        # Prose without the counts sentence, such as "No references to check.": the summary
        check["summary"] = recorder.copy(
            "reference_check.text", f"{target}.summary", references["text"]
        )
    if summary:
        source = "reference_check.summary"
        check["summary"] = recorder.parse(source, f"{target}.summary", summary, plain(summary))
        sentence = plain(summary)
        checked = CHECKED.search(sentence)
        if checked:
            measurement = {"key": "checked", "value": int(checked.group(1))}
            measurements.append(
                recorder.parse(source, f"{target}.measurements[0]", checked.group(0), measurement)
            )
        counts = sentence.split(":", 1)[1] if ":" in sentence else ""
        for match in COUNT.finditer(counts):
            number, label = match.groups()
            measurement = {"key": slug(label), "value": int(number)}
            measurement_target = f"{target}.measurements[{len(measurements)}]"
            measurements.append(
                recorder.parse(source, measurement_target, match.group(0).strip(), measurement)
            )
    if measurements:
        check["measurements"] = measurements
    items = []
    for index, entry in enumerate(references.get("entries", [])):
        source, item_target = f"reference_check.entries[{index}]", f"{target}.items[{len(items)}]"
        raw_status = entry.get("status", "")
        if not raw_status:
            recorder.skip(source, "no status")
            continue
        link: dict[str, Any] = {"type": "bibliography", "ref": ""}
        if entry.get("number"):
            link["ref"] = recorder.copy(
                f"{source}.number", f"{item_target}.target.ref", entry["number"]
            )
        if entry.get("citation"):
            citation = recorder.copy(
                f"{source}.citation", f"{item_target}.target.work.citation", entry["citation"]
            )
            link["work"] = {"citation": citation}
        status = recorder.parse(
            f"{source}.status", f"{item_target}.status", raw_status, plain(raw_status)
        )
        item: dict[str, Any] = {"target": link, "status": status}
        flagged = status_flag(status)
        if flagged is not None:
            item["flagged"] = recorder.parse(
                f"{source}.status", f"{item_target}.flagged", raw_status, flagged
            )
        items.append(item)
    if items:
        check["items"] = items
    return check


def comment_link(
    comment: dict[str, str],
    source: str,
    target: str,
    recorder: Recorder,
    blocks: list[Block] | None,
) -> dict[str, Any] | None:
    """One evidence link from a comment's page and excerpt, or None when it has neither."""
    page, excerpt = comment.get("page"), comment.get("excerpt")
    if not page and not excerpt:
        return None
    link: dict[str, Any] = {"type": "paper_section", "ref": ""}
    label = next(
        (kind for pattern, kind in LABEL_TYPES if excerpt and pattern.match(excerpt)), None
    )
    if label:
        link["type"] = recorder.parse(f"{source}.excerpt", f"{target}.type", excerpt, label)
        link["ref"] = recorder.copy(f"{source}.excerpt", f"{target}.ref", excerpt)
    elif page:
        pages = f"Page {page}" + (f"–{comment['page_end']}" if comment.get("page_end") else "")
        link["ref"] = recorder.parse(f"{source}.page", f"{target}.ref", page, pages)
    if excerpt and not label:
        link["quote"] = recorder.copy(f"{source}.excerpt", f"{target}.quote", excerpt)
        recorder.anchor(f"{source}.excerpt", target, excerpt, blocks)
    if page:
        location = {
            "page": recorder.parse(f"{source}.page", f"{target}.location.page", page, int(page))
        }
        if comment.get("page_end") and int(comment["page_end"]) > int(page):
            location["page_end"] = recorder.parse(
                f"{source}.page_end",
                f"{target}.location.page_end",
                comment["page_end"],
                int(comment["page_end"]),
            )
        link["location"] = location
    return link


def map_comments(
    report: dict[str, Any], recorder: Recorder, blocks: list[Block] | None
) -> list[dict[str, Any]]:
    comments = []
    parsed = report.get("comments", [])
    # A comment's id follows its printed number when the numbers are unique; a list written
    # `1.`, `1.`, `1.` (valid Markdown) numbers its comments by position instead
    numbers = [comment.get("number") for comment in parsed]
    by_number = all(numbers) and len(set(numbers)) == len(numbers)
    for index, comment in enumerate(parsed):
        source, target = f"comments[{index}]", f"findings.comments[{len(comments)}]"
        if not comment.get("text"):
            # OCRS requires a point's text; the comment stays in extensions
            recorder.skip(source, "no explanation")
            continue
        point_id = f"comment-{comment['number'] if by_number else index + 1}"
        point: dict[str, Any] = {
            "id": recorder.parse(f"{source}.number", f"{target}.id", numbers[index], point_id)
        }
        if comment.get("title"):
            point["title"] = recorder.copy(f"{source}.title", f"{target}.title", comment["title"])
        if comment.get("text"):
            point["text"] = recorder.copy(f"{source}.text", f"{target}.text", comment["text"])
        point["group"] = [COMMENTS_GROUP]
        link = comment_link(comment, source, f"{target}.evidence_links[0]", recorder, blocks)
        if link:
            point["evidence_links"] = [link]
        comments.append(point)
    return comments


def map_reviewer3(output: str, review: dict[str, Any], blocks: list[Block] | None) -> MappingResult:
    """Fills `review`, the envelope map_with_record built, from Reviewer3's Markdown report."""
    if not isinstance(output, str):
        raise TypeError("Reviewer3 output is the report's Markdown text")
    report = parse_report(output)
    recorder = Recorder(checks_quotes=blocks is not None)
    review["text_format"] = dict(TEXT_FORMAT)
    if report.get("title"):
        review["target"]["title"] = recorder.copy("title", "target.title", report["title"])
    contributions = map_contributions(report, recorder)
    if contributions:
        review["opinion"]["contributions"] = contributions

    checks: list[dict[str, Any]] = []
    weaknesses: list[dict[str, Any]] = []

    def add(check: dict[str, Any]) -> None:
        # A check with nothing in it (say, a table whose rows all lack a status) is left
        # out; what it skipped stays in extensions
        if CHECK_CONTENT & check.keys():
            checks.append(check)

    if report.get("ai_text_detection"):
        add(ai_text_check(report["ai_text_detection"], f"checks[{len(checks)}]", recorder))
    if report.get("fatal_flaws"):
        target = f"checks[{len(checks)}]"
        add(fatal_flaw_check(report["fatal_flaws"], target, weaknesses, recorder))
    if report.get("reference_check"):
        target = f"checks[{len(checks)}]"
        add(reference_check(report["reference_check"], target, recorder))
    if checks:
        review["checks"] = checks

    findings: dict[str, list[dict[str, Any]]] = {}
    if weaknesses:
        findings["weaknesses"] = weaknesses
    comments = map_comments(report, recorder, blocks)
    if comments:
        findings["comments"] = comments
    if findings:
        review["findings"] = findings
    return finish(review, recorder, report, ignored=set())
